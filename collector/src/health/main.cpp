#include "hids/health/snapshot.hpp"
#ifdef __linux__
#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cstddef>
#include <cstring>
#include <fcntl.h>
#include <grp.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/netlink.h>
#include <linux/seccomp.h>
#include <poll.h>
#include <pwd.h>
#include <set>
#include <stdexcept>
#include <string>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/un.h>
#include <unistd.h>
using hids::health::Json;
namespace {
using Clock = std::chrono::steady_clock;
using Deadline = Clock::time_point;
constexpr auto endpoint = "/run/hids/m3/health/metrics.sock";
struct Fd {
    int value;
    explicit Fd(int fd) : value(fd) {}
    ~Fd() { if (value >= 0) ::close(value); }
    Fd(const Fd&) = delete;
};
bool valid_version(const Json& value) {
    return value.is_object() && value.contains("version") && value["version"].is_number_integer() && value["version"] == 3;
}
bool uuid(std::string_view value) {
    if (value.size() != 36) return false;
    for (std::size_t i=0; i<value.size(); ++i) {
        if (i==8 || i==13 || i==18 || i==23) { if (value[i]!='-') return false; }
        else if (!((value[i]>='0' && value[i]<='9') || (value[i]>='a' && value[i]<='f'))) return false;
    }
    return true;
}
bool wait(int fd, short events, Deadline end) {
    while (Clock::now() < end) {
        const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(end-Clock::now()).count();
        pollfd item{fd, events, 0};
        const auto result = ::poll(&item, 1, static_cast<int>(std::max<std::int64_t>(1, std::min<std::int64_t>(ms, 100))));
        if (result > 0) return item.revents & (events|POLLHUP|POLLERR);
        if (result < 0 && errno != EINTR) return false;
    }
    return false;
}
Json exchange(const Json& request, uid_t uid, gid_t gid, gid_t ipc, Deadline end) {
    struct stat info{};
    if (::lstat("/run/hids/m3/health", &info) || !S_ISDIR(info.st_mode) || info.st_uid != uid ||
        info.st_gid != ipc || (info.st_mode & 0777) != 0750) throw std::runtime_error("health_directory");
    if (::lstat(endpoint, &info) || !S_ISSOCK(info.st_mode) || info.st_uid != uid ||
        info.st_gid != ipc || (info.st_mode & 0777) != 0660) throw std::runtime_error("health_socket");
    Fd fd(::socket(AF_UNIX, SOCK_STREAM|SOCK_NONBLOCK|SOCK_CLOEXEC, 0));
    if (fd.value < 0) throw std::runtime_error("health_connect");
    sockaddr_un address{}; address.sun_family=AF_UNIX;
    std::memcpy(address.sun_path, endpoint, std::strlen(endpoint)+1);
    if (::connect(fd.value, reinterpret_cast<sockaddr*>(&address), sizeof(address))) {
        if ((errno != EINPROGRESS && errno != EAGAIN) || !wait(fd.value, POLLOUT, end)) throw std::runtime_error("health_connect");
        int error=0; socklen_t size=sizeof(error);
        if (::getsockopt(fd.value, SOL_SOCKET, SO_ERROR, &error, &size) || error) throw std::runtime_error("health_connect");
    }
    ucred peer{}; socklen_t size=sizeof(peer);
    if (::getsockopt(fd.value, SOL_SOCKET, SO_PEERCRED, &peer, &size) || size != sizeof(peer) ||
        peer.pid <= 0 || peer.uid != uid || peer.gid != gid) throw std::runtime_error("health_peer");
    const auto data = request.dump()+"\n";
    if (data.size() > 2048) throw std::runtime_error("health_frame");
    std::size_t sent=0;
    while (sent < data.size() && Clock::now() < end) {
        const auto count=::send(fd.value, data.data()+sent, data.size()-sent, MSG_NOSIGNAL);
        if (count > 0) sent+=count;
        else if (count < 0 && errno == EINTR) continue;
        else if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK) && wait(fd.value, POLLOUT, end)) continue;
        else throw std::runtime_error("health_send");
    }
    if (sent != data.size()) throw std::runtime_error("health_send");
    std::string raw;
    while (Clock::now() < end) {
        char byte;
        const auto count=::recv(fd.value, &byte, 1, 0);
        if (count == 1) {
            if (byte == '\n') {
                std::set<std::string> keys;
                auto callback = [&keys](int depth, Json::parse_event_t event, Json& parsed) {
                    if (depth > 1 || event == Json::parse_event_t::array_start ||
                        (event == Json::parse_event_t::object_start && depth != 0)) throw std::runtime_error("health_response");
                    if (event == Json::parse_event_t::key && !keys.insert(parsed.get<std::string>()).second)
                        throw std::runtime_error("health_duplicate");
                    return true;
                };
                return Json::parse(raw, callback);
            }
            if (raw.size() >= 512) throw std::runtime_error("health_response_size");
            raw+=byte;
        } else if (count < 0 && errno == EINTR) continue;
        else if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK) && wait(fd.value, POLLIN, end)) continue;
        else break;
    }
    throw std::runtime_error("health_reply_unconfirmed");
}
bool secure() {
#if defined(__aarch64__)
    constexpr unsigned architecture = AUDIT_ARCH_AARCH64;
#elif defined(__x86_64__)
    constexpr unsigned architecture = AUDIT_ARCH_X86_64;
#else
    return false;
#endif
    const sock_filter filter[]{
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(seccomp_data, arch)),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, architecture, 1, 0),
        BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(seccomp_data, nr)),
