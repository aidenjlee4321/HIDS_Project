#include "hids/pilot/contract.hpp"
#include <charconv>
#include <chrono>
#include <cstdio>
#include <ctime>
#include <cerrno>
#include <regex>
#include <set>
#include <vector>

namespace hids::pilot {
namespace {
bool ascii(const std::string& s) {
    for (unsigned char c : s) if (c > 127) return false;
    return s.size() <= 256;
}
void tree(const Json& j, unsigned depth = 0) {
    if (j.is_structured() && depth >= 8) throw Invalid("invalid_json");
    if (j.is_string() && !ascii(j.get_ref<const std::string&>())) throw Invalid();
    if (j.is_object()) for (auto it = j.begin(); it != j.end(); ++it) {
        if (!ascii(it.key())) throw Invalid();
        tree(it.value(), depth + 1);
    }
    if (j.is_array()) for (const auto& v : j) tree(v, depth + 1);
}
struct Guard final : nlohmann::json_sax<Json> {
    std::vector<std::set<std::string>> keys;
    const char* error = "invalid_json";
    bool null() override { return true; }
    bool boolean(bool) override { return true; }
    bool number_integer(number_integer_t) override { return true; }
    bool number_unsigned(number_unsigned_t) override { return true; }
    bool number_float(number_float_t, const string_t&) override { return true; }
    bool string(string_t& s) override { if (!ascii(s)) {error = "invalid_event"; return false;} return true; }
    bool binary(binary_t&) override { return false; }
    bool push() { if (keys.size() == 8) return false; keys.emplace_back(); return true; }
    bool start_object(std::size_t) override { return push(); }
    bool key(string_t& key) override {
        if (!ascii(key)) {error = "invalid_event"; return false;}
        return !keys.empty() && keys.back().insert(key).second;
    }
    bool end_object() override { keys.pop_back(); return true; }
    bool start_array(std::size_t) override { return push(); }
    bool end_array() override { keys.pop_back(); return true; }
    bool parse_error(std::size_t, const std::string&, const nlohmann::detail::exception&) override { return false; }
};
void shape(const Json& j, std::initializer_list<const char*> names) {
    if (!j.is_object() || j.size() != names.size()) throw Invalid();
    for (const char* key : names) if (!j.contains(key)) throw Invalid();
}
void integer(const Json& j, std::uint64_t lo, std::uint64_t hi) {
    if (!j.is_number_integer()) throw Invalid();
    if (!j.is_number_unsigned() && j.get<std::int64_t>() < 0) throw Invalid();
    const auto n = j.get<std::uint64_t>();
    if (n < lo || n > hi) throw Invalid();
}
bool one_of(const Json& j, std::initializer_list<const char*> values) {
    if (!j.is_string()) return false;
    for (const auto* v : values) if (j == v) return true;
    return false;
}
} // namespace
Json parse(std::string_view raw, std::size_t limit, bool fixture_document) {
    if (raw.size() > limit) throw Invalid("frame_too_large");
    if (raw.empty() || (!fixture_document && raw.find_first_of("\r\n") != raw.npos) || raw.starts_with("\xef\xbb\xbf")) throw Invalid("invalid_json");
    Guard guard;
    if (!Json::sax_parse(raw.begin(), raw.end(), &guard)) throw Invalid(guard.error);
    auto j = Json::parse(raw.begin(), raw.end());
    if (!j.is_object()) throw Invalid();
    return j;
}
bool uuid_valid(const Json& j) {
    static const std::regex pattern("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}");
    return j.is_string() && std::regex_match(j.get_ref<const std::string&>(), pattern);
}
void timestamp_valid(const Json& j) {
    static const std::regex pattern("[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{6}Z");
    if (!j.is_string()) throw Invalid();
    const auto& s = j.get_ref<const std::string&>();
    if (!std::regex_match(s, pattern)) throw Invalid();
    const int y = std::stoi(s.substr(0,4)), m = std::stoi(s.substr(5,2)), d = std::stoi(s.substr(8,2));
    const bool leap = y%4 == 0 && (y%100 != 0 || y%400 == 0);
    const int days[] = {31, leap ? 29 : 28,31,30,31,30,31,31,30,31,30,31};
    if (y < 1 || m < 1 || m > 12 || d < 1 || d > days[m-1] ||
        std::stoi(s.substr(11,2)) > 23 || std::stoi(s.substr(14,2)) > 59 || std::stoi(s.substr(17,2)) > 59) throw Invalid();
}
void validate_native(const Json& j) {
    shape(j,{"what","what_code","pid","tgid","parent","cpu","connector_sequence","timestamp_ns","timestamp_unit","timestamp_clock"});
    if (j["what"] != "PROC_EVENT_EXEC" || j["timestamp_unit"] != "ns" || j["timestamp_clock"] != "linux.cn_proc.timestamp_ns" || !j["parent"].is_null()) throw Invalid();
    integer(j["what_code"],2,2); integer(j["pid"],1,2147483647); integer(j["tgid"],1,2147483647);
    integer(j["cpu"],0,4294967295ULL); integer(j["connector_sequence"],0,4294967295ULL);
    if (!j["timestamp_ns"].is_string()) throw Invalid();
    const auto& s = j["timestamp_ns"].get_ref<const std::string&>();
    if (s.empty() || s.size() > 20 || (s.size() > 1 && s[0] == '0')) throw Invalid();
    for (char c : s) if (c < '0' || c > '9') throw Invalid();
    std::uint64_t value{};
    auto parsed = std::from_chars(s.data(),s.data()+s.size(),value);
    if (parsed.ec != std::errc{} || parsed.ptr != s.data()+s.size()) throw Invalid();
}
void validate_event(const Json& j) {
    tree(j);
    if (!j.is_object() || !j.contains("protocol_version") || !j.contains("contract_version") || !j.contains("ecs_reference_version")) throw Invalid();
    if (!j["protocol_version"].is_number_integer() || !j["contract_version"].is_string() || !j["ecs_reference_version"].is_string()) throw Invalid();
    if (j["protocol_version"] != 1 || j["contract_version"] != "m1.process-exec/0.1.0" || j["ecs_reference_version"] != "9.5.0") throw Invalid("unsupported_version");
    shape(j,{"protocol_version","message_type","contract_version","ecs_reference_version","event_id","producer_instance_id","source","native","timestamps"});
    if (j["message_type"] != "event" || !uuid_valid(j["event_id"]) || !uuid_valid(j["producer_instance_id"])) throw Invalid();
    const Json source = {{"adapter","linux.cn_proc"},{"mode","sanitized_fixture"},{"fixture_id","synthetic-exec-001"},{"boot_id",nullptr}};
    if (j["source"] != source) throw Invalid();
    validate_native(j["native"]);
    const auto& t = j["timestamps"];
    shape(t,{"activity_wall_time","activity_wall_time_reason","observed_at","observation"});
    if (!t["activity_wall_time"].is_null() || t["activity_wall_time_reason"] != "not_emitted_by_source" || t["observation"] != "fixture_decode") throw Invalid();
    timestamp_valid(t["observed_at"]);
}
Response validate_response(const Json& j, std::string_view id) {
    tree(j);
    if (!j.is_object() || !j.contains("protocol_version") || !j["protocol_version"].is_number_integer() || j["protocol_version"] != 1 || !j.contains("message_type")) throw Invalid();
    if (j["message_type"] == "ack") {
        shape(j,{"protocol_version","message_type","event_id","result"});
        if (j["event_id"] != id || !one_of(j["result"],{"stored","duplicate"})) throw Invalid();
        return {"acknowledged",j["result"].get<std::string>()};
    }
    shape(j,{"protocol_version","message_type","event_id","code"});
    if (j["message_type"] == "reject") {
        if ((!j["event_id"].is_null() && j["event_id"] != id) || !one_of(j["code"],{"invalid_json","invalid_event","unsupported_version","frame_too_large","id_conflict","capacity_exceeded"})) throw Invalid();
        return {"rejected",j["code"].get<std::string>()};
    }
    if (j["message_type"] != "error" || j["event_id"] != id || j["code"] != "storage_error") throw Invalid();
    return {"unconfirmed","storage_error"};
}
std::string uuid_v4(const std::function<ssize_t(void*,std::size_t)>& read) {
    std::array<unsigned char,16> b{};
    std::size_t offset = 0;
    while (offset < b.size()) {
        const auto n = read(b.data()+offset,b.size()-offset);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0 || static_cast<std::size_t>(n) > b.size()-offset) throw Invalid("uuid_generation_failed");
        offset += static_cast<std::size_t>(n);
    }
    b[6] = (b[6]&15U)|64U; b[8] = (b[8]&63U)|128U;
    static constexpr char hex[] = "0123456789abcdef";
    std::string out;
    for (std::size_t i=0;i<b.size();++i) {
        if (i==4 || i==6 || i==8 || i==10) out += '-';
        out += hex[b[i]>>4U]; out += hex[b[i]&15U];
    }
    return out;
}
std::string utc_now() {
    timespec observed{};
    if (::clock_gettime(CLOCK_REALTIME,&observed)!=0 || observed.tv_nsec<0 || observed.tv_nsec>=1000000000)
        throw Invalid("observation_clock_failed");
    const std::time_t seconds = observed.tv_sec;
    std::tm tm{};
    if (!gmtime_r(&seconds,&tm)) throw Invalid("observation_clock_failed");
    if (tm.tm_year < -1899 || tm.tm_year > 8099) throw Invalid("observation_clock_failed");
    char buffer[40]{};
    const int n = std::snprintf(buffer,sizeof(buffer),"%04d-%02d-%02dT%02d:%02d:%02d.%06lldZ",tm.tm_year+1900,tm.tm_mon+1,tm.tm_mday,tm.tm_hour,tm.tm_min,tm.tm_sec,static_cast<long long>(observed.tv_nsec/1000));
    if (n != 27) throw Invalid("observation_clock_failed");
    timestamp_valid(std::string(buffer));
    return buffer;
}
Json normalize(const process::NativeEvent& e, const std::string& observed, const std::string& producer, const std::string& id) {
    if (e.kind != process::Lifecycle::executed || e.parent || e.native_exit_status || e.native_exit_signal) throw Invalid();
    Json j = {{"protocol_version",1},{"message_type","event"},{"contract_version","m1.process-exec/0.1.0"},{"ecs_reference_version","9.5.0"},
              {"event_id",id},{"producer_instance_id",producer},
              {"source",{{"adapter","linux.cn_proc"},{"mode","sanitized_fixture"},{"fixture_id","synthetic-exec-001"},{"boot_id",nullptr}}},
              {"native",{{"what","PROC_EVENT_EXEC"},{"what_code",2},{"pid",e.tid},{"tgid",e.tgid},{"parent",nullptr},{"cpu",e.cpu},{"connector_sequence",e.sequence},{"timestamp_ns",std::to_string(e.kernel_monotonic_ns)},{"timestamp_unit","ns"},{"timestamp_clock","linux.cn_proc.timestamp_ns"}}},
              {"timestamps",{{"activity_wall_time",nullptr},{"activity_wall_time_reason","not_emitted_by_source"},{"observed_at",observed},{"observation","fixture_decode"}}}};
    validate_event(j); return j;
}
std::string prepare_line(const process::NativeEvent& e,
    const std::function<std::string()>& clock,const std::function<std::string()>& ids,
    const std::function<std::string(const Json&)>& serialize) {
    if (e.kind!=process::Lifecycle::executed || e.tid<=0 || e.tgid<=0 || e.parent || e.native_exit_status || e.native_exit_signal)
        throw Invalid("native_fixture_failed");
    std::string observed;
    try {observed=clock();timestamp_valid(observed);} catch (...) {throw Invalid("observation_clock_failed");}
    const auto producer=ids();const auto id=ids();
    const auto event=normalize(e,observed,producer,id);
    try {
        const auto payload=serialize(event);
        if (payload.size()>event_limit || parse(payload)!=event) throw Invalid();
        return payload+"\n";
    } catch (...) {throw Invalid("serialization_failed");}
}
} // namespace hids::pilot
