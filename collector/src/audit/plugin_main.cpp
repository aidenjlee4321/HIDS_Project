#include "hids/audit/auparse_execution.hpp"
#include "hids/audit/current_tail.hpp"
#include "hids/audit/plugin_transport.hpp"
#include "hids/journal/transport.hpp"

#include <array>
#include <cerrno>
#include <charconv>
#include <csignal>
#include <iostream>
#include <poll.h>
#include <unistd.h>

namespace {
volatile std::sig_atomic_t stopping = 0;

void stop(int signal) {
    stopping = signal;
}

bool number(std::string_view input, unsigned& value) {
    const auto [end, error] = std::from_chars(input.data(), input.data() + input.size(), value);
    return error == std::errc{} && end == input.data() + input.size();
}

std::string_view failure_code(std::string_view error) {
    if (error == "resource_report_unconfirmed" || error == "admission_unconfirmed" || error == "finalization_unconfirmed")
        return "collector_delivery_failure";
    if (error == "parser_failure") return "collector_parser_failure";
    if (error == "allocation_failure") return "collector_capacity";
    if (error == "assembly_timeout") return "assembly_timeout";
    if (error.ends_with("capacity")) return "collector_capacity";
    return "collector_input_failure";
}
}

int main(int argc, char** argv) {
    // The trusted launcher provides the scope only after activation and drops
    // to the configured reader identity before invoking this executable.
    if ((argc != 10 && argc != 11) || getuid() == 0 || geteuid() == 0) return 1;
    if (argc == 11 && std::string_view(argv[10]) != "--current-tail") return 1;
    unsigned reader_uid, reader_gid;
    hids::journal::Peer peer{};
    if (!number(argv[5], reader_uid) || !number(argv[6], reader_gid) ||
        !number(argv[7], peer.uid) || !number(argv[8], peer.gid) ||
        !number(argv[9], peer.ipc_gid) || reader_gid == 0 || peer.gid == 0 ||
        peer.ipc_gid == 0) return 1;

    struct sigaction action{};
    action.sa_handler = stop;
    if (sigemptyset(&action.sa_mask) || sigaction(SIGTERM, &action, nullptr) ||
        sigaction(SIGINT, &action, nullptr)) return 1;
    // Auditd sends HUP after reconfiguration, including plugin startup. This
    // process has immutable launcher arguments. Its receiver owns lease revocation.
    action.sa_handler = SIG_IGN;
    if (sigaction(SIGHUP, &action, nullptr)) return 1;

    auto cancelled = [] { return stopping != 0; };
    hids::journal::UnixChannel channel(argv[1], peer, cancelled, reader_uid, reader_gid);
    using namespace std::chrono;
    if (const auto error = channel.connect(channel.now() + seconds(2))) {
        std::cerr << "M3 plugin connection failed: " << error << '\n';
        return 1;
    }
    const hids::audit::PluginScope scope{argv[2], argv[3], argv[4]};
    const auto fail = [&](std::string_view code) {
        hids::audit::report_plugin_gap(channel, scope, code);
        return 1;
    };
    if (argc == 11 && !hids::audit::discard_queued_input(
            STDIN_FILENO, hids::audit::Limits{}.total_bytes, cancelled)) {
        std::cerr << "M3 current-tail boundary unavailable\n";
        return fail("current_tail_unavailable");
    }
    if (argc == 11) {
        try {
            const hids::journal::Json request{
                {"version", 3}, {"op", "boundary"}, {"activation", argv[2]},
                {"generation", argv[3]}, {"lease", argv[4]},
            };
            const auto reply = hids::journal::request(channel, request, channel.now() + seconds(2), 256);
            if (reply != hids::journal::Json{{"version", 3}, {"status", "boundary"}}) return 1;
        } catch (const std::exception&) {
            std::cerr << "M3 current-tail boundary unconfirmed\n";
            return 1;
        }
    }
    const auto start = channel.now();
    const auto clock = [&channel, start] {
        return static_cast<std::uint64_t>(duration_cast<milliseconds>(channel.now()-start).count());
    };
    auto session = hids::audit::make_plugin_session(
        channel, scope, hids::audit::validate_auparse_execution, clock);

    std::array<char, 4096> bytes{};
    while (!cancelled()) {
        const auto tick = duration_cast<milliseconds>(channel.now() - start).count();
        if (!session.tick(tick)) {
            std::cerr << "M3 plugin stopped: " << session.error() << '\n';
            return fail(failure_code(session.error()));
        }
        pollfd inputs[]{{STDIN_FILENO, POLLIN, 0}, {channel.descriptor(), POLLIN, 0}};
        const int ready = ::poll(inputs, 2, 100);
        if (ready < 0 && errno == EINTR) continue;
        if (inputs[1].revents) {
            std::cerr << "M3 receiver disconnected\n";
            return 1;
        }
        if (ready < 0 || (inputs[0].revents & (POLLERR | POLLNVAL))) {
            std::cerr << "M3 plugin input poll failed\n";
            return fail("collector_input_failure");
        }
        if (ready == 0) continue;
        const auto count = ::read(STDIN_FILENO, bytes.data(), bytes.size());
        if (count < 0 && errno == EINTR) continue;
        if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (count < 0) {
            std::cerr << "M3 plugin input read failed\n";
            return fail("collector_input_failure");
        }
        if (count == 0) {
            if (session.finish()) return 0;
            std::cerr << "M3 plugin input closed with unfinished records\n";
            return fail("incomplete_shutdown");
        }
        const auto observed = duration_cast<milliseconds>(channel.now() - start).count();
        if (!session.consume({bytes.data(), static_cast<std::size_t>(count)}, observed)) {
            std::cerr << "M3 plugin stopped: " << session.error()
                      << "; signal=" << stopping << '\n';
            return fail(failure_code(session.error()));
        }
    }
    return 0;
}
