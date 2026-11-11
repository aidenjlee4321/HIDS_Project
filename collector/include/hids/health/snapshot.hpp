#pragma once
#include <cstdint>
#include <string_view>
#include <nlohmann/json.hpp>
namespace hids::health {
using Json = nlohmann::json;
inline constexpr std::uint64_t fresh_ns = 15000000000ULL;
Json parse_dispatcher(std::string_view data, std::uint64_t mtime_ns, std::uint64_t now_ns);
Json read_dispatcher(const char* path = "/run/audit/auditd.state");
}
