#include "hids/audit/reconstruction.hpp"

#include <algorithm>
#include <limits>
#include <new>
#include <stdexcept>

namespace hids::audit {
Reconstructor::Reconstructor(std::uint64_t boundary, Limits limits)
    : limits_(limits), frontier_(boundary), next_(boundary) {
    if (!limits.record_bytes || !limits.group_bytes || !limits.records_per_group ||
        !limits.open_groups || !limits.total_bytes || !limits.tracked_records ||
        !limits.finalized_groups || !limits.timeout_ms) throw std::invalid_argument("invalid_audit_limits");
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
    // Aliasing pointer: immutable event shares its group's bounded lifetime.
    ready_.emplace_back(group, &group->event);
    return true;
}
FeedResult Reconstructor::feed(std::uint64_t offset, std::string_view line, std::uint64_t now) {
    if (failed()) return FeedResult::failed;
    if (stopped_) { fail("input_after_shutdown"); return FeedResult::failed; }
    if (!tick(now)) return FeedResult::failed;
    if (pause_depth_) { fail("input_while_paused"); return FeedResult::failed; }
    now = active_clock_;
    try {
        if (offset < next_) {
            const auto found = history_.find(offset);
            if (found == history_.end() || line.empty() || line.back() != '\n' ||
                line.size()-1 != found->second->raw.size() ||
                line.substr(0, line.size()-1) != found->second->raw) {
                fail("conflicting_replay"); return FeedResult::failed;
            }
            return FeedResult::duplicate;
        }
        if (offset != next_) { fail("noncontiguous_input"); return FeedResult::failed; }
        // Charge input plus conservative per-record structural overhead. Count
        // limits additionally bound container nodes/control blocks. This is not
        // an allocator/RSS guarantee; output ownership is also caller-managed.
        constexpr std::size_t overhead = 1024;
        if (line.size() > std::numeric_limits<std::size_t>::max()-overhead ||
            line.size()+overhead > limits_.total_bytes-retained_ ||
            history_.size() >= limits_.tracked_records || spans_.size() >= limits_.tracked_records) {
            fail("assembly_capacity"); return FeedResult::failed;
        }
        auto parsed = parse_record(line, offset, limits_.record_bytes, limits_.profile);
        if (!parsed.record) { fail(parsed.error); return FeedResult::failed; }
        auto& record = *parsed.record;
        auto found = groups_.find(record.key);
        if (found != groups_.end() && found->second->finalized) {
            fail("late_record"); return FeedResult::failed;
        }
        if (found == groups_.end()) {
            if (token_ == std::numeric_limits<std::uint64_t>::max()) {
                fail("token_exhaustion"); return FeedResult::failed;
            }
            if (open_ >= limits_.open_groups) { fail("open_group_capacity"); return FeedResult::failed; }
            auto group = std::make_shared<Group>();
            group->event.token = ++token_;
            group->event.key = record.key;
            group->first_seen = now;
            found = groups_.emplace(record.key, group).first;
            tokens_.emplace(group->event.token, group);
            ++open_;
        }
        const auto group = found->second;
        group->last_seen = now;
        if (line.size() > limits_.group_bytes-group->bytes ||
            group->event.records.size() >= limits_.records_per_group) {
            fail("group_capacity"); return FeedResult::failed;
        }
        auto immutable = std::make_shared<const Record>(std::move(record));
        auto& event = group->event;
        if (std::any_of(event.records.begin(), event.records.end(), [&](const auto& previous) {
            return previous->raw == immutable->raw;
        })) ++event.duplicate_content_records; // Distinct positions stay distinct.
        event.records.push_back(immutable);
        history_.emplace(offset, immutable);
        spans_.push_back({immutable->end, event.token});
        retained_ += line.size()+overhead;
        group->bytes += line.size();
        next_ = immutable->end;
        event.syscall_seen |= immutable->type == "SYSCALL";
        event.execve_seen |= immutable->type == "EXECVE";
        event.cwd_seen |= immutable->type == "CWD";
        event.proctitle_seen |= immutable->type == "PROCTITLE";
        event.eoe_seen |= immutable->type == "EOE";
        if (immutable->type == "PATH") ++event.path_records;
        if (event.eoe_seen || ((limits_.profile == RecordProfile::fixture && limits_.proctitle_terminal) && event.proctitle_seen)) {
            if (!finalize(group, event.eoe_seen ? Basis::eoe : Basis::proctitle_terminal)) return FeedResult::failed;
        }
        return FeedResult::accepted;
    } catch (const std::bad_alloc&) {
        fail("allocation_failure"); return FeedResult::failed;
    }
}
bool Reconstructor::expire(std::uint64_t now) {
    if (failed() || stopped_ || !tick(now)) return false;
    now = active_clock_;
    try {
        // First source position, not map key or wall time, defines deterministic
        // order when several deadlines expire in the same caller tick.
        for (const auto& [token, group] : tokens_) {
            (void)token;
            const auto inactivity = limits_.inactivity_timeout_ms ?
                limits_.inactivity_timeout_ms : limits_.timeout_ms;
            if (!group->finalized && (now-group->first_seen >= limits_.timeout_ms ||
                now-group->last_seen >= inactivity)) {
                group->event.timeout = TimeoutEvidence{
                    now-group->first_seen >= limits_.timeout_ms ? "lifetime" : "inactivity",
                    group->first_seen, group->last_seen, now, clock_, clock_-active_clock_,
                    inactivity, limits_.timeout_ms};
                if (!finalize(group, Basis::timeout)) return false;
            }
        }
        return true;
    } catch (const std::bad_alloc&) { return fail("allocation_failure"); }
}
bool Reconstructor::finish() {
    if (failed()) return false;
    if (stopped_) return true;
    try {
        for (const auto& [token, group] : tokens_) {
            (void)token;
            if (!group->finalized && !finalize(group, Basis::shutdown)) return false;
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
    if (pause_depth_ || record.begin != next_ || record.end <= record.begin)
        return fail("invalid_suppressed_position");
    const auto group = groups_.find(record.key);
    if (group != groups_.end() && !group->second->finalized) return fail("unexpected_suppression");
    if (spans_.size() >= limits_.tracked_records) return fail("assembly_capacity");
    try { spans_.push_back({record.end, 0}); }
    catch (const std::bad_alloc&) { return fail("allocation_failure"); }
    next_ = record.end;
    advance();
    return true;
}
void Reconstructor::advance() {
    auto candidate = frontier_;
    for (const auto& span : spans_) {
        if (span.token && !tokens_.at(span.token)->acknowledged) break;
        candidate = span.end;
    }
    // Do not split even an acknowledged event across a replay boundary. Its
    // later records could otherwise reconstruct as an orphan after restart.
    bool changed = true;
    while (changed) {
        changed = false;
        for (const auto& [id, group] : tokens_) {
            (void)id;
            const auto& records = group->event.records;
            if (!records.empty() && records.front()->begin < candidate &&
                records.back()->end > candidate) {
                candidate = records.front()->begin;
                changed = true;
            }
        }
    }
    while (!spans_.empty() && spans_.front().end <= candidate) spans_.pop_front();
    frontier_ = candidate;
    if (!limits_.retain_history) {
        for (auto item = tokens_.begin(); item != tokens_.end();) {
            const auto& group = item->second;
            const auto& records = group->event.records;
            if (!group->acknowledged || records.empty() || records.back()->end > frontier_) {
                ++item;
                continue;
            }
            for (const auto& record : records) {
                retained_ -= record->raw.size()+1+1024;
                history_.erase(record->begin);
            }
            groups_.erase(group->event.key);
            --finalized_;
            item = tokens_.erase(item);
        }
    }
}
} // namespace hids::audit
