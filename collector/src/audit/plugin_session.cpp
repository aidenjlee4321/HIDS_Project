#include "hids/audit/plugin_session.hpp"

#include <utility>

namespace hids::audit {
namespace {
Limits plugin_limits() {
    Limits limits;
    limits.profile = RecordProfile::auditd_string;
    // Preserve the existing provisional live duration. The observed Audit
    // reload queue defect is not fixed by increasing this deadline. Inactivity
    // currently follows this same ceiling; the clocks remain independently tunable.
    limits.timeout_ms = 10000;
    limits.group_bytes = 16*1024*1024;
    limits.total_bytes = 32*1024*1024;
    limits.records_per_group = 4096;
    limits.resource_recovery = true;
    limits.retain_history = false;
    return limits;
}
}

PluginSession::PluginSession(Register admit, Finalize finalize, Validate validate, Clock clock, Timeout timeout,
                             Resource resource, std::optional<Limits> limits)
    : reader_(0, limits ? *limits : plugin_limits(), [this](const Key& key, const ResourceEvidence& evidence) {
          if (!resource_ || !pause()) return false;
          const bool confirmed = resource_(key, evidence);
          return resume() && confirmed;
      }), admit_(std::move(admit)),
      finalize_(std::move(finalize)), validate_(std::move(validate)), clock_(std::move(clock)),
      timeout_(std::move(timeout)), resource_(std::move(resource)) {}

bool PluginSession::pause() { return !clock_ || reader_.pause(clock_()); }
bool PluginSession::resume() { return !clock_ || reader_.resume(clock_()); }

bool PluginSession::consume(std::string_view chunk, std::uint64_t monotonic_ms) {
    if (!tick(monotonic_ms)) return false;
    while (!chunk.empty()) {
        const auto status = input_.consume(chunk);
        if (status == PluginInput::Result::partial) return true;
        if (status == PluginInput::Result::invalid) {
            error_ = "plugin_input";
            stopped_ = true;
            return false;
        }
        const auto raw = input_.record();
        const auto offset = reader_.next_offset();
        const auto parsed = parse_record(raw, offset, 65536, RecordProfile::auditd_string);
        if (!parsed.record) error_ = parsed.error;
        else {
            // Both monotonic deadlines freeze while admission deliberately stops
            // source reads. Use a fresh clock after the bounded storage wait.
            if (!pause()) error_ = reader_.error();
            else {
                const auto admission = admit_(*parsed.record);
                if (!resume()) error_ = reader_.error();
                else if (admission.state == Admission::failed) error_ = "admission_unconfirmed";
                else if (admission.state == Admission::suppressed) {
                    if (!reader_.skip(*parsed.record, clock_ ? clock_() : monotonic_ms)) error_ = reader_.error();
                } else if (reader_.feed(offset, raw, clock_ ? clock_() : monotonic_ms) != FeedResult::accepted)
                    error_ = reader_.error();
            }
        }
        if (!error_.empty()) {
            stopped_ = true;
            return false;
        }
        if (!drain_ready()) return false;
    }
    return true;
}
bool PluginSession::drain_ready() {
    while (const auto event = reader_.take_ready()) {
        const bool timed = event->basis == Basis::timeout;
        if (timed && !timeout_) { error_ = "assembly_timeout"; stopped_ = true; return false; }
        const auto result = timed || event->resource ? ExecutionResult{} : validate_(*event);
        if ((!timed && event->basis != Basis::eoe) || !pause()) {
            error_ = "finalization_unconfirmed"; stopped_ = true; return false;
        }
        const bool finalized = timed ? timeout_(*event) : finalize_(*event, result);
        if (!resume() || !finalized || !reader_.acknowledge(event->token)) {
            error_ = "finalization_unconfirmed"; stopped_ = true; return false;
        }
    }
    return true;
}

bool PluginSession::tick(std::uint64_t monotonic_ms) {
    if (stopped_) return false;
    if (!reader_.expire(clock_ ? clock_() : monotonic_ms)) error_ = reader_.error();
    if (error_.empty()) return drain_ready();
    stopped_ = true;
    return false;
}

bool PluginSession::finish() {
    if (stopped_) return false;
    stopped_ = true;
    // Shutdown can expose incomplete groups. They belong to stream recovery.
    return input_.complete() && reader_.finish() && !reader_.take_ready();
}
}
