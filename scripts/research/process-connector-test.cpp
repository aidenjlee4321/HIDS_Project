// Temporary Linux cn_proc research, not a production HIDS collector.
// Build on Ubuntu: c++ -std=c++20 -O2 -Wall -Wextra -Wpedantic ...
// One socket, one filtered LISTEN, one child, one explicit IGNORE; no sudo.
// Protocol review: https://github.com/torvalds/linux/blob/v7.0/drivers/connector/cn_proc.c
#ifndef __linux__
#include <cstdio>
int main() {
    std::puts("Not investigated: this experiment requires Linux UAPI headers and a Linux kernel.");
    return 2;
}
#else
#include <linux/cn_proc.h>
#include <linux/connector.h>
#include <linux/netlink.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <sys/utsname.h>
#include <poll.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cerrno>
#include <climits>

namespace {
using Clock = std::chrono::steady_clock;
volatile sig_atomic_t interrupted = 0;
void stop(int sig) { interrupted = sig; } // No socket operations inside handlers.
constexpr std::uint32_t mask = PROC_EVENT_FORK | PROC_EVENT_EXEC | PROC_EVENT_EXIT;
constexpr std::uint32_t listen_seq = 1, ignore_seq = 2;
constexpr std::size_t nl_size = sizeof(nlmsghdr), cn_size = sizeof(cn_msg);
static_assert(sizeof(proc_cn_mcast_op) == 4 && sizeof(proc_cn_event) == 4);
static_assert(sizeof(proc_input) == 8 && offsetof(proc_input, event_type) == 4);
static_assert(nl_size == 16 && cn_size == 20 && offsetof(cn_msg, data) == 20);
static_assert(offsetof(proc_event, timestamp_ns) == 8);
static_assert(offsetof(proc_event, event_data) == 16 && alignof(proc_event) >= 8);
static_assert(sizeof(proc_event) == 40, "Unexpected UAPI ABI; review before running");

void error(const char* operation, int code = errno) {
    std::printf("%s: errno=%d (%s)\n", operation, code, std::strerror(code));
}

// Byte-copy serialization avoids flexible-array embedding and unaligned casts.
auto control_packet(proc_cn_mcast_op op, std::uint32_t port, std::uint32_t token) {
    std::array<unsigned char, nl_size + cn_size + sizeof(proc_input)> packet{};
    nlmsghdr n{};
    n.nlmsg_len = static_cast<__u32>(packet.size());
    n.nlmsg_type = NLMSG_DONE;
    n.nlmsg_pid = port;
    n.nlmsg_seq = op == PROC_CN_MCAST_LISTEN ? listen_seq : ignore_seq;
    cn_msg c{};
    c.id.idx = CN_IDX_PROC;
    c.id.val = CN_VAL_PROC;
    c.seq = n.nlmsg_seq;
    c.ack = token;
    c.len = sizeof(proc_input);
    proc_input input{};
    input.mcast_op = op;
    input.event_type = static_cast<proc_cn_event>(mask);
    std::memcpy(packet.data(), &n, nl_size);
    std::memcpy(packet.data() + nl_size, &c, cn_size);
    std::memcpy(packet.data() + nl_size + cn_size, &input, sizeof(input));
    return packet;
}

struct Resources {
    int fd = -1;
    pid_t child = -1; // Not reaped until no more child events will be accepted.
    bool listen_attempted = false;
    std::uint32_t port = 0, token = 0;
    bool cleanup_ok = true;

    bool control(proc_cn_mcast_op op) {
        const auto packet = control_packet(op, port, token);
        sockaddr_nl kernel{};
        kernel.nl_family = AF_NETLINK;
        const auto sent = sendto(fd, packet.data(), packet.size(), MSG_DONTWAIT,
                                 reinterpret_cast<sockaddr*>(&kernel), sizeof(kernel));
        if (sent < 0) {
            error(op == PROC_CN_MCAST_LISTEN ? "LISTEN sendto" : "IGNORE sendto");
            return false; // No control-message retries, including EINTR.
        }
        if (static_cast<std::size_t>(sent) != packet.size()) {
            std::puts("Control datagram short send; outcome inconclusive.");
            return false;
        }
        return true;
    }

