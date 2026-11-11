#pragma once

#include "hids/audit/execution.hpp"
#include "hids/audit/plugin_input.hpp"

#include <functional>

namespace hids::audit {
// The caller owns activation, peer authentication and transport deadlines.
class PluginSession {
public:
    struct Admission {
        enum State { failed, admitted, suppressed } state;
        Admission(bool okay) : state(okay ? admitted : failed) {}
        Admission(State value) : state(value) {}
    };
    using Register = std::function<Admission(const Record&)>;
    using Finalize = std::function<bool(const Event&, const ExecutionResult&)>;
    using Validate = std::function<ExecutionResult(const Event&)>;
    using Clock = std::function<std::uint64_t()>;
    using Timeout = std::function<bool(const Event&)>;
    using Resource = Reconstructor::Resource;
    using WallClock = std::function<std::optional<std::uint64_t>()>;

    PluginSession(Register admit, Finalize finalize, Validate validate, Clock clock = {}, Timeout timeout = {},
                  Resource resource = {}, std::optional<Limits> limits = {}, WallClock wall_clock = {});
    PluginSession(const PluginSession&) = delete;
    PluginSession(PluginSession&&) = delete;
    bool consume(std::string_view chunk, std::uint64_t monotonic_ms);
    bool tick(std::uint64_t monotonic_ms);
    bool finish();
    std::string_view error() const noexcept { return error_; }

private:
    PluginInput input_;
    Reconstructor reader_;
    Register admit_;
    Finalize finalize_;
    Validate validate_;
    Clock clock_;
    WallClock wall_clock_;
    Timeout timeout_;
    Resource resource_;
    std::string_view error_;
    bool stopped_ = false;
    bool pause();
    bool resume();
    bool drain_ready();
};
}
