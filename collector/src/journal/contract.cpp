#include "hids/journal/contract.hpp"
#include <charconv>
#include <set>
#include <vector>
namespace hids::journal {
namespace {
void shape(const Json& j,std::initializer_list<const char*> keys) {
    if (!j.is_object() || j.size()!=keys.size()) throw Invalid();
    for (auto k:keys) if (!j.contains(k)) throw Invalid();
}
void text(const Json& j,std::size_t max,std::size_t min=0,bool ascii=false) {
    if (!j.is_string()) throw Invalid();
    const auto& s=j.get_ref<const std::string&>();
    if (s.size()<min || s.size()>max || s.find('\0')!=s.npos) throw Invalid();
    if (ascii) for (unsigned char c:s) if (c>127) throw Invalid();
    try { (void)j.dump(); } catch (...) { throw Invalid(); } // UTF-8, including surrogates.
}
void number(const Json& j,std::uint64_t max) {
    if (!j.is_number_integer() || (!j.is_number_unsigned() && j.get<std::int64_t>()<0) || j.get<std::uint64_t>()>max) throw Invalid();
}
void decimal(const Json& j,std::uint64_t max,std::uint64_t min=0) {
    text(j,20,1,true);const auto& s=j.get_ref<const std::string&>();
    if (s.size()>1 && s[0]=='0') throw Invalid();
    for (char c:s) if (c<'0'||c>'9') throw Invalid();
    std::uint64_t n=0;auto r=std::from_chars(s.data(),s.data()+s.size(),n);
    if (r.ec!=std::errc{} || r.ptr!=s.data()+s.size() || n<min || n>max) throw Invalid();
}
bool hex32(const Json& j) {
    if (!j.is_string() || j.get_ref<const std::string&>().size()!=32) return false;
    for (char c:j.get_ref<const std::string&>()) if (!((c>='0'&&c<='9')||(c>='a'&&c<='f'))) return false;
    return true;
}
bool reason(const Json& j) {return j=="missing_required"||j=="malformed_field"||j=="duplicate_field"||j=="binary_field"||j=="field_too_large"||j=="too_many_fields"||j=="event_too_large";}
struct Guard final : nlohmann::json_sax<Json> {
    std::vector<std::set<std::string>> keys;
    bool null() override{return true;} bool boolean(bool) override{return true;}
    bool number_integer(number_integer_t) override{return true;}
    bool number_unsigned(number_unsigned_t) override{return true;}
    bool number_float(number_float_t,const string_t&) override{return false;}
    bool string(string_t&) override{return true;} bool binary(binary_t&) override{return false;}
    bool push(){if(keys.size()==8)return false;keys.emplace_back();return true;}
    bool start_object(std::size_t) override{return push();}
    bool start_array(std::size_t) override{return push();}
    bool key(string_t& s) override{return !keys.empty() && keys.back().insert(s).second;}
    bool end_object() override{keys.pop_back();return true;}
    bool end_array() override{keys.pop_back();return true;}
    bool parse_error(std::size_t,const std::string&,const nlohmann::detail::exception&) override{return false;}
};
}
Json parse(std::string_view raw,std::size_t limit) {
    if(raw.size()>limit)throw Invalid("frame_too_large");
    if(raw.empty()||raw.find_first_of("\r\n")!=raw.npos||raw.starts_with("\xef\xbb\xbf"))throw Invalid("invalid_json");
    Guard guard;if(!Json::sax_parse(raw.begin(),raw.end(),&guard))throw Invalid("invalid_json");
    auto j=Json::parse(raw.begin(),raw.end());if(!j.is_object())throw Invalid();return j;
}
std::string identity(const std::string& source,const std::string& cursor) {
    if(!pilot::uuid_valid(source))throw Invalid();
    text(cursor,512,1,true);std::string out="j1."+source+".";constexpr char hex[]="0123456789abcdef";
    for(unsigned char c:cursor){if(c<32||c>126)throw Invalid();out+=hex[c>>4];out+=hex[c&15];}return out;
}
bool matches(const Json& f) {
    if(!f.is_object()||!f.contains("_COMM")||!f.contains("_EXE"))return false;
    return (f["_COMM"]=="sshd-session"&&f["_EXE"]=="/usr/lib/openssh/sshd-session") || (f["_COMM"]=="sshd"&&f["_EXE"]=="/usr/sbin/sshd");
}
void validate(const Json& j) {
    if(!j.is_object()||!j.contains("protocol_version")||!j.contains("contract_version"))throw Invalid();
    if(!j["protocol_version"].is_number_integer()||!j["contract_version"].is_string())throw Invalid();
    if(j["protocol_version"]!=2||j["contract_version"]!="m2.journal-ssh/0.1.0")throw Invalid("unsupported_version");
    if(!j.contains("message_type")) {
        throw Invalid();
    }
    const bool rejected=j["message_type"]=="journal_rejection";
    if(rejected)shape(j,{"protocol_version","message_type","contract_version","source_id","activation_id","event_id","cursor","expected_revision","observation","reason"});
    else {if(j["message_type"]!="journal_event")throw Invalid();shape(j,{"protocol_version","message_type","contract_version","source_id","activation_id","event_id","cursor","expected_revision","observation","journal","fields","activity_wall_time","activity_wall_time_reason"});}
    if(!pilot::uuid_valid(j["source_id"])||!pilot::uuid_valid(j["activation_id"]))throw Invalid();
    text(j["cursor"],512,1,true);
    if(j["event_id"]!=identity(j["source_id"].get<std::string>(),j["cursor"].get<std::string>()))throw Invalid();
    number(j["expected_revision"],9223372036854775807ULL);
    const auto& o=j["observation"];shape(o,{"producer_instance_id","observed_at"});
    if(!pilot::uuid_valid(o["producer_instance_id"])) {
        throw Invalid();
    }
    pilot::timestamp_valid(o["observed_at"]);
    if(rejected){if(!reason(j["reason"]))throw Invalid();return;}
    const auto& c=j["journal"];shape(c,{"boot_id","realtime_us","monotonic_us"});if(!hex32(c["boot_id"]))throw Invalid();
    decimal(c["realtime_us"],UINT64_MAX);decimal(c["monotonic_us"],UINT64_MAX);
    if(!j["activity_wall_time"].is_null()||j["activity_wall_time_reason"]!="not_established")throw Invalid();
    const auto& f=j["fields"];shape(f,{"_COMM","_EXE","MESSAGE","_PID","_UID","_GID","_SYSTEMD_UNIT","PRIORITY","_TRANSPORT","MESSAGE_ID"});
    text(f["_COMM"],64,1);text(f["_EXE"],1024,1);text(f["MESSAGE"],4096);
    for(auto k:{"_PID","_UID","_GID"})if(!f[k].is_null())decimal(f[k],std::string_view(k)=="_PID"?2147483647ULL:4294967295ULL,std::string_view(k)=="_PID"?1:0);
    if(!f["_SYSTEMD_UNIT"].is_null())text(f["_SYSTEMD_UNIT"],256);
    if(!f["PRIORITY"].is_null()){text(f["PRIORITY"],1,1,true);if(f["PRIORITY"].get<std::string>()[0]<'0'||f["PRIORITY"].get<std::string>()[0]>'7')throw Invalid();}
    if(!f["_TRANSPORT"].is_null())text(f["_TRANSPORT"],32,1,true);
    if(!f["MESSAGE_ID"].is_null()&&!hex32(f["MESSAGE_ID"]))throw Invalid();
    if(!matches(f))throw Invalid();
}
std::string canonical(const Json& event) {
    validate(event);auto copy=event;for(auto k:{"activation_id","expected_revision","observation"})copy.erase(k);return copy.dump(-1,' ',true);
}
void validate_response(const Json& j,std::string_view id) {
    if(!j.is_object()||!j.contains("protocol_version")||!j["protocol_version"].is_number_integer()||j["protocol_version"]!=2||!j.contains("message_type"))throw Invalid();
    if(j["message_type"]=="ack"){
        shape(j,{"protocol_version","message_type","event_id","result","checkpoint_revision","code"});number(j["checkpoint_revision"],9223372036854775807ULL);
        if(j["checkpoint_revision"]==0||j["event_id"]!=id)throw Invalid();
        if(j["result"]=="rejected_record"){if(!reason(j["code"]))throw Invalid();}
        else if((j["result"]!="stored"&&j["result"]!="duplicate")||!j["code"].is_null())throw Invalid();
        return;
    }
    shape(j,{"protocol_version","message_type","event_id","code"});
    if(j["message_type"]=="error"){if(j["event_id"]!=id||j["code"]!="storage_error")throw Invalid();return;}
    if(j["message_type"]!="reject"||(!j["event_id"].is_null()&&j["event_id"]!=id))throw Invalid();
    for(auto k:{"invalid_json","invalid_event","unsupported_version","frame_too_large","id_conflict","stale_revision","inactive_source","reader_busy"})if(j["code"]==k)return;
    throw Invalid();
}
}
