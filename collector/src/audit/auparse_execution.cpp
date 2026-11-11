#include "hids/audit/auparse_execution.hpp"

#include <auparse.h>

#include <algorithm>
#include <memory>
#include <string>
#include <vector>

namespace hids::audit {
namespace {
constexpr std::size_t max_event_bytes = 16 * 1024 * 1024;
constexpr std::size_t max_record_bytes = 65536;

struct InputRecord {
    const Record* record;
    std::size_t fraction;
};
}

ExecutionResult validate_auparse_execution(const Event& event) {
    std::size_t source_bytes = 0;
    std::size_t input_bytes = 0;
    std::vector<InputRecord> inputs;
    if (event.basis != Basis::eoe || !event.eoe_seen || event.records.empty()) {
        return {{}, "auparse_ineligible"};
    }

    if (event.key.seconds.empty() || event.key.seconds.size() > 20 ||
        event.key.serial.empty() || event.key.serial.size() > 20 ||
        event.key.fraction.empty() || event.key.fraction.size() > 9 ||
        !std::all_of(event.key.fraction.begin(), event.key.fraction.end(), [](char c) {
            return c >= '0' && c <= '9';
        })) return {{}, "auparse_identity"};

    const std::string identity =
        " msg=audit(" + event.key.seconds + "." + event.key.fraction + ":" + event.key.serial + "):";

    for (std::size_t i = 0; i < event.records.size(); ++i) {
        const auto& record = event.records[i];
        if (!record || record->raw.size() > max_record_bytes ||
            record->raw.size() + 1 > max_event_bytes - source_bytes ||
            record->raw.find('\0') != std::string::npos ||
            record->raw.find_first_of("\r\n") != std::string::npos ||
            record->key != event.key) return {{}, "auparse_record"};
        source_bytes += record->raw.size() + 1;

        const auto prefix = "type=" + record->type + identity;
        if (!record->raw.starts_with(prefix)) return {{}, "auparse_identity"};
        if (record->type == "EOE") {
            const auto suffix = record->profile == RecordProfile::auditd_string ? " " : "";
            if (i + 1 != event.records.size() || record->raw != prefix + suffix) {
                return {{}, "auparse_unexpected_eoe"};
            }
            continue;
        }
        if (i + 1 == event.records.size()) return {{}, "auparse_missing_eoe"};

        const auto projected = record->raw.size() - event.key.fraction.size() + 4;
        if (projected > max_event_bytes - input_bytes) return {{}, "auparse_capacity"};
        input_bytes += projected;
        inputs.push_back({record.get(), prefix.size() - event.key.fraction.size() - event.key.serial.size() - 3});
    }
    if (inputs.empty()) return {{}, "auparse_empty"};

    std::string fraction = event.key.fraction.substr(0, 3);
    fraction.resize(3, '0');
    std::string buffer;
    buffer.reserve(input_bytes);
    for (const auto& input : inputs) {
        const auto& raw = input.record->raw;
        buffer.append(raw, 0, input.fraction);
        buffer += fraction;
        buffer.append(raw, input.fraction + event.key.fraction.size());
        buffer += '\n';
    }

    std::unique_ptr<auparse_state_t, decltype(&auparse_destroy)> state(
        auparse_init(AUSOURCE_BUFFER, buffer.c_str()), auparse_destroy);
    if (!state) return {{}, "auparse_init"};
    if (auparse_next_event(state.get()) != 1 || auparse_first_record(state.get()) != 1) {
        return {{}, "auparse_missing_event"};
    }

    std::string_view remaining(buffer);
    for (const auto& input : inputs) {
        const auto length = remaining.find('\n');
        const auto expected = remaining.substr(0, length);
        const char* actual = auparse_get_record_text(state.get());
        const char* type = auparse_get_type_name(state.get());
        if (!actual || !type || expected != actual || input.record->type != type) {
            return {{}, "auparse_record_mismatch"};
        }
        if (auparse_first_field(state.get()) != 1) return {{}, "auparse_missing_field"};
        int next;
        do {
            if (!auparse_get_field_name(state.get()) || !auparse_get_field_str(state.get())) {
                return {{}, "auparse_field"};
            }
            next = auparse_next_field(state.get());
        } while (next > 0);
        if (next != 0) return {{}, "auparse_field"};
        remaining.remove_prefix(length + 1);
        if (auparse_next_record(state.get()) != (remaining.empty() ? 0 : 1)) {
            return {{}, "auparse_record_count"};
        }
    }
    if (auparse_next_event(state.get()) != 0) return {{}, "auparse_event_count"};
    return validate_execution(event);
}
}
