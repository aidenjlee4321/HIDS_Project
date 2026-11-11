#include "hids/audit/plugin_input.hpp"

namespace hids::audit {
PluginInput::Result PluginInput::consume(std::string_view& chunk) {
    if (failed_) return Result::invalid;
    if (ready_) {
        line_.clear();
        ready_ = false;
    }

    const auto delimiter = chunk.find('\n');
    const auto body = chunk.substr(0, delimiter);
    if (body.size() > max_record_bytes - line_.size() ||
        body.find('\0') != body.npos || body.find('\r') != body.npos ||
        (delimiter != chunk.npos && body.empty() && line_.empty())) {
        line_.clear();
        failed_ = true;
        return Result::invalid;
    }

    const auto count = body.size() + (delimiter == chunk.npos ? 0 : 1);
    if (count) line_.append(chunk.substr(0, count));
    chunk.remove_prefix(count);
    ready_ = delimiter != chunk.npos;
    return ready_ ? Result::record : Result::partial;
}
}
