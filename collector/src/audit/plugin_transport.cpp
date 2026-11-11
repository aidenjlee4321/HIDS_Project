#include "hids/audit/plugin_transport.hpp"
#include "hids/journal/transport.hpp"
#include <chrono>

namespace hids::audit {
namespace {
using journal::Json;

std::string identity(const Key& key) {
    return key.seconds + "." + key.fraction + ":" + key.serial;
}

bool exchange(pilot::Channel& channel, const PluginScope& scope,
              Json request, std::string_view expected, bool* suppressed = nullptr) {
    request["version"] = 3;
    request["activation"] = scope.activation;
    request["generation"] = scope.generation;
    request["lease"] = scope.lease;
    try {
        const auto reply = journal::request(channel, request,
            channel.now() + std::chrono::seconds(2), 256);
        if (reply.is_object() && reply.size() == 2 && reply.contains("version") &&
            reply["version"].is_number_integer() && reply["version"] == 3 &&
            reply.contains("status")) {
            if (reply["status"] == expected) return true;
            if (suppressed && reply["status"] == "suppressed") {
                *suppressed = true;
                return true;
            }
        }
    } catch (const std::exception&) {
        // An unconfirmed request ends this stream. Never reconnect and replay it here.
    }
    channel.close();
    return false;
}

Json execution_payload(const Execution& x) {
    return {
        {"syscall", x.syscall}, {"pid", x.pid}, {"ppid", x.ppid},
        {"uid", x.uid}, {"euid", x.euid}, {"suid", x.suid}, {"fsuid", x.fsuid},
        {"auid", x.auid ? Json(*x.auid) : Json(nullptr)},
        {"session", x.session ? Json(*x.session) : Json(nullptr)},
        {"result", x.result}, {"success", x.success},
        {"exe_base64", x.exe_base64}, {"comm_base64", x.comm_base64},
        {"path_count", x.path_count}, {"cwd_present", x.cwd_present},
        {"proctitle_present", x.proctitle_present},
    };
}
}

bool report_plugin_gap(pilot::Channel& channel, const PluginScope& scope, std::string_view code) {
    const bool confirmed = exchange(channel, scope,
        {{"op", "gap"}, {"code", std::string(code)}}, "interrupted");
    channel.close();
    return confirmed;
}

PluginSession make_plugin_session(pilot::Channel& channel, PluginScope scope,
                                  PluginSession::Validate validate, PluginSession::Clock clock, PluginSession::WallClock wall_clock) {
    if (!wall_clock) wall_clock = []() -> std::optional<std::uint64_t> {
        const auto count = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
        if (count < 0) return {};
        return static_cast<std::uint64_t>(count);
    };
    return PluginSession(
        [&channel, scope](const Record& record) {
            bool suppressed = false;
            const bool confirmed = exchange(channel, scope,
                {{"op", "register"}, {"identity", identity(record.key)},
                 {"begin", record.begin}, {"end", record.end}, {"eoe", record.type == "EOE"}},
                "admit", &suppressed);
            return PluginSession::Admission(!confirmed ? PluginSession::Admission::failed :
                suppressed ? PluginSession::Admission::suppressed : PluginSession::Admission::admitted);
        },
        [&channel, scope](const Event& event, const ExecutionResult& result) {
            if (!result.execution) {
                return exchange(channel, scope,
                    {{"op", "reject"}, {"identity", identity(event.key)},
                     {"reason", event.resource ? "resource_limit" : result.error.empty() ? "unspecified" : std::string(result.error)}}, "rejected");
            }
            Json request{{"op", "accept"}, {"identity", identity(event.key)},
                         {"execution", execution_payload(*result.execution)}};
            if (event.first_observed_unix_ns) request["observation"] = {
                {"version", 1}, {"arch", result.execution->arch},
                {"profile", "linux.audit.aarch64.string/1"},
                {"first_observed_unix_ns", *event.first_observed_unix_ns}};
            return exchange(channel, scope, std::move(request), "accepted");
        },
        std::move(validate), std::move(clock),
        [&channel, scope](const Event& event) {
            if (!event.timeout) return false;
            const auto& t = *event.timeout;
            return exchange(channel, scope,
                {{"op", "timeout"}, {"identity", identity(event.key)}, {"evidence", {
                    {"policy", 1}, {"reason", std::string(t.reason)},
                    {"first_active_ms", t.first_active_ms}, {"last_active_ms", t.last_active_ms},
                    {"observed_active_ms", t.observed_active_ms},
                    {"observed_monotonic_ms", t.observed_monotonic_ms}, {"paused_ms", t.paused_ms},
                    {"inactivity_limit_ms", t.inactivity_limit_ms}, {"lifetime_limit_ms", t.lifetime_limit_ms}
                }}}, "timed_out");
        },
        [&channel, scope](const Key& key, const ResourceEvidence& e) {
            return exchange(channel, scope,
                {{"op", "resource"}, {"identity", identity(key)}, {"evidence", {
                    {"policy", 1}, {"reason", std::string(e.reason)},
                    {"event_bytes_before", e.event_bytes_before}, {"event_records_before", e.event_records_before},
                    {"trigger_begin", e.trigger_begin}, {"trigger_end", e.trigger_end}, {"incoming_for_event", e.incoming_for_event},
                    {"group_limit", e.group_limit}, {"group_record_limit", e.group_record_limit}, {"aggregate_limit", e.aggregate_limit},
                    {"retained_accounted_bytes", e.retained_accounted_bytes}, {"retained_records", e.retained_records},
                    {"retained_record_limit", e.retained_record_limit}, {"requested_accounted_bytes", e.requested_accounted_bytes},
                    {"observed_active_ms", e.observed_active_ms}, {"observed_monotonic_ms", e.observed_monotonic_ms},
                    {"paused_ms", e.paused_ms}
                }}}, "resource_recorded");
        }, {}, std::move(wall_clock));
}
}
