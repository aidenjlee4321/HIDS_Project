#include "hids/process_collector.hpp"
#include <linux/cn_proc.h>
#include <linux/connector.h>
#include <linux/netlink.h>
#include <cstring>
#include <climits>
#include <cerrno>

namespace hids::process {
namespace {
constexpr std::size_t nh = sizeof(nlmsghdr), ch = sizeof(cn_msg);
constexpr std::uint32_t wanted = PROC_EVENT_FORK | PROC_EVENT_EXEC | PROC_EVENT_EXIT;
static_assert(sizeof(proc_input) == 8 && sizeof(proc_cn_event) == 4 && sizeof(proc_cn_mcast_op) == 4);
static_assert(offsetof(proc_input, event_type) == 4);
static_assert(nh == 16 && ch == 20 && offsetof(cn_msg, data) == ch);
static_assert(sizeof(proc_event) == 40 && alignof(proc_event) >= 8);
static_assert(offsetof(proc_event, timestamp_ns) == 8 && offsetof(proc_event, event_data) == 16);
void malformed(DecodeSink& sink) noexcept { sink.protocol_diagnostic(Reason::malformed); }
void event(const cn_msg& c, const proc_event& e, DecodeSink& sink) noexcept {
    if (e.what == PROC_EVENT_NONE) {
        sink.acknowledgement(c.ack, e.event_data.ack.err); return;
    }
    NativeEvent out{};
    out.cpu = e.cpu; out.sequence = c.seq; out.kernel_monotonic_ns = e.timestamp_ns;
    switch (e.what) {
    case PROC_EVENT_FORK:
        out.kind = Lifecycle::forked;
        out.tid = e.event_data.fork.child_pid; out.tgid = e.event_data.fork.child_tgid;
        out.parent = Parent{e.event_data.fork.parent_pid, e.event_data.fork.parent_tgid};
        break;
    case PROC_EVENT_EXEC:
        out.kind = Lifecycle::executed;
        out.tid = e.event_data.exec.process_pid; out.tgid = e.event_data.exec.process_tgid;
        break;
    case PROC_EVENT_EXIT:
        out.kind = Lifecycle::exited;
        out.tid = e.event_data.exit.process_pid; out.tgid = e.event_data.exit.process_tgid;
        out.parent = Parent{e.event_data.exit.parent_pid, e.event_data.exit.parent_tgid};
        out.native_exit_status = e.event_data.exit.exit_code;
        out.native_exit_signal = e.event_data.exit.exit_signal;
        break;
    default:
        sink.protocol_diagnostic(Reason::unexpected_event); return;
    }
    if (out.tid <= 0 || out.tgid <= 0 ||
        (out.parent && (out.parent->tid < 0 || out.parent->tgid < 0))) {
        malformed(sink); return;
    }
    sink.native_event(out);
}
} // namespace
ControlPacket control_packet(bool listen, std::uint32_t port, std::uint32_t cookie) noexcept {
    ControlPacket bytes{};
    nlmsghdr n{}; n.nlmsg_len = bytes.size(); n.nlmsg_type = NLMSG_DONE;
    n.nlmsg_pid = port; n.nlmsg_seq = listen ? 1U : 2U;
    cn_msg c{}; c.id.idx = CN_IDX_PROC; c.id.val = CN_VAL_PROC;
    c.seq = n.nlmsg_seq; c.ack = cookie; c.len = sizeof(proc_input);
    proc_input input{};
    input.mcast_op = listen ? PROC_CN_MCAST_LISTEN : PROC_CN_MCAST_IGNORE;
    input.event_type = static_cast<proc_cn_event>(wanted);
    std::memcpy(bytes.data(), &n, nh);
    std::memcpy(bytes.data() + nh, &c, ch);
    std::memcpy(bytes.data() + nh + ch, &input, sizeof(input));
    return bytes;
}
void decode(std::span<const std::byte> bytes, DecodeSink& sink) noexcept {
    if (bytes.empty()) { malformed(sink); return; }
    std::size_t offset = 0;
    while (offset < bytes.size()) {
        if (bytes.size() - offset < nh) { malformed(sink); return; }
        nlmsghdr n{}; std::memcpy(&n, bytes.data() + offset, nh);
        const std::size_t length = n.nlmsg_len;
        if (length < nh || length > bytes.size() - offset || n.nlmsg_pid != 0) {
            malformed(sink); return;
        }
        const auto payload = bytes.subspan(offset + nh, length - nh);
        switch (n.nlmsg_type) {
        case NLMSG_NOOP: break;
        case NLMSG_OVERRUN: sink.protocol_diagnostic(Reason::receive_overrun); break;
        case NLMSG_ERROR: {
            if (payload.size() < sizeof(nlmsgerr)) { malformed(sink); return; }
            nlmsgerr err{}; std::memcpy(&err, payload.data(), sizeof(err));
            if (err.error != 0) {
                const auto code = -static_cast<std::int64_t>(err.error);
                sink.protocol_diagnostic(Reason::kernel_error,
                    code > 0 && code <= INT_MAX ? static_cast<int>(code) : EPROTO);
                return; // Do not deliver later data after a fatal kernel error.
            }
            break; // Generic success is NOT a connector subscription ACK.
        }
        case NLMSG_DONE: {
            if (payload.size() < ch) { malformed(sink); return; }
            cn_msg c{}; std::memcpy(&c, payload.data(), ch);
            if (c.id.idx != CN_IDX_PROC || c.id.val != CN_VAL_PROC ||
                c.len != sizeof(proc_event) || c.len != payload.size() - ch) {
                malformed(sink); return;
            }
            // No pointer cast: proc_event may follow a 4-byte-aligned wire header.
            proc_event e{}; std::memcpy(&e, payload.data() + ch, sizeof(e));
            event(c, e, sink);
            break;
        }
        default: malformed(sink); break;
        }
        const auto aligned = (length + 3U) & ~std::size_t{3U};
        if (aligned > bytes.size() - offset) {
            if (length != bytes.size() - offset) malformed(sink);
            return;
        }
        offset += aligned;
    }
}
} // namespace hids::process
