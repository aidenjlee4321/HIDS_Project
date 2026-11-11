#include "hids/audit/reconstruction.hpp"

#include <algorithm>
#include <limits>
#include <new>
#include <stdexcept>
#include <utility>

namespace hids::audit {
namespace {
constexpr std::size_t record_overhead = 1024;
constexpr std::size_t group_reserve = 2048;
constexpr std::size_t span_reserve = 64;
}
Reconstructor::Reconstructor(std::uint64_t boundary, Limits limits, Resource resource)
    : limits_(limits), resource_(std::move(resource)), frontier_(boundary), next_(boundary) {
    if (!limits.record_bytes || !limits.group_bytes || !limits.records_per_group ||
        !limits.open_groups || !limits.total_bytes || !limits.tracked_records ||
        !limits.finalized_groups || !limits.timeout_ms) throw std::invalid_argument("invalid_audit_limits");
    if (limits_.resource_recovery) {
        const auto maximum = std::numeric_limits<std::size_t>::max();
        if (limits_.retain_history || limits_.group_bytes > 16*1024*1024 || limits_.total_bytes > 32*1024*1024 ||
            limits_.group_bytes > limits_.total_bytes || limits_.open_groups > maximum-limits_.finalized_groups ||
            limits_.open_groups+limits_.finalized_groups > maximum/group_reserve ||
            limits_.tracked_records > maximum/span_reserve) throw std::invalid_argument("invalid_resource_limits");
        const auto groups = (limits_.open_groups+limits_.finalized_groups)*group_reserve;
        const auto spans = limits_.tracked_records*span_reserve;
        if (groups > maximum-spans || groups+spans >= limits_.total_bytes)
            throw std::invalid_argument("metadata_reserve_exhausts_assembly");
        // Reserve bounded group/suppression and range bookkeeping up front. The
        // per-record charge additionally covers retained record/container overhead.
        retained_ = groups+spans;
    }
}
bool Reconstructor::fail(std::string_view code) {
    if (error_.empty()) error_ = code;
    return false;
}
bool Reconstructor::tick(std::uint64_t now) {
    if (clock_seen_ && now < clock_) return fail("monotonic_clock_reversed");
    if (!clock_seen_) active_clock_ = now;
    else if (!pause_depth_) active_clock_ += now-clock_;
    clock_ = now;
    clock_seen_ = true;
    return true;
}
bool Reconstructor::pause(std::uint64_t now) {
    if (failed() || stopped_ || !tick(now)) return false;
    if (pause_depth_ == std::numeric_limits<std::size_t>::max()) return fail("pause_capacity");
    ++pause_depth_;
    return true;
}
bool Reconstructor::resume(std::uint64_t now) {
    if (failed() || stopped_ || !tick(now)) return false;
    if (!pause_depth_) return fail("pause_not_active");
    --pause_depth_;
    return true;
}
bool Reconstructor::finalize(const std::shared_ptr<Group>& group, Basis basis) {
    if (group->finalized) return fail("already_finalized");
    if (finalized_ >= limits_.finalized_groups) return fail("finalized_history_capacity");
    group->event.basis = basis;
    group->event.terminal_seen = basis == Basis::eoe || basis == Basis::proctitle_terminal;
    group->finalized = true;
    --open_;
    ++finalized_;
    ready_.emplace_back(group, &group->event);
    return true;
}
void Reconstructor::release_payload(const std::shared_ptr<Group>& group) {
    for (const auto& record : group->event.records) {
        retained_ -= record->raw.size()+1+record_overhead;
        history_.erase(record->begin);
    }
    if (!group->finalized) decltype(group->event.records){}.swap(group->event.records);
    group->bytes = 0;
}
void Reconstructor::append_span(std::uint64_t end, std::uint64_t token) {
    if (!limits_.retain_history && !spans_.empty() && spans_.back().token == token)
        spans_.back().end = end;
    else spans_.push_back({end, token});
}
bool Reconstructor::pressure(const Record& record) {
    const auto incoming = record.end-record.begin;
    if (incoming > std::numeric_limits<std::size_t>::max()-record_overhead) return fail("assembly_capacity");
    const auto requested = static_cast<std::size_t>(incoming)+record_overhead;
    const auto current = groups_.at(record.key);
    while (!current->event.resource) {
        std::string_view reason;
        auto victim = current;
        if (incoming > limits_.group_bytes-current->bytes) reason = "event_bytes";
        else if (current->seen_records >= limits_.records_per_group) reason = "event_records";
        else if (requested > limits_.total_bytes-retained_ || history_.size() >= limits_.tracked_records) {
            reason = requested > limits_.total_bytes-retained_ ? "aggregate_bytes" : "aggregate_records";
            victim.reset();
            // The live session has drained and durably ACKed all complete work.
            // Remaining payload holders require unread input/EOE, so waiting with
            // frozen clocks cannot free them. Reject the earliest such blocker.
            for (const auto& [token, candidate] : tokens_) {
                (void)token;
                if (!candidate->finalized && !candidate->event.resource && !candidate->event.records.empty()) {
                    victim = candidate; break;
                }
            }
            if (!victim) victim = current; // Discard the pending input if only metadata remains.
        } else return true;
        const ResourceEvidence evidence{
            reason, victim->seen_bytes, victim->seen_records,
            record.begin, record.end, victim == current,
            limits_.group_bytes, limits_.records_per_group, limits_.total_bytes,
            retained_, history_.size(), limits_.tracked_records, requested,
            active_clock_, clock_, clock_-active_clock_};
        if (!resource_ || !resource_(victim->event.key, evidence)) return fail("resource_report_unconfirmed");
        // The callback must commit the cause before memory is released. No
        // successful disposition is invented here; EOE/timeout resolves it later.
        victim->event.resource = evidence;
        release_payload(victim);
    }
    return true;
}
FeedResult Reconstructor::feed(std::uint64_t offset, std::string_view line, std::uint64_t now) {
    if (failed()) return FeedResult::failed;
    if (stopped_) { fail("input_after_shutdown"); return FeedResult::failed; }
    if (!tick(now)) return FeedResult::failed;
    if (pause_depth_) { fail("input_while_paused"); return FeedResult::failed; }
    try {
        if (offset < next_) {
            const auto found = history_.find(offset);
            if (found == history_.end() || line.empty() || line.back() != '\n' ||
                line.size()-1 != found->second->raw.size() || line.substr(0,line.size()-1) != found->second->raw) {
                fail("conflicting_replay"); return FeedResult::failed;
            }
            return FeedResult::duplicate;
        }
        if (offset != next_) { fail("noncontiguous_input"); return FeedResult::failed; }
        if (!limits_.resource_recovery &&
            (line.size() > std::numeric_limits<std::size_t>::max()-record_overhead ||
             line.size()+record_overhead > limits_.total_bytes-retained_ || history_.size() >= limits_.tracked_records)) {
            fail("assembly_capacity"); return FeedResult::failed;
        }
        auto parsed = parse_record(line, offset, limits_.record_bytes, limits_.profile);
        if (!parsed.record) { fail(parsed.error); return FeedResult::failed; }
        auto& record = *parsed.record;
        auto found = groups_.find(record.key);
        if (found != groups_.end() && found->second->finalized) { fail("late_record"); return FeedResult::failed; }
        if (found == groups_.end()) {
            if (token_ == std::numeric_limits<std::uint64_t>::max()) { fail("token_exhaustion"); return FeedResult::failed; }
            if (open_ >= limits_.open_groups) { fail("open_group_capacity"); return FeedResult::failed; }
            auto group = std::make_shared<Group>();
            group->event.token = ++token_;
            group->event.key = record.key;
            group->first_seen = active_clock_;
            group->first_offset = record.begin;
            found = groups_.emplace(record.key,group).first;
            tokens_.emplace(group->event.token,group);
            ++open_;
        }
        const auto group = found->second;
        const bool needs_span = limits_.retain_history || spans_.empty() || spans_.back().token != group->event.token;
        if (needs_span && spans_.size() >= limits_.tracked_records) { fail("assembly_metadata_capacity"); return FeedResult::failed; }
        if (limits_.resource_recovery) {
            if (!pressure(record)) return FeedResult::failed;
        } else if (line.size() > limits_.group_bytes-group->bytes || group->event.records.size() >= limits_.records_per_group) {
            fail("group_capacity"); return FeedResult::failed;
        }
        if (group->seen_bytes > std::numeric_limits<std::uint64_t>::max()-line.size() ||
            group->seen_records == std::numeric_limits<std::uint64_t>::max()) {
            fail("record_counter_overflow"); return FeedResult::failed;
        }
        group->seen_bytes += line.size();
        ++group->seen_records;
        group->last_seen = active_clock_;
        group->last_end = record.end;
        auto& event = group->event;
        event.syscall_seen |= record.type == "SYSCALL";
        event.execve_seen |= record.type == "EXECVE";
        event.cwd_seen |= record.type == "CWD";
        event.proctitle_seen |= record.type == "PROCTITLE";
        event.eoe_seen |= record.type == "EOE";
        if (record.type == "PATH") ++event.path_records;
        const auto end = record.end;
        if (!event.resource) {
            auto immutable = std::make_shared<const Record>(std::move(record));
            if (std::any_of(event.records.begin(),event.records.end(),[&](const auto& previous) { return previous->raw == immutable->raw; }))
                ++event.duplicate_content_records;
            event.records.push_back(immutable);
            history_.emplace(offset,immutable);
            retained_ += line.size()+record_overhead;
            group->bytes += line.size();
        }
        append_span(end,event.token);
        next_ = end;
        if (event.eoe_seen || (limits_.profile == RecordProfile::fixture && limits_.proctitle_terminal && event.proctitle_seen)) {
            if (!finalize(group,event.eoe_seen ? Basis::eoe : Basis::proctitle_terminal)) return FeedResult::failed;
        }
        return FeedResult::accepted;
    } catch (const std::bad_alloc&) { fail("allocation_failure"); return FeedResult::failed; }
}
bool Reconstructor::expire(std::uint64_t now) {
    if (failed() || stopped_ || !tick(now)) return false;
    try {
        for (const auto& [token,group] : tokens_) {
            (void)token;
            const auto inactivity = limits_.inactivity_timeout_ms ? limits_.inactivity_timeout_ms : limits_.timeout_ms;
            if (!group->finalized && (active_clock_-group->first_seen >= limits_.timeout_ms || active_clock_-group->last_seen >= inactivity)) {
                group->event.timeout = TimeoutEvidence{
                    active_clock_-group->first_seen >= limits_.timeout_ms ? "lifetime" : "inactivity",
                    group->first_seen,group->last_seen,active_clock_,clock_,clock_-active_clock_,inactivity,limits_.timeout_ms};
                if (!finalize(group,Basis::timeout)) return false;
            }
        }
        return true;
    } catch (const std::bad_alloc&) { return fail("allocation_failure"); }
}
bool Reconstructor::finish() {
    if (failed()) return false;
    if (stopped_) return true;
    try {
        for (const auto& [token,group] : tokens_) {
            (void)token;
            if (!group->finalized && !finalize(group,Basis::shutdown)) return false;
        }
        stopped_ = true;
        return true;
    } catch (const std::bad_alloc&) { return fail("allocation_failure"); }
}
std::shared_ptr<const Event> Reconstructor::take_ready() {
    if (ready_.empty()) return {};
    auto result = ready_.front(); ready_.pop_front(); return result;
}
bool Reconstructor::acknowledge(std::uint64_t token) {
    if (failed()) return false;
    const auto found = tokens_.find(token);
    if (found == tokens_.end() || !found->second->finalized) return false;
    found->second->acknowledged = true;
    advance();
    return true;
}
bool Reconstructor::skip(const Record& record, std::uint64_t now) {
    if (failed() || stopped_ || !tick(now)) return false;
    if (pause_depth_ || record.begin != next_ || record.end <= record.begin) return fail("invalid_suppressed_position");
    const auto group = groups_.find(record.key);
    if (group != groups_.end() && !group->second->finalized) return fail("unexpected_suppression");
    const bool needs_span = limits_.retain_history || spans_.empty() || spans_.back().token != 0;
    if (needs_span && spans_.size() >= limits_.tracked_records) return fail("assembly_metadata_capacity");
    try { append_span(record.end,0); }
    catch (const std::bad_alloc&) { return fail("allocation_failure"); }
    next_ = record.end;
    advance();
    return true;
}
void Reconstructor::advance() {
    if (!limits_.retain_history) {
        // Durable Python state is authoritative for this non-replay stream.
        // Completed B can release payload even while open A blocks the frontier.
        for (auto item = tokens_.begin(); item != tokens_.end();) {
            const auto& group = item->second;
            if (!group->acknowledged) { ++item; continue; }
            for (auto& span : spans_) if (span.token == item->first) span.token = 0;
            release_payload(group);
            groups_.erase(group->event.key);
            --finalized_;
            item = tokens_.erase(item);
        }
        std::size_t output = 0;
        for (std::size_t i=0; i<spans_.size(); ++i) {
            if (output && spans_[output-1].token == spans_[i].token) spans_[output-1].end = spans_[i].end;
            else spans_[output++] = spans_[i];
        }
        while (spans_.size() > output) spans_.pop_back();
        while (!spans_.empty() && spans_.front().token == 0) {
            frontier_ = spans_.front().end;
            spans_.pop_front();
        }
        return;
    }
    auto candidate = frontier_;
    for (const auto& span : spans_) {
        if (span.token && !tokens_.at(span.token)->acknowledged) break;
        candidate = span.end;
    }
    bool changed = true;
    while (changed) {
        changed = false;
        for (const auto& [id,group] : tokens_) {
            (void)id;
            if (group->first_offset < candidate && group->last_end > candidate) {
                candidate = group->first_offset; changed = true;
            }
        }
    }
    while (!spans_.empty() && spans_.front().end <= candidate) spans_.pop_front();
    frontier_ = candidate;
}
} // namespace hids::audit
