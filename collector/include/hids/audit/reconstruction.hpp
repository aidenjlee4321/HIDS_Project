#pragma once

#include <compare>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace hids::audit {
// Internal structural types, NOT the m3.audit-exec JSON contract. Payloads have
// not been semantically validated. No source I/O, clocks, SQL or IPC is performed.
struct Key {
    std::string seconds, fraction, serial;
    auto operator<=>(const Key&) const = default;
};
enum class RecordProfile { fixture, auditd_string };

struct Record {
    Key key;
    std::string type;
    std::string raw; // Sensitive transient native bytes; never log/persist blindly.
    std::uint64_t begin = 0, end = 0;
    RecordProfile profile = RecordProfile::fixture;
};
struct ParseResult {
    std::optional<Record> record;
    std::string_view error; // Static code only, never source content.
};
ParseResult parse_record(std::string_view line, std::uint64_t offset,
                         std::size_t maximum = 65536,
                         RecordProfile profile = RecordProfile::fixture);

enum class Basis { eoe, proctitle_terminal, timeout, shutdown };
struct TimeoutEvidence {
    std::string_view reason;
    std::uint64_t first_active_ms, last_active_ms, observed_active_ms;
    std::uint64_t observed_monotonic_ms, paused_ms, inactivity_limit_ms, lifetime_limit_ms;
};
struct ResourceEvidence {
    std::string_view reason;
    std::uint64_t event_bytes_before, event_records_before;
    std::uint64_t trigger_begin, trigger_end;
    bool incoming_for_event;
    std::uint64_t group_limit, group_record_limit, aggregate_limit;
    std::uint64_t retained_accounted_bytes, retained_records, retained_record_limit;
    std::uint64_t requested_accounted_bytes;
    std::uint64_t observed_active_ms, observed_monotonic_ms, paused_ms;
};
struct Event {
    std::uint64_t token = 0;
    Key key;
    std::vector<std::shared_ptr<const Record>> records;
    Basis basis = Basis::shutdown;
    bool terminal_seen = false; // Structural delimiter, NOT semantic completeness.
    bool syscall_seen = false, execve_seen = false, cwd_seen = false;
    bool proctitle_seen = false, eoe_seen = false;
    std::size_t path_records = 0, duplicate_content_records = 0;
    std::optional<TimeoutEvidence> timeout;
    std::optional<ResourceEvidence> resource;
    std::optional<std::uint64_t> first_observed_unix_ns;
    // SYSCALL classification, field validation and normalized output are deferred
    // to an approved native payload parser. Never infer successful exec here.
};
// Offline EXECVE candidate profile. Empty result means complete arguments only.
std::string_view validate_execve(const Event& event);

struct Limits {
    std::size_t record_bytes = 65536, group_bytes = 262144;
    std::size_t records_per_group = 256, open_groups = 128;
    std::size_t total_bytes = 8*1024*1024, tracked_records = 4096;
    std::size_t finalized_groups = 256;
    std::uint64_t timeout_ms = 2000;
    // Zero follows timeout_ms, preserving the existing provisional durations.
    std::uint64_t inactivity_timeout_ms = 0;
    RecordProfile profile = RecordProfile::fixture;
    bool proctitle_terminal = false; // Explicit fixture/profile opt-in only.
    bool resource_recovery = false; // Requires non-replay mode and a durable incident gate.
    bool retain_history = true; // Offline replay checks; live suppression is Python-owned.
};
enum class FeedResult { accepted, duplicate, failed };

// Single serialized owner and one caller-established stream epoch. Offset zero
// need not be the activation boundary. All intervals are [begin,end).
class Reconstructor {
public:
    using Resource = std::function<bool(const Key&, const ResourceEvidence&)>;
    explicit Reconstructor(std::uint64_t boundary = 0, Limits limits = {}, Resource resource = {});
    FeedResult feed(std::uint64_t offset, std::string_view complete_line,
                    std::uint64_t monotonic_ms, std::optional<std::uint64_t> observed_unix_ns = {});
    bool expire(std::uint64_t monotonic_ms);
    bool pause(std::uint64_t monotonic_ms);
    bool resume(std::uint64_t monotonic_ms);
    bool skip(const Record&, std::uint64_t monotonic_ms); // Durable suppression only.
    bool finish(); // Shutdown-finalize open groups as incomplete, never ACK them.
    std::shared_ptr<const Event> take_ready();
    bool acknowledge(std::uint64_t token); // Trusted caller disposition, NOT commit.
    std::uint64_t volatile_frontier() const { return frontier_; }
    std::uint64_t next_offset() const { return next_; }
    std::size_t retained_bytes() const { return retained_; }
    std::size_t tracked_records() const { return history_.size(); }
    bool failed() const { return !error_.empty(); }
    std::string_view error() const { return error_; }
private:
    struct Group {
        Event event;
        std::size_t bytes = 0;
        std::uint64_t seen_bytes = 0, seen_records = 0, first_offset = 0, last_end = 0;
        std::uint64_t first_seen = 0, last_seen = 0;
        bool finalized = false, acknowledged = false;
    };
    struct Span { std::uint64_t end, token; };
    Limits limits_;
    Resource resource_;
    std::uint64_t frontier_, next_, clock_ = 0, token_ = 0;
    std::uint64_t active_clock_ = 0;
    std::size_t pause_depth_ = 0;
    bool clock_seen_ = false, stopped_ = false;
    std::size_t retained_ = 0, open_ = 0, finalized_ = 0;
    std::string_view error_;
    std::map<Key, std::shared_ptr<Group>> groups_;
    std::map<std::uint64_t, std::shared_ptr<Group>> tokens_;
    std::map<std::uint64_t, std::shared_ptr<const Record>> history_;
    std::deque<Span> spans_;
    std::deque<std::shared_ptr<const Event>> ready_;
    bool fail(std::string_view code);
    bool tick(std::uint64_t now);
    bool finalize(const std::shared_ptr<Group>&, Basis);
    void advance();
    void release_payload(const std::shared_ptr<Group>&);
    void append_span(std::uint64_t end, std::uint64_t token);
    bool pressure(const Record&);
};
} // namespace hids::audit
