#include "hids/audit/plugin_transport.hpp"
#include "hids/journal/transport.hpp"

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
                                  PluginSession::Validate validate, PluginSession::Clock clock) {
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
                    {{"op", "reject"}, {"identity", identity(event.key)}}, "rejected");
            }
            return exchange(channel, scope,
                {{"op", "accept"}, {"identity", identity(event.key)},
                 {"execution", execution_payload(*result.execution)}}, "accepted");
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
        });
}
}
