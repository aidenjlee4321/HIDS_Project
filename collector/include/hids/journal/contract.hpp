#pragma once
#include "hids/pilot/contract.hpp"
namespace hids::journal {
using Json = nlohmann::json;
using Invalid = pilot::Invalid;
inline constexpr std::size_t event_limit=65536, response_limit=2048;
Json parse(std::string_view raw, std::size_t limit=event_limit);
void validate(const Json&);
void validate_response(const Json&,std::string_view pending);
std::string identity(const std::string& source,const std::string& cursor);
std::string canonical(const Json&);
bool matches(const Json& fields);
}
