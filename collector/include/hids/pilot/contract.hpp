#pragma once
#include "hids/process_collector.hpp"
#include <nlohmann/json.hpp>
#include <functional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/types.h>

namespace hids::pilot {
static_assert(NLOHMANN_JSON_VERSION_MAJOR == 3 && NLOHMANN_JSON_VERSION_MINOR == 12 && NLOHMANN_JSON_VERSION_PATCH == 0,
              "M1 requires the owner-approved nlohmann/json 3.12.0 pin");
using Json = nlohmann::json;
inline constexpr std::size_t event_limit = 65536, response_limit = 512;
struct Invalid : std::runtime_error {
    explicit Invalid(const char* code = "invalid_event") : std::runtime_error(code) {}
};
Json parse(std::string_view, std::size_t limit = event_limit, bool fixture_document = false);
bool uuid_valid(const Json&);
void timestamp_valid(const Json&);
void validate_native(const Json&);
void validate_event(const Json&);
struct Response { std::string outcome, code; };
Response validate_response(const Json&, std::string_view pending_id);
std::string utc_now();
std::string uuid_v4(const std::function<ssize_t(void*, std::size_t)>&);
Json normalize(const process::NativeEvent&, const std::string& observation,
               const std::string& producer_id, const std::string& event_id);
std::string prepare_line(const process::NativeEvent&,
    const std::function<std::string()>& clock,
    const std::function<std::string()>& ids,
    const std::function<std::string(const Json&)>& serialize = [](const Json& j) { return j.dump(); });
} // namespace hids::pilot
