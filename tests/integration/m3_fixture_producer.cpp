#include "hids/audit/plugin_transport.hpp"
#include "nlohmann/json.hpp"

#include <fstream>
#include <iostream>
#include <poll.h>
#include <unistd.h>

using nlohmann::json;

namespace {
class FixtureSocket final : public hids::pilot::Channel {
public:
    explicit FixtureSocket(int fd) : fd_(fd) {}
    ~FixtureSocket() override { close(); }
    int connect(hids::pilot::Deadline) override { return 0; }
    ssize_t write(const void* bytes, std::size_t size) override { return ::write(fd_, bytes, size); }
    ssize_t read(void* bytes, std::size_t size) override { return ::read(fd_, bytes, size); }
    bool wait(bool writing, hids::pilot::Deadline deadline) override {
        const auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - now());
        if (duration.count() <= 0) return false;
        pollfd item{fd_, static_cast<short>(writing ? POLLOUT : POLLIN), 0};
        return ::poll(&item, 1, static_cast<int>(duration.count())) > 0;
    }
    void close() noexcept override {
        if (fd_ >= 0) ::close(fd_);
        fd_ = -1;
    }
private:
    int fd_;
};

bool exchange(json request, std::string_view expected) {
    request["version"] = 3;
    request["activation"] = "fixture-activation";
    request["generation"] = "fixture-generation";
    request["lease"] = "fixture-lease";
    std::cout << request.dump() << std::endl;
    std::string reply;
    for (char byte; reply.size() < 32 && std::cin.get(byte);) {
        if (byte == '\n') return reply == expected;
        reply += byte;
    }
    return false;
}

std::string identity(const hids::audit::Key& key) {
    return key.seconds + "." + key.fraction + ":" + key.serial;
}
}

int drive(hids::audit::PluginSession& session) {
    std::ifstream fixture("tests/fixtures/audit/structural-exec.log");
    if (!fixture) return 1;
    for (std::string line; std::getline(fixture, line);) {
        if (fixture.eof()) return 1;
        if (line.starts_with("type=EOE ")) line += ' ';
        line += '\n';
        if (!session.consume(line, 0)) return 2;
    }
    return fixture.eof() && session.finish() ? 0 : 1;
}

int main(int argc, char** argv) {
    using namespace hids::audit;
    if (argc == 2) {
        FixtureSocket channel(std::stoi(argv[1]));
        auto session = make_plugin_session(channel,
            {"fixture-activation", "fixture-generation", "fixture-lease"}, validate_execution);
        return drive(session);
    }
    PluginSession session(
        [](const Record& record) {
            return exchange({{"op", "register"}, {"identity", identity(record.key)},
                             {"begin", record.begin}, {"end", record.end},
                             {"eoe", record.type == "EOE"}}, "admit");
        },
        [](const Event& event, const ExecutionResult& result) {
            if (!result.execution) {
                return exchange({{"op", "reject"}, {"identity", identity(event.key)}}, "rejected");
            }
            const auto& x = *result.execution;
            const json payload = {
                {"syscall", x.syscall}, {"pid", x.pid}, {"ppid", x.ppid},
                {"uid", x.uid}, {"euid", x.euid}, {"suid", x.suid}, {"fsuid", x.fsuid},
                {"auid", x.auid ? json(*x.auid) : json(nullptr)},
                {"session", x.session ? json(*x.session) : json(nullptr)},
                {"result", x.result}, {"success", x.success},
                {"exe_base64", x.exe_base64}, {"comm_base64", x.comm_base64},
                {"path_count", x.path_count}, {"cwd_present", x.cwd_present},
                {"proctitle_present", x.proctitle_present},
            };
            return exchange({{"op", "accept"}, {"identity", identity(x.key)},
                             {"execution", payload}}, "accepted");
        },
        validate_execution);
    return drive(session);
}
