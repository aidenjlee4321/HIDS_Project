#include "hids/linux_process_connector.hpp"
#include <cerrno>
#ifdef __linux__
#include <linux/connector.h>
#include <linux/netlink.h>
#include <sys/socket.h>
#include <unistd.h>
#include <poll.h>
#include <atomic>
#include <algorithm>
#endif

namespace hids::process {
#ifdef __linux__
namespace {
// Prevent competing subscriptions from this adapter in one process. This is not
// an interprocess lock; service supervision must avoid duplicate collectors.
std::atomic_flag active = ATOMIC_FLAG_INIT;
}
OpenResult LinuxConnectorIo::open() noexcept {
    if (fd_ >= 0 || guard_owned_) return {EBUSY, 0};
    if (active.test_and_set()) return {EBUSY, 0};
    guard_owned_ = true;
    fd_ = socket(AF_NETLINK, SOCK_DGRAM | SOCK_CLOEXEC, NETLINK_CONNECTOR);
    if (fd_ < 0) { const int error = errno; close(); return {error, 0}; }
    auto failed = [this](int error) { close(); return OpenResult{error, 0}; };
    sockaddr_nl local{};
    local.nl_family = AF_NETLINK;
    local.nl_groups = 1U << (CN_IDX_PROC - 1);
    // Kernel chooses a free port; do not assume port ID equals PID.
    if (bind(fd_, reinterpret_cast<sockaddr*>(&local), sizeof(local)) < 0) return failed(errno);
    socklen_t length = sizeof(local);
    if (getsockname(fd_, reinterpret_cast<sockaddr*>(&local), &length) < 0) return failed(errno);
    if (length != sizeof(local) || local.nl_family != AF_NETLINK || local.nl_pid == 0)
        return failed(EPROTO);
    return {0, local.nl_pid};
}
int LinuxConnectorIo::send(std::span<const std::byte> bytes) noexcept {
    if (fd_ < 0) return EBADF;
    // The caller only supplies its codec's exact control datagrams.
    if (bytes.size() != ControlPacket{}.size()) return EINVAL;
    sockaddr_nl kernel{}; kernel.nl_family = AF_NETLINK;
    const auto size = sendto(fd_, bytes.data(), bytes.size(), MSG_DONTWAIT,
                            reinterpret_cast<sockaddr*>(&kernel), sizeof(kernel));
    if (size < 0) return errno; // Including EINTR: never repeat a LISTEN/IGNORE.
    return static_cast<std::size_t>(size) == bytes.size() ? 0 : EIO;
}
ReadResult LinuxConnectorIo::receive(std::span<std::byte> bytes, std::chrono::milliseconds timeout) noexcept {
    if (fd_ < 0) return {ReadKind::error, 0, EBADF};
    pollfd p{fd_, POLLIN, 0};
    const auto ms = std::clamp(timeout.count(), decltype(timeout.count()){0}, decltype(timeout.count()){100});
    const int ready = poll(&p, 1, static_cast<int>(ms));
    if (ready < 0) return {errno == EINTR ? ReadKind::interrupted : ReadKind::error, 0, errno};
    if (ready == 0) return {ReadKind::timeout};
    if (p.revents & POLLNVAL) return {ReadKind::error, 0, EBADF};
    if (p.revents & POLLHUP) return {ReadKind::closed, 0, EIO};
    if (!(p.revents & (POLLIN | POLLERR))) return {ReadKind::timeout};
    // Netlink uses datagram_poll: POLLERR may be a pending ENOBUFS, including
    // alongside POLLIN. recvmsg retrieves the actual socket error before
    // dequeuing a datagram. Do not close on the readiness bit or consume and
    // discard a readable packet: classify errno below, then let the next poll
    // receive queued data after a recoverable error. EAGAIN is a stale snapshot.
    // See Linux v7.0 net/core/datagram.c __skb_try_recv_datagram().
    sockaddr_nl sender{};
    iovec iov{bytes.data(), bytes.size()};
    msghdr msg{}; msg.msg_name = &sender; msg.msg_namelen = sizeof(sender);
    msg.msg_iov = &iov; msg.msg_iovlen = 1;
    const auto size = recvmsg(fd_, &msg, MSG_DONTWAIT);
    if (size < 0) {
        const int error = errno;
        if (error == EAGAIN || error == EWOULDBLOCK) return {ReadKind::timeout};
        if (error == EINTR) return {ReadKind::interrupted, 0, error};
        if (error == ENOBUFS) return {ReadKind::no_buffer, 0, error};
        return {ReadKind::error, 0, error};
    }
    if (msg.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) return {ReadKind::truncated};
    if (msg.msg_namelen != sizeof(sender) || sender.nl_family != AF_NETLINK || sender.nl_pid != 0)
        return {ReadKind::foreign_sender};
    if (size == 0 || static_cast<std::size_t>(size) > bytes.size()) return {ReadKind::error, 0, EPROTO};
    return {ReadKind::data, static_cast<std::size_t>(size)};
}
int LinuxConnectorIo::close() noexcept {
    int error = 0;
    if (fd_ >= 0) {
        const int fd = fd_; fd_ = -1;
        if (::close(fd) < 0) error = errno; // Linux close must not be retried.
    }
    if (guard_owned_) { guard_owned_ = false; active.clear(); }
    return error;
}
#else
OpenResult LinuxConnectorIo::open() noexcept { return {ENOTSUP, 0}; }
int LinuxConnectorIo::send(std::span<const std::byte>) noexcept { return ENOTSUP; }
ReadResult LinuxConnectorIo::receive(std::span<std::byte>, std::chrono::milliseconds) noexcept {
    return {ReadKind::error, 0, ENOTSUP};
}
int LinuxConnectorIo::close() noexcept { return 0; }
#endif
LinuxConnectorIo::~LinuxConnectorIo() { close(); }
} // namespace hids::process