    bool cleanup() {
        if (fd >= 0 && listen_attempted) {
            // This flag is set before LISTEN sendto, including uncertain sends.
            // Exactly one IGNORE attempt; never parallel with another control.
            listen_attempted = false;
            if (control(PROC_CN_MCAST_IGNORE)) {
                std::puts("IGNORE sent before close; kernel completion unconfirmed. No IGNORE ACK wait (final-listener ACK may be suppressed).");
            } else {
                std::puts("WARNING: explicit unsubscribe failed; listener cleanup is inconclusive. Do not rerun automatically.");
                cleanup_ok = false;
            }
        }
        if (child > 0) {
            int status = 0;
            pid_t result;
            do { result = waitpid(child, &status, WNOHANG); } while (result < 0 && errno == EINTR);
            if (result == 0) {
                // Only the unreaped direct child: PID cannot have been reused.
                if (kill(child, SIGKILL) < 0 && errno != ESRCH) {
                    error("Controlled child cleanup kill");
                    cleanup_ok = false;
                }
                do { result = waitpid(child, &status, 0); } while (result < 0 && errno == EINTR);
            }
            if (result == child) {
                if (WIFEXITED(status))
                    std::printf("Controlled child reaped: exit_status=%d\n", WEXITSTATUS(status));
                else if (WIFSIGNALED(status))
                    std::printf("Controlled child reaped: signal=%d\n", WTERMSIG(status));
            } else {
                error("Controlled child waitpid");
                cleanup_ok = false;
            }
            child = -1;
        }
        if (fd >= 0) {
            // Never retry close: on Linux fd ownership is released even on EINTR.
            if (close(fd) < 0) { error("Socket close"); cleanup_ok = false; }
            fd = -1;
        }
        return cleanup_ok;
    }
    ~Resources() { cleanup(); }
};

struct Report {
    bool ack_seen = false, fatal = false;
    bool fork_seen = false, exec_seen = false, exit_seen = false;
    std::uint32_t ack_error = 0;
    unsigned malformed = 0, overrun = 0, enobufs = 0, truncated = 0;
    unsigned discontinuities = 0, untracked_cpu = 0, shown = 0;
    struct Sequence { bool seen = false; std::uint32_t last = 0; };
    std::array<Sequence, 4096> sequences{};

    void event(const cn_msg& c, const proc_event& e, pid_t child, std::uint32_t token) {
        if (e.what == PROC_EVENT_NONE) {
            // ACKs are multicast, not necessarily ours. v7.0 send_msg overwrites
            // seq/cpu, so match the request's ack cookie, not a global sequence.
            if (c.ack == token + 1U) {
                const bool first_ack = !ack_seen;
                ack_seen = true;
                ack_error = e.event_data.ack.err;
                if (first_ack && ack_error == 0)
                    std::puts("LISTEN: matching connector ACK reported success.");
                if (ack_error != 0) {
                    if (ack_error <= INT_MAX) error("LISTEN connector ACK", static_cast<int>(ack_error));
                    else std::printf("LISTEN connector ACK: error=%u (unknown errno)\n", ack_error);
                    fatal = true;
                }
            }
            return;
        }
        // Sequence accounting is per CPU and includes allowed unrelated events
        // internally. Filtering and ACKs can skip numbers: never assert loss count.
        if (e.cpu < sequences.size()) {
            auto& s = sequences[e.cpu];
            if (s.seen && static_cast<std::uint32_t>(c.seq - s.last) != 1U) ++discontinuities;
            s = {true, c.seq};
        } else ++untracked_cpu;
        if (child <= 0) return;
        int pid = 0, tgid = 0, ppid = 0, ptgid = 0;
        const char* name = nullptr;
        bool parents = false;
        if (e.what == PROC_EVENT_FORK) {
            pid = e.event_data.fork.child_pid; tgid = e.event_data.fork.child_tgid;
            ppid = e.event_data.fork.parent_pid; ptgid = e.event_data.fork.parent_tgid;
            name = "FORK"; parents = true;
        } else if (e.what == PROC_EVENT_EXEC) {
            pid = e.event_data.exec.process_pid; tgid = e.event_data.exec.process_tgid;
            name = "EXEC";
        } else if (e.what == PROC_EVENT_EXIT) {
            pid = e.event_data.exit.process_pid; tgid = e.event_data.exit.process_tgid;
            ppid = e.event_data.exit.parent_pid; ptgid = e.event_data.exit.parent_tgid;
            name = "EXIT"; parents = true;
        }
        // Exact single-thread child identity, not events where child is a parent.
        if (!name || pid != child || tgid != child) return;
        if (e.what == PROC_EVENT_FORK) fork_seen = true;
        if (e.what == PROC_EVENT_EXEC) exec_seen = true;
        if (e.what == PROC_EVENT_EXIT) exit_seen = true;
        if (shown++ >= 8) return;
        std::printf("event=%s pid=%d tgid=%d", name, pid, tgid);
        if (parents) std::printf(" parent_pid=%d parent_tgid=%d", ppid, ptgid);
        else std::printf(" parent=not_provided");
        std::printf(" cpu=%u connector_seq=%u timestamp_ns=%llu (kernel monotonic, not wall clock)\n",
                    e.cpu, c.seq, static_cast<unsigned long long>(e.timestamp_ns));
    }

