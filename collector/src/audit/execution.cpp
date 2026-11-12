#include "hids/audit/execution.hpp"

#include <algorithm>
#include <new>
#include <array>
#include <charconv>
#include <limits>

namespace hids::audit {
namespace {
using Fields = std::map<std::string_view, std::string_view>;

std::optional<Fields> fields(const Record& record) {
    const auto boundary = record.raw.find("): ");
    if (boundary == std::string::npos) return {};
    auto rest = std::string_view(record.raw).substr(boundary + 3);
    Fields result;
    while (!rest.empty()) {
        const auto end = rest.find(' ');
        const auto field = rest.substr(0, end);
        const auto equals = field.find('=');
        if (equals == field.npos ||
            !result.emplace(field.substr(0, equals), field.substr(equals + 1)).second) return {};
        rest.remove_prefix(end == rest.npos ? rest.size() : end + 1);
    }
    return result;
}

template<typename T>
bool number(std::string_view value, T& output, int base = 10) {
    if (value.empty()) return false;
    const auto [end, error] = std::from_chars(value.data(), value.data() + value.size(), output, base);
    return error == std::errc{} && end == value.data() + value.size();
}

int hex_digit(char digit) {
    constexpr std::string_view digits = "0123456789ABCDEF";
    const auto position = digits.find(digit);
    return position == digits.npos ? -1 : static_cast<int>(position);
}

std::optional<std::string> audit_bytes(std::string_view value, std::size_t limit, bool allow_nul = false) {
    if (value.size() >= 2 && value.front() == '"' && value.back() == '"') {
        value.remove_prefix(1);
        value.remove_suffix(1);
        if (value.size() > limit || !std::all_of(value.begin(), value.end(), [](unsigned char c) {
                return c >= 0x21 && c <= 0x7e && c != '"';
            })) return {};
        return std::string(value);
    }
    if (value.empty() || value.size() % 2 || value.size() / 2 > limit) return {};
    std::string output;
    for (std::size_t i = 0; i < value.size(); i += 2) {
        const auto high = hex_digit(value[i]);
        const auto low = hex_digit(value[i + 1]);
        if (high < 0 || low < 0 || (!allow_nul && high == 0 && low == 0)) return {};
        output.push_back(static_cast<char>(high * 16 + low));
    }
    return output;
}

std::string base64(std::string_view bytes) {
    constexpr std::string_view alphabet =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string encoded;
    encoded.reserve(((bytes.size() + 2) / 3) * 4);
    for (std::size_t i = 0; i < bytes.size(); i += 3) {
        const bool second = i + 1 < bytes.size();
        const bool third = i + 2 < bytes.size();
        const unsigned a = static_cast<unsigned char>(bytes[i]);
        const unsigned b = second ? static_cast<unsigned char>(bytes[i + 1]) : 0;
        const unsigned c = third ? static_cast<unsigned char>(bytes[i + 2]) : 0;
        encoded += alphabet[a >> 2];
        encoded += alphabet[((a & 3) << 4) | (b >> 4)];
        encoded += second ? alphabet[((b & 15) << 2) | (c >> 6)] : '=';
        encoded += third ? alphabet[c & 63] : '=';
    }
    return encoded;
}

bool syscall_fields(const Fields& input, Execution& event, std::size_t& items, bool native) {
    const auto get = [&](std::string_view key) {
        const auto it = input.find(key);
        return it == input.end() ? std::string_view{} : it->second;
    };
    const auto arch = get("arch");
    std::uint32_t architecture, auid, session;
    const auto outcome = get("success");
    if (arch.size() != 8 || !number(arch, architecture, 16) || architecture != 0xc00000b7 ||
        !number(get("syscall"), event.syscall) || (event.syscall != 221 && event.syscall != 281) ||
        (outcome != "yes" && outcome != "no") || !number(get("exit"), event.result) ||
        ((outcome == "yes") != (event.result == 0)) || event.result > 0 ||
        !number(get("pid"), event.pid) || !event.pid || !number(get("ppid"), event.ppid) ||
        !number(get("uid"), event.uid) || !number(get("euid"), event.euid) ||
        !number(get("suid"), event.suid) || !number(get("fsuid"), event.fsuid) ||
        !number(get("auid"), auid) || !number(get("ses"), session) ||
        !number(get("items"), items)) return false;

    for (const auto& [name, value] : input) {
        constexpr std::array<std::string_view, 15> known{
            "arch", "syscall", "success", "exit", "items", "ppid", "pid", "auid",
            "uid", "euid", "suid", "fsuid", "ses", "comm", "exe",
        };
        if (std::find(known.begin(), known.end(), name) != known.end()) continue;
        if (name == "gid" || name == "egid" || name == "sgid" || name == "fsgid") {
            std::uint32_t discarded;
            if (number(value, discarded)) continue;
        }
        if (name == "a0" || name == "a1" || name == "a2" || name == "a3") {
            std::uint64_t discarded;
            if (number(value, discarded, 16)) continue;
        }
        if (name == "key" && (value == "(null)" || audit_bytes(value, 4096))) continue;
        if (native && (name == "tty" || name == "subj") && !value.empty()) continue;
        return false;
    }

    const auto exe = audit_bytes(get("exe"), 4096);
    const auto comm = audit_bytes(get("comm"), 256);
    if (!exe || exe->empty() || !comm || comm->empty()) return false;
    event.arch = architecture;
    event.exe_base64 = base64(*exe);
    event.comm_base64 = base64(*comm);
    if (auid != std::numeric_limits<std::uint32_t>::max()) event.auid = auid;
    if (session != std::numeric_limits<std::uint32_t>::max()) event.session = session;
    event.success = outcome == "yes";
    return true;
}
}

ExecutionResult validate_execution(const Event& event) try {
    if (const auto error = validate_execve(event); !error.empty()) return {{}, error};
    Execution execution{};
    execution.key = event.key;
    bool syscall = false;
    std::size_t items = 0;

    for (const auto& record : event.records) {
        if (record->type == "EOE" || record->type == "EXECVE") continue;
        const auto input = fields(*record);
        if (!input) return {{}, "invalid_execution_fields"};
        const bool native = record->profile == RecordProfile::auditd_string;
        if (record->type == "SYSCALL") {
            if (syscall || !syscall_fields(*input, execution, items, native)) return {{}, "invalid_syscall"};
            syscall = true;
        } else if (record->type == "CWD" || record->type == "PROCTITLE") {
            const bool cwd = record->type == "CWD";
            auto& seen = cwd ? execution.cwd_present : execution.proctitle_present;
            const auto value = input->find(cwd ? "cwd" : "proctitle");
            if (seen || input->size() != 1 || value == input->end() ||
                (!cwd && !native && value->second.starts_with('"')) ||
                !audit_bytes(value->second, 65536, !cwd)) return {{}, "invalid_context_record"};
            seen = true;
        } else if (record->type == "PATH") {
            const auto item = input->find("item");
            const auto name = input->find("name");
            const auto kind = input->find("nametype");
            std::size_t index;
            if ((!native && input->size() != 3) || item == input->end() || name == input->end() ||
                kind == input->end() || !number(item->second, index) ||
                index != execution.path_count || kind->second != "NORMAL" ||
                !audit_bytes(name->second, 4096)) return {{}, "invalid_path_record"};
            constexpr std::array<std::string_view, 15> path_fields{
                "item", "name", "nametype", "inode", "dev", "mode", "ouid", "ogid",
                "rdev", "obj", "cap_fp", "cap_fi", "cap_fe", "cap_fver", "cap_frootid",
            };
            for (const auto& [field, value] : *input) {
                if (value.empty() ||
                    std::find(path_fields.begin(), path_fields.end(), field) == path_fields.end()) {
                    return {{}, "invalid_path_record"};
                }
            }
            ++execution.path_count;
        } else {
            return {{}, "unsupported_execution_record"};
        }
    }
    if (!syscall || execution.path_count != items) return {{}, "incomplete_execution"};
    return {std::move(execution), {}};
} catch (const std::bad_alloc&) {
    return {{}, "execution_allocation"};
}
}
