#include "hids/process_collector.hpp"
#include <algorithm>
#include <cerrno>
#include <climits>

namespace hids::process {
Collector::~Collector() { stop(); }
void Collector::diagnostic(Reason reason, int error, bool incomplete) noexcept {
    sink_.on_diagnostic({reason, error, {}, {}, {}});
    if (incomplete) {
        status_.incomplete_interval = true;
        if (open_) status_.state = State::degraded;
        sink_.on_status(status_);
    }
}
bool Collector::start() noexcept {
    if (open_) { diagnostic(Reason::duplicate_start); return false; }
    const auto session = status_.session + 1;
    status_ = {}; status_.session = session; status_.state = State::starting;
    sequences_ = {};
    sink_.on_status(status_);
    const auto opened = io_.open();
    if (opened.error != 0) {
        status_.state = State::unavailable;
        diagnostic(Reason::open_failed, opened.error);
        sink_.on_status(status_);
        return false;
    }
    open_ = true; port_ = opened.port;
    cookie_ = static_cast<std::uint32_t>(std::chrono::steady_clock::now().time_since_epoch().count()) ^ port_;
    cookie_ &= 0x7fffffffU;
    listen_attempted_ = true; // Even an interrupted send has uncertain effect.
    const auto request = control_packet(true, port_, cookie_);
    const int error = io_.send(request);
    if (error != 0) { terminate_source(Reason::listen_failed, error); return false; }
    status_.state = State::unconfirmed;
    diagnostic(Reason::listening_unconfirmed);
    sink_.on_status(status_);
    return true;
}
void Collector::stop() noexcept {
    if (!open_) return;
    if (listen_attempted_) {
        listen_attempted_ = false;
        const auto request = control_packet(false, port_, cookie_);
        const int error = io_.send(request);
        if (error != 0) diagnostic(Reason::unsubscribe_failed, error, true);
        // Never wait for IGNORE ACK or retry a control operation.
    }
    const int error = io_.close();
    open_ = false;
    if (error != 0) diagnostic(Reason::close_failed, error, true);
    status_.state = State::stopped;
    sink_.on_status(status_);
}
void Collector::terminate_source(Reason reason, int error) noexcept {
    diagnostic(reason, error, true);
    stop(); // Only this adapter is stopped; caller/other sources remain alive.
    status_.state = State::unavailable;
    sink_.on_status(status_);
}
void Collector::poll_once(std::chrono::milliseconds timeout) noexcept {
    if (!open_) return;
    timeout = std::clamp(timeout, std::chrono::milliseconds{0}, std::chrono::milliseconds{100});
    const auto read = io_.receive(buffer_, timeout);
    switch (read.kind) {
    case ReadKind::timeout: return;
    case ReadKind::interrupted:
        diagnostic(Reason::receive_interrupted, read.error); return;
    case ReadKind::no_buffer:
        diagnostic(Reason::no_buffer, read.error, true); return;
    case ReadKind::truncated:
        diagnostic(Reason::truncated, read.error, true); return;
    case ReadKind::foreign_sender:
        diagnostic(Reason::malformed, read.error, true); return;
    case ReadKind::closed: case ReadKind::error:
        terminate_source(Reason::receive_failed, read.error); return;
    case ReadKind::data:
        if (read.size == 0 || read.size > buffer_.size()) {
            diagnostic(Reason::malformed, 0, true); return;
        }
        decode(std::span<const std::byte>{buffer_.data(), read.size}, *this);
    }
}
void Collector::native_event(const NativeEvent& event) noexcept {
    if (!open_) return; // A preceding error in the datagram may have stopped us.
    if (event.cpu < sequences_.size()) {
        auto& seq = sequences_[event.cpu];
        if (seq.seen && static_cast<std::uint32_t>(event.sequence - seq.last) != 1U) {
            sink_.on_diagnostic({Reason::sequence_discontinuity, 0, event.cpu, seq.last, event.sequence});
            // Filtered sequence positions cannot establish a receive-loss count.
        }
        seq = {true, event.sequence};
    } else sink_.on_diagnostic({Reason::sequence_tracking_unavailable, 0, event.cpu, {}, event.sequence});
    const bool first = !status_.delivery_observed;
    status_.delivery_observed = true;
    status_.state = status_.incomplete_interval ? State::degraded : State::observing;
    if (first) {
        diagnostic(Reason::delivery_observed);
        sink_.on_status(status_);
    }
    sink_.on_event(event);
}
void Collector::acknowledgement(std::uint32_t reply, std::uint32_t error) noexcept {
    if (!open_ || reply != cookie_ + 1U) return;
    if (error != 0) {
        terminate_source(Reason::kernel_error, error <= INT_MAX ? static_cast<int>(error) : EPROTO);
        return;
    }
    if (!status_.subscription_acknowledged) {
        status_.subscription_acknowledged = true;
        if (!status_.delivery_observed && !status_.incomplete_interval)
            status_.state = State::acknowledged;
        diagnostic(Reason::subscription_acknowledged);
        sink_.on_status(status_); // ACK alone never claims event delivery.
    }
}
void Collector::protocol_diagnostic(Reason reason, int error) noexcept {
    if (!open_) return;
    if (reason == Reason::kernel_error) terminate_source(reason, error);
    else diagnostic(reason, error, true);
}
} // namespace hids::process