    void parse(const unsigned char* bytes, std::size_t size, pid_t child, std::uint32_t token) {
        std::size_t offset = 0;
        while (offset < size && !fatal) {
            if (size - offset < nl_size) { ++malformed; return; }
            nlmsghdr n{};
            std::memcpy(&n, bytes + offset, nl_size);
            const std::size_t len = n.nlmsg_len;
            if (len < nl_size || len > size - offset) { ++malformed; return; }
            const auto* payload = bytes + offset + nl_size;
            const std::size_t payload_len = len - nl_size;
            if (n.nlmsg_pid != 0) { ++malformed; return; }
            if (n.nlmsg_type == NLMSG_OVERRUN) ++overrun;
            else if (n.nlmsg_type == NLMSG_ERROR) {
                if (payload_len < sizeof(nlmsgerr)) { ++malformed; return; }
                nlmsgerr err{};
                std::memcpy(&err, payload, sizeof(err));
                if (err.error != 0) {
                    // Widen before negation so INT_MIN cannot overflow.
                    const auto code = -static_cast<std::int64_t>(err.error);
                    if (code > 0 && code <= INT_MAX) error("Kernel NLMSG_ERROR", static_cast<int>(code));
                    else std::printf("Kernel NLMSG_ERROR: unexpected signed error=%d\n", err.error);
                    fatal = true;
                }
                // A generic netlink success is not a connector LISTEN ACK.
            } else if (n.nlmsg_type == NLMSG_DONE) {
                // Connector uses NLMSG_DONE to carry data, not a dump terminator.
                if (payload_len < cn_size) { ++malformed; return; }
                cn_msg c{};
                std::memcpy(&c, payload, cn_size);
                if (c.len != payload_len - cn_size) { ++malformed; return; }
                if (c.id.idx == CN_IDX_PROC && c.id.val == CN_VAL_PROC) {
                    if (c.len != sizeof(proc_event)) { ++malformed; return; }
                    proc_event e{};
                    // Wire data follows a 20-byte cn_msg: may be only 4-byte
                    // aligned on ARM64. Never cast that pointer to proc_event*.
                    std::memcpy(&e, payload + cn_size, sizeof(e));
                    event(c, e, child, token);
                }
            } else if (n.nlmsg_type != NLMSG_NOOP) ++malformed;
            const std::size_t aligned = (len + 3U) & ~std::size_t{3U};
            if (aligned > size - offset) {
                if (len != size - offset) ++malformed;
                return; // An unpadded final message is safe to accept.
            }
            offset += aligned;
        }
    }
};

// Bounded receive: no loops without a monotonic deadline, even on busy hosts.
void receive_until(Resources& r, Report& report, Clock::time_point deadline, bool ack_phase) {
    unsigned datagrams = 0;
    while (!interrupted && !report.fatal && Clock::now() < deadline && datagrams < 10000) {
        if (ack_phase && report.ack_seen) break;
        if (!ack_phase && report.fork_seen && report.exec_seen && report.exit_seen) break;
        pollfd p{r.fd, POLLIN, 0};
        const auto ready = poll(&p, 1, 50);
        if (ready < 0) {
            if (errno == EINTR) continue;
            error("poll"); report.fatal = true; break;
        }
        if (ready == 0) continue;
        if (p.revents & (POLLHUP | POLLNVAL)) {
            std::puts("Socket hangup/invalid descriptor; observation inconclusive.");
            report.fatal = true; break;
        }
        std::array<unsigned char, 16384> buffer{};
        sockaddr_nl sender{};
        iovec iov{buffer.data(), buffer.size()};
        msghdr msg{};
        msg.msg_name = &sender; msg.msg_namelen = sizeof(sender);
        msg.msg_iov = &iov; msg.msg_iovlen = 1;
        const auto size = recvmsg(r.fd, &msg, MSG_DONTWAIT);
        if (size < 0) {
            if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) continue;
            if (errno == ENOBUFS) { ++report.enobufs; continue; }
            error("recvmsg"); report.fatal = true; break;
        }
        ++datagrams;
        if (msg.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) { ++report.truncated; continue; }
        if (size == 0 || static_cast<std::size_t>(size) > buffer.size() ||
            msg.msg_namelen != sizeof(sender) || sender.nl_family != AF_NETLINK || sender.nl_pid != 0) {
            ++report.malformed; continue;
        }
        report.parse(buffer.data(), static_cast<std::size_t>(size), r.child, r.token);
    }
    if (datagrams == 10000) {
        std::puts("Receive work cap reached; observation incomplete.");
        report.fatal = true;
    }
}

