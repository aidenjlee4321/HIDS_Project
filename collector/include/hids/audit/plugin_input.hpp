#pragma once

#include <cstddef>
#include <string>
#include <string_view>

namespace hids::audit {
// Framing for auditd format=string. The caller owns stream lifecycle and admission.
class PluginInput {
public:
    enum class Result { partial, record, invalid };

    Result consume(std::string_view& chunk);
    std::string_view record() const { return ready_ ? line_ : std::string_view{}; }
    bool complete() const { return !failed_ && (ready_ || line_.empty()); }

private:
    static constexpr std::size_t max_record_bytes = 65536;
    std::string line_;
    bool ready_ = false;
    bool failed_ = false;
};
}
