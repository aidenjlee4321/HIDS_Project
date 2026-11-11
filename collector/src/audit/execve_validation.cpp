#include "hids/audit/reconstruction.hpp"

#include <algorithm>
#include <charconv>

namespace hids::audit {
namespace {
bool number(std::string_view text, std::size_t& value) {
    if (text.empty() || (text.size() > 1 && text.front() == '0')) return false;
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), value);
    return error == std::errc{} && end == text.data() + text.size();
}

// The RAW fragment length counts quoted content bytes or hex digits.
std::optional<std::size_t> logged_length(std::string_view value) {
    if (value.size() >= 2 && value.front() == '"' && value.back() == '"') {
        value.remove_prefix(1);
        value.remove_suffix(1);
        if (std::all_of(value.begin(), value.end(), [](unsigned char c) {
                return c >= 0x21 && c <= 0x7e && c != '"';
            })) return value.size();
        return {};
    }
    if (value.empty() || value.size() % 2 != 0 ||
        !std::all_of(value.begin(), value.end(), [](unsigned char c) {
            return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F');
        })) return {};
    return value.size();
}
}

std::string_view validate_execve(const Event& event) {
    if (event.basis != Basis::eoe || !event.eoe_seen) return "execve_unclosed_event";

    std::optional<std::size_t> argc;
    std::optional<std::size_t> remaining;
    std::size_t argument = 0;
    std::size_t fragment = 0;
    bool quoted_fragments = false;

    for (const auto& record : event.records) {
        if (record->type != "EXECVE") continue;
        const auto boundary = record->raw.find("): ");
        if (boundary == std::string::npos) return "execve_invalid_record";
        std::string_view fields(record->raw);
        fields.remove_prefix(boundary + 3);
        if (record->profile == RecordProfile::auditd_string && fields.starts_with(" a")) {
            fields.remove_prefix(1);
        }

        while (!fields.empty()) {
            const auto space = fields.find(' ');
            const auto field = fields.substr(0, space);
            fields.remove_prefix(space == fields.npos ? fields.size() : space + 1);
            const auto equals = field.find('=');
            if (equals == field.npos) return "execve_invalid_field";
            auto name = field.substr(0, equals);
            const auto value = field.substr(equals + 1);

            if (!argc) {
                std::size_t count;
                if (name != "argc" || !number(value, count)) return "execve_invalid_argc";
                argc = count;
                continue;
            }

            if (!name.starts_with('a') || argument >= *argc) return "execve_unexpected_field";
            name.remove_prefix(1);
            const auto suffix = name.find_first_of("_[");
            std::size_t index;
            if (!number(name.substr(0, suffix), index) || index != argument) {
                return "execve_argument_order";
            }

            if (suffix == name.npos) {
                if (remaining || !logged_length(value)) return "execve_invalid_argument";
                ++argument;
                continue;
            }

            name.remove_prefix(suffix);
            if (name == "_len") {
                std::size_t length;
                if (remaining || !number(value, length) || length == 0) return "execve_invalid_length";
                remaining = length;
                fragment = 0;
                continue;
            }

            std::size_t part;
            const auto size = logged_length(value);
            const bool quoted = value.starts_with('"');
            if (!remaining || !name.starts_with('[') || !name.ends_with(']') ||
                !number(name.substr(1, name.size() - 2), part) || part != fragment ||
                !size || *size == 0 || *size > *remaining ||
                (fragment != 0 && quoted != quoted_fragments)) return "execve_invalid_fragment";

            quoted_fragments = quoted;
            *remaining -= *size;
            ++fragment;
            if (*remaining == 0) {
                remaining.reset();
                ++argument;
            }
        }
    }
    if (!argc) return "execve_missing_argc";
    if (remaining || argument != *argc) return "execve_incomplete";
    return {};
}
} // namespace hids::audit