#define DENY(number) BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, number, 0, 1), BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ERRNO|EPERM)
        DENY(__NR_execve), DENY(__NR_execveat), DENY(__NR_kill), DENY(__NR_tkill), DENY(__NR_tgkill),
        DENY(__NR_ptrace), DENY(__NR_process_vm_readv), DENY(__NR_process_vm_writev),
#ifdef __NR_pidfd_send_signal
        DENY(__NR_pidfd_send_signal),
#endif
#undef DENY
        BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ALLOW)
    };
    const sock_fprog program{static_cast<unsigned short>(std::size(filter)), const_cast<sock_filter*>(filter)};
    return !::prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) && !::prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program);
}
Json kernel(Deadline end) {
    Fd boot(::open("/proc/sys/kernel/random/boot_id", O_RDONLY|O_NOFOLLOW|O_CLOEXEC));
    std::array<char, 38> bytes{};
    const auto count=boot.value < 0 ? -1 : ::read(boot.value, bytes.data(), bytes.size());
    if (count != 37 || bytes[36] != '\n' || !uuid(std::string_view(bytes.data(), 36))) return {{"state", "invalid"}};
    const std::string boot_id(bytes.data(), 36);
    Fd fd(::socket(AF_NETLINK, SOCK_RAW|SOCK_NONBLOCK|SOCK_CLOEXEC, NETLINK_AUDIT));
    if (fd.value < 0) return {{"state", "unavailable"}};
    sockaddr_nl local{}; local.nl_family=AF_NETLINK;
    if (::bind(fd.value, reinterpret_cast<sockaddr*>(&local), sizeof(local))) return {{"state", "unavailable"}};
    nlmsghdr request{}; request.nlmsg_len=NLMSG_HDRLEN; request.nlmsg_type=AUDIT_GET;
    request.nlmsg_flags=NLM_F_REQUEST|NLM_F_ACK; request.nlmsg_seq=1;
    sockaddr_nl address{}; address.nl_family=AF_NETLINK;
    if (::sendto(fd.value, &request, sizeof(request), 0, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != static_cast<ssize_t>(sizeof(request)))
        return {{"state", "unavailable"}};
    for (unsigned attempt=0; attempt<4; ++attempt) {
        if (!wait(fd.value, POLLIN, std::min(end, Clock::now()+std::chrono::milliseconds(500)))) return {{"state", "timeout"}};
        alignas(nlmsghdr) std::array<char, 4096> packet{};
        sockaddr_nl from{}; socklen_t size=sizeof(from);
        const auto length=::recvfrom(fd.value, packet.data(), packet.size(), 0, reinterpret_cast<sockaddr*>(&from), &size);
        if (length < 0 && (errno == EINTR || errno == EAGAIN)) continue;
        if (length < static_cast<ssize_t>(sizeof(nlmsghdr)) || size != sizeof(from) || from.nl_pid != 0 || from.nl_groups != 0)
            return {{"state", "invalid"}};
        const auto* header=reinterpret_cast<const nlmsghdr*>(packet.data());
        if (header->nlmsg_seq != 1 || header->nlmsg_len > static_cast<unsigned>(length) || header->nlmsg_len < NLMSG_HDRLEN)
            return {{"state", "invalid"}};
        const auto payload=header->nlmsg_len-NLMSG_HDRLEN;
        if (header->nlmsg_type == NLMSG_ERROR) {
            if (payload < sizeof(nlmsgerr)) return {{"state", "invalid"}};
            nlmsgerr error{}; std::memcpy(&error, packet.data()+NLMSG_HDRLEN, sizeof(error));
            if (error.error == 0) continue;
            return {{"state", "unavailable"}};
        }
        if (header->nlmsg_type != AUDIT_GET || payload < offsetof(audit_status, backlog)+sizeof(unsigned)) return {{"state", "invalid"}};
        audit_status status{};
        std::memcpy(&status, packet.data()+NLMSG_HDRLEN, std::min<std::size_t>(payload, sizeof(status)));
        if (status.enabled > 2) return {{"state", "invalid"}};
        return {{"state", "observed"}, {"boot_id", boot_id}, {"auditd_pid", status.pid},
                {"enabled", status.enabled}, {"lost", status.lost}, {"backlog", status.backlog}, {"backlog_limit", status.backlog_limit}};
    }
    return {{"state", "invalid"}};
}
}
int main(int argc, char**) {
    if (argc != 1 || ::getuid() != 0 || ::geteuid() != 0) return 1;
    try {
        const auto* account=::getpwnam("hids-ingest");
        if (!account || account->pw_uid == 0 || account->pw_gid == 0) return 1;
        const auto uid=account->pw_uid, gid=account->pw_gid;
        const auto* group=::getgrnam("hids-ipc");
        if (!group || group->gr_gid == 0) return 1;
        const auto ipc=group->gr_gid;
        if (!secure()) return 1;
        const auto end=Clock::now()+std::chrono::seconds(2);
        const auto scope=exchange({{"version", 3}, {"command", "scope"}}, uid, gid, ipc, end);
        if (!valid_version(scope)) return 1;
        if (scope == Json{{"version", 3}, {"result", "inactive"}}) return 0;
        if (scope.size() != 4 || !scope.contains("version") || !scope["version"].is_number_integer() || scope["version"] != 3 ||
            scope.value("result", "") != "scope" || !scope.contains("activation") || !scope["activation"].is_string() ||
            !scope.contains("generation") || !scope["generation"].is_string() || !uuid(scope["activation"].get<std::string>()) ||
            !uuid(scope["generation"].get<std::string>())) return 1;
        const auto sample=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();
        Json observation{{"sample_ns", sample}, {"kernel", kernel(end)}, {"dispatcher", hids::health::read_dispatcher()}};
        const auto response=exchange({{"version", 3}, {"command", "sample"}, {"activation", scope["activation"]},
            {"generation", scope["generation"]}, {"observation", observation}}, uid, gid, ipc, end);
        if (!valid_version(response)) return 1;
        if (response == Json{{"version", 3}, {"result", "recorded"}} || response == Json{{"version", 3}, {"result", "duplicate"}}) return 0;
    } catch (const std::exception&) {}
    constexpr char error[]="m3_health_sample_unconfirmed\n";
    ::write(STDERR_FILENO, error, sizeof(error)-1);
    return 1;
}
#else
int main() { return 1; }
#endif