int run() {
    if (geteuid() == 0 || getuid() == 0) {
        std::puts("Run once as an ordinary user. Root launch refused; no sudo retry.");
        return 2;
    }
    struct sigaction action{};
    action.sa_handler = stop;
    sigemptyset(&action.sa_mask);
    for (int sig : {SIGINT, SIGTERM, SIGHUP}) {
        if (sigaction(sig, &action, nullptr) < 0) { error("sigaction"); return 1; }
    }
    // Avoid termination by a closed report pipe before RAII cleanup can execute.
    action.sa_handler = SIG_IGN;
    if (sigaction(SIGPIPE, &action, nullptr) < 0) { error("sigaction SIGPIPE"); return 1; }
    // Keep the direct child unreaped (and its PID reserved) until cleanup.
    action.sa_handler = SIG_DFL;
    if (sigaction(SIGCHLD, &action, nullptr) < 0) { error("sigaction SIGCHLD"); return 1; }
    std::puts("Temporary cn_proc experiment v1: one ordinary-user subscription; FORK|EXEC|EXIT only.");
    utsname platform{};
    if (uname(&platform) == 0) std::printf("Kernel=%s architecture=%s\n", platform.release, platform.machine);
    std::printf("ABI: proc_input=%zu cn_msg=%zu proc_event=%zu event_alignment=%zu\n",
                sizeof(proc_input), cn_size, sizeof(proc_event), alignof(proc_event));
    Resources r;
    r.fd = socket(AF_NETLINK, SOCK_DGRAM, NETLINK_CONNECTOR);
    if (r.fd < 0) { error("socket NETLINK_CONNECTOR"); return 1; }
    if (fcntl(r.fd, F_SETFD, FD_CLOEXEC) < 0) { error("fcntl FD_CLOEXEC"); return 1; }
    sockaddr_nl local{};
    local.nl_family = AF_NETLINK;
    local.nl_pid = static_cast<__u32>(getpid());
    local.nl_groups = 1U << (CN_IDX_PROC - 1);
    if (bind(r.fd, reinterpret_cast<sockaddr*>(&local), sizeof(local)) < 0) {
        error("bind CN_IDX_PROC"); return 1;
    }
    r.port = local.nl_pid;
    r.token = (static_cast<std::uint32_t>(Clock::now().time_since_epoch().count()) ^ r.port) & 0x7fffffffU;
    if (interrupted) return 128 + interrupted;
    r.listen_attempted = true;
    if (!r.control(PROC_CN_MCAST_LISTEN)) return 1;
    Report report;
    receive_until(r, report, Clock::now() + std::chrono::seconds(1), true);
    if (report.fatal || interrupted) return interrupted ? 128 + interrupted : 1;
    if (!report.ack_seen) std::puts("LISTEN ACK not observed: subscription unconfirmed (filtered ACK may be suppressed). One controlled child will test delivery; no LISTEN/root retry.");
    if (interrupted) return 128 + interrupted;
    r.child = fork();
    if (r.child < 0) { error("fork"); return 1; }
    if (r.child == 0) {
        // The child never sends controls and never runs the parent's destructors.
        close(r.fd);
        if (interrupted) _exit(126);
        execl("/usr/bin/sleep", "sleep", "2", static_cast<char*>(nullptr));
        const int code = errno;
        // No private arguments or unrelated process information.
        dprintf(STDOUT_FILENO, "Controlled child exec failed: errno=%d\n", code);
        _exit(127);
    }
    std::printf("Controlled child pid/tgid=%d; requested sleep duration=2 seconds.\n", r.child);
    receive_until(r, report, Clock::now() + std::chrono::seconds(5), false);
    std::printf("Child observations: FORK=%s EXEC=%s EXIT=%s\n",
                report.fork_seen ? "Observed" : "Not observed in sample",
                report.exec_seen ? "Observed" : "Not observed in sample",
                report.exit_seen ? "Observed" : "Not observed in sample");
    std::printf("Receive diagnostics: malformed_or_unexpected=%u overrun=%u ENOBUFS=%u truncated=%u\n",
                report.malformed, report.overrun, report.enobufs, report.truncated);
    std::printf("Per-CPU sequence discontinuities=%u (not a loss count); untracked CPU observations=%u.\n",
                report.discontinuities, report.untracked_cpu);
    std::puts("Limitations: filtered multicast is lossy; missing events/ACKs are inconclusive. No wall-clock conversion, system-wide history or root retry.");
    const bool cleaned = r.cleanup();
    if (interrupted) return 128 + interrupted;
    return cleaned && !report.fatal && report.fork_seen && report.exec_seen && report.exit_seen &&
           !report.malformed && !report.overrun && !report.enobufs && !report.truncated ? 0 : 1;
}
} // namespace

int main() {
    // No asynchronous cleanup, threads, automatic retries or repeated subscriptions.
    return run();
}
#endif
