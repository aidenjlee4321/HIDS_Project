#include "hids/audit/reconstruction.hpp"

#include <algorithm>
#include <charconv>
#include <limits>
#include <new>

namespace hids::audit {
namespace {
bool decimal(std::string_view s) {
    if (s.empty() || s.size() > 20 || (s.size() > 1 && s.front() == '0')) return false;
    std::uint64_t value = 0;
    const auto [end, error] = std::from_chars(s.data(), s.data()+s.size(), value);
    return error == std::errc{} && end == s.data()+s.size();
}
bool field_name_byte(unsigned char c) {
    return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') ||
           c == '_' || c == '[' || c == ']';
}

bool valid_field(std::string_view token) {
    const auto separator = token.find('=');
    if (separator == token.npos || separator == 0) return false;
    const auto name = token.substr(0, separator);
    if (name.front() < 'a' || name.front() > 'z' ||
        !std::all_of(name.begin(), name.end(), field_name_byte)) return false;

    auto value = token.substr(separator + 1);
    if (value.empty()) return false;
    if (value.front() == '"') {
        if (value.size() < 2 || value.back() != '"') return false;
        value.remove_prefix(1);
        value.remove_suffix(1);
    }
    return std::all_of(value.begin(), value.end(), [](unsigned char c) {
        return c >= 0x21 && c <= 0x7e && c != '"';
    });
}

bool valid_payload(std::string_view payload) {
    // Provisional offline profile: exactly one ASCII space before each field.
    while (!payload.empty()) {
        payload.remove_prefix(1);
        const auto boundary = payload.find(' ');
        if (!valid_field(payload.substr(0, boundary))) return false;
        if (boundary == payload.npos) return true;
        payload.remove_prefix(boundary);
    }
    return false;
}

}
ParseResult parse_record(std::string_view line, std::uint64_t offset, std::size_t maximum,
                         RecordProfile profile) try {
    if (line.empty() || line.back() != '\n') return {{}, "unterminated_record"};
    const auto size = line.size();
    line.remove_suffix(1);
    if (line.size() > maximum) return {{}, "record_capacity"};
    if (size > std::numeric_limits<std::uint64_t>::max()-offset) return {{}, "offset_overflow"};
    if (line.find_first_of("\r\n") != line.npos || line.find('\0') != line.npos) return {{}, "invalid_record_bytes"};
    // Narrow framing profile for local records without a node prefix.
    if (!line.starts_with("type=")) return {{}, "unsupported_header"};
    const auto separator = line.find(' ');
    if (separator == line.npos || separator <= 5 || separator-5 > 64) return {{}, "invalid_type"};
    const auto type = line.substr(5, separator-5);
    if (!std::all_of(type.begin(), type.end(), [](unsigned char c) {
        return (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_';
    })) return {{}, "invalid_type"};
    const auto rest = line.substr(separator+1);
    if (!rest.starts_with("msg=audit(")) return {{}, "missing_audit_identity"};
    const auto close = rest.find("):", 10);
    if (close == rest.npos) return {{}, "invalid_audit_identity"};
    const auto identity = rest.substr(10, close-10);
    const auto dot = identity.find('.'), colon = identity.find(':');
    if (dot == identity.npos || colon == identity.npos || colon <= dot) return {{}, "invalid_audit_identity"};
    const auto seconds = identity.substr(0, dot);
    const auto fraction = identity.substr(dot+1, colon-dot-1);
    const auto serial = identity.substr(colon+1);
    if (!decimal(seconds) || !decimal(serial) || fraction.empty() || fraction.size() > 9 ||
        !std::all_of(fraction.begin(), fraction.end(), [](unsigned char c){return c >= '0' && c <= '9';})) {
        return {{}, "invalid_audit_identity"};
    }
    const auto payload = rest.substr(close+2);
    // The dispatcher appends one ASCII space to a payload-free EOE.
    // Accept only the delimiter observed for the selected source profile.
    const std::string_view eoe_suffix = profile == RecordProfile::auditd_string ? " " : "";
    if (type == "EOE" && payload != eoe_suffix) return {{}, "unexpected_eoe_payload"};
    if (!payload.empty() && payload.front() != ' ') {
        return {{}, "missing_payload"};
    }
    if (type != "EOE" && (payload.size() < 2 || payload.find_first_not_of(' ') == payload.npos)) {
        return {{}, "missing_payload"};
    }
    auto lexical_payload = payload;
    // Native continuation EXECVE records carry a second leading space.
    // Preserve it in the raw record and byte positions.
    if (profile == RecordProfile::auditd_string && type == "EXECVE" &&
        lexical_payload.starts_with("  a")) lexical_payload.remove_prefix(1);
    if (type != "EOE" && !valid_payload(lexical_payload)) return {{}, "invalid_payload_syntax"};
    Record record{{std::string(seconds), std::string(fraction), std::string(serial)},
                  std::string(type), std::string(line), offset, offset+size, profile};
    return {std::move(record), {}};
} catch (const std::bad_alloc&) {
    return {{}, "allocation_failure"};
}
} // namespace hids::audit
