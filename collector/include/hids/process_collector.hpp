#pragma once

#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>

namespace hids::process {
// Internal source-native C++ types. NOT ECS, JSON, IPC or a persistent schema.
enum class Lifecycle { forked, executed, exited };
struct Parent { std::int32_t tid; std::int32_t tgid; };
struct NativeEvent {
    Lifecycle kind;
    std::int32_t tid;
    std::int32_t tgid;
    std::optional<Parent> parent;
    std::uint32_t cpu;
    std::uint32_t sequence;
    std::uint64_t kernel_monotonic_ns; // No wall-clock conversion/fallback.
    std::optional<std::uint32_t> native_exit_status; // Raw kernel encoding, not exit(3) code.
    std::optional<std::uint32_t> native_exit_signal;
};
// ACK and delivery are independent facts. acknowledged means ACK before any
// delivery; observing may have no ACK; degraded takes precedence over both.
enum class State { stopped, starting, unconfirmed, acknowledged, observing, degraded, unavailable };
enum class Reason {
    starting, listening_unconfirmed, delivery_observed, subscription_acknowledged,
    open_failed, listen_failed, kernel_error, receive_failed, receive_interrupted,
    receive_overrun, no_buffer, truncated, malformed, unexpected_event,
    sequence_discontinuity, sequence_tracking_unavailable, unsubscribe_failed,
    close_failed, stopped, duplicate_start
};
struct Diagnostic {
    Reason reason;
    int error = 0; // Exact positive errno where one exists; zero means not supplied.
    std::optional<std::uint32_t> cpu;
    std::optional<std::uint32_t> previous_sequence;
    std::optional<std::uint32_t> current_sequence;
};
struct Status {
    State state = State::stopped;
    bool subscription_acknowledged = false;
    bool delivery_observed = false;
    bool incomplete_interval = false; // Persists through a session after known reception failure.
    std::uint64_t session = 0; // Local adapter generation, NOT a global event/boot identity.
};
class Sink {
public:
    virtual ~Sink() = default;
    // Trusted internal consumer; callbacks must not throw, block or reenter adapter.
    virtual void on_event(const NativeEvent&) noexcept = 0;
    virtual void on_diagnostic(const Diagnostic&) noexcept = 0;
    virtual void on_status(const Status&) noexcept = 0;
};

enum class ReadKind { data, timeout, interrupted, no_buffer, truncated, foreign_sender, closed, error };
struct ReadResult { ReadKind kind; std::size_t size = 0; int error = 0; };
struct OpenResult { int error = 0; std::uint32_t port = 0; };
class ConnectorIo {
public:
    virtual ~ConnectorIo() = default;
    virtual OpenResult open() noexcept = 0;
    virtual int send(std::span<const std::byte>) noexcept = 0;
    virtual ReadResult receive(std::span<std::byte>, std::chrono::milliseconds) noexcept = 0;
    virtual int close() noexcept = 0;
};

// Protocol boundary, separated from OS I/O so decoding needs no live subscription.
using ControlPacket = std::array<std::byte, 44>;
ControlPacket control_packet(bool listen, std::uint32_t port, std::uint32_t cookie) noexcept;
class DecodeSink {
public:
    virtual ~DecodeSink() = default;
    virtual void native_event(const NativeEvent&) noexcept = 0;
    virtual void acknowledgement(std::uint32_t cookie_reply, std::uint32_t error) noexcept = 0;
    virtual void protocol_diagnostic(Reason, int error = 0) noexcept = 0;
};
void decode(std::span<const std::byte>, DecodeSink&) noexcept;

// Caller owns scheduling/cancellation. All operations (including destruction)
// require one serialized owner thread; no signal-handler calls or auto reconnect.
class Collector final : private DecodeSink {
public:
    Collector(ConnectorIo& io, Sink& sink) noexcept : io_(io), sink_(sink) {}
    ~Collector();
    Collector(const Collector&) = delete;
    Collector& operator=(const Collector&) = delete;
    bool start() noexcept; // True = LISTEN sent, not formally acknowledged.
    void poll_once(std::chrono::milliseconds timeout = std::chrono::milliseconds{0}) noexcept;
    void stop() noexcept; // Idempotent; one IGNORE attempt before close.
    const Status& status() const noexcept { return status_; }
private:
    void native_event(const NativeEvent&) noexcept override;
    void acknowledgement(std::uint32_t, std::uint32_t) noexcept override;
    void protocol_diagnostic(Reason, int) noexcept override;
    void diagnostic(Reason, int error = 0, bool incomplete = false) noexcept;
    void terminate_source(Reason, int) noexcept;
    ConnectorIo& io_;
    Sink& sink_;
    Status status_{};
    bool open_ = false, listen_attempted_ = false;
    std::uint32_t port_ = 0, cookie_ = 0;
    struct Sequence { bool seen = false; std::uint32_t last = 0; };
    std::array<Sequence, 4096> sequences_{};
    std::array<std::byte, 16384> buffer_{}; // Bounded; no internal event queues.
};
} // namespace hids::process
