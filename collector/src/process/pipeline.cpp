#include "hids/process/pipeline.hpp"
#include <charconv>
#include <cstdio>
#include <regex>
namespace hids::processlive {
namespace {
using pilot::Invalid;
void shape(const Json& j,std::initializer_list<const char*> names){
 if(!j.is_object()||j.size()!=names.size())throw Invalid();
 for(auto key:names)if(!j.contains(key))throw Invalid();
}
void number(const Json& j,std::uint64_t lo,std::uint64_t hi){
 if(!j.is_number_integer()||(!j.is_number_unsigned()&&j.get<std::int64_t>()<0))throw Invalid();
 const auto v=j.get<std::uint64_t>();if(v<lo||v>hi)throw Invalid();
}
struct Kind {const char* name;std::uint32_t code;const char* action;const char* type;};
Kind kind(process::Lifecycle value){
 switch(value){
 case process::Lifecycle::forked:return {"PROC_EVENT_FORK",1,"fork","creation"};
 case process::Lifecycle::executed:return {"PROC_EVENT_EXEC",2,"exec","start"};
 case process::Lifecycle::exited:return {"PROC_EVENT_EXIT",2147483648U,"exit","end"};
 }throw Invalid();
}
Kind kind(const Json& value){
 if(value=="PROC_EVENT_FORK")return kind(process::Lifecycle::forked);
 if(value=="PROC_EVENT_EXEC")return kind(process::Lifecycle::executed);
 if(value=="PROC_EVENT_EXIT")return kind(process::Lifecycle::exited);
 throw Invalid();
}
Json mapped(const Json& n,const Kind& k,const Json& id,const Json& observed){
 Json p={{"pid",n.at("tgid")},{"thread",{{"id",n.at("tid")}}}};
 if(!n.at("parent").is_null()&&n.at("parent").at("tgid").get<std::int64_t>()>0)p["parent"]={{"pid",n.at("parent").at("tgid")}};
 return {{"event",{{"id",id},{"kind","event"},{"category",Json::array({"process"})},{"type",Json::array({k.type})},{"action",k.action},{"provider","linux.cn_proc"},{"created",observed}}},{"process",p}};
}
}
void validate_source(const Json& s,std::string_view mode){
 shape(s,{"adapter","mode","source_id","activation_id","boot_id","profile"});
 if((mode!="live"&&mode!="synthetic")||s["adapter"]!="linux.cn_proc"||s["mode"]!=mode||s["profile"]!="linux.cn_proc.lifecycle/1"||!pilot::uuid_valid(s["source_id"])||!pilot::uuid_valid(s["activation_id"]))throw Invalid();
 static const std::regex boot("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}");
 if(!s["boot_id"].is_string()||!std::regex_match(s["boot_id"].get_ref<const std::string&>(),boot))throw Invalid();
}
void validate(const Json& j,const Json& source,std::string_view mode){
 shape(j,{"protocol_version","message_type","contract_version","ecs_reference_version","event_id","producer_instance_id","source","native","timestamps","normalized"});
 number(j["protocol_version"],1,1);
 if(j["message_type"]!="event"||j["contract_version"]!=contract||j["ecs_reference_version"]!="9.5.0"||!pilot::uuid_valid(j["event_id"])||!pilot::uuid_valid(j["producer_instance_id"]))throw Invalid();
 validate_source(source,mode);validate_source(j["source"],mode);if(j["source"]!=source)throw Invalid();
 const auto& n=j["native"];shape(n,{"what","what_code","tid","tgid","parent","cpu","connector_sequence","timestamp_ns","native_exit_status","native_exit_signal"});
 const auto k=kind(n["what"]);number(n["what_code"],k.code,k.code);
 number(n["tid"],1,2147483647);number(n["tgid"],1,2147483647);number(n["cpu"],0,4294967295ULL);number(n["connector_sequence"],0,4294967295ULL);
 if(!n["timestamp_ns"].is_string())throw Invalid();
 const auto& raw=n["timestamp_ns"].get_ref<const std::string&>();
 if(raw.empty()||raw.size()>20||(raw.size()>1&&raw[0]=='0'))throw Invalid();
 for(char c:raw)if(c<'0'||c>'9')throw Invalid();
 std::uint64_t value{};const auto parsed=std::from_chars(raw.data(),raw.data()+raw.size(),value);
 if(parsed.ec!=std::errc{}||parsed.ptr!=raw.data()+raw.size())throw Invalid();
 if(k.code==2){if(!n["parent"].is_null())throw Invalid();}
 else {shape(n["parent"],{"tid","tgid"});number(n["parent"]["tid"],0,2147483647);number(n["parent"]["tgid"],0,2147483647);}
 for(auto key:{"native_exit_status","native_exit_signal"}){
  if(k.code==2147483648U)number(n[key],0,4294967295ULL);else if(!n[key].is_null())throw Invalid();
 }
 const auto& t=j["timestamps"];shape(t,{"activity_wall_time","activity_wall_time_reason","observed_at","observation"});
 if(!t["activity_wall_time"].is_null()||t["activity_wall_time_reason"]!="not_emitted_by_source"||t["observation"]!="native_decode")throw Invalid();
 pilot::timestamp_valid(t["observed_at"]);
 if(j["normalized"].dump()!=mapped(n,k,j["event_id"],t["observed_at"]).dump())throw Invalid();
 const auto raw_event=j.dump();if(raw_event.size()>event_limit)throw Invalid("frame_too_large");
 // Reuse the bounded duplicate-key/depth/ASCII parser, not the M1 event contract.
 (void)pilot::parse(raw_event,event_limit);
}
Json normalize(const process::NativeEvent& e,const std::string& observed,const Json& source,const std::string& producer,const std::string& id){
 const auto k=kind(e.kind);Json parent=nullptr;
 if(e.parent)parent={{"tid",e.parent->tid},{"tgid",e.parent->tgid}};
 Json native={{"what",k.name},{"what_code",k.code},{"tid",e.tid},{"tgid",e.tgid},{"parent",parent},{"cpu",e.cpu},{"connector_sequence",e.sequence},{"timestamp_ns",std::to_string(e.kernel_monotonic_ns)},{"native_exit_status",nullptr},{"native_exit_signal",nullptr}};
 if(e.native_exit_status)native["native_exit_status"]=*e.native_exit_status;
 if(e.native_exit_signal)native["native_exit_signal"]=*e.native_exit_signal;
 Json j={{"protocol_version",1},{"message_type","event"},{"contract_version",contract},{"ecs_reference_version","9.5.0"},{"event_id",id},{"producer_instance_id",producer},{"source",source},{"native",native},
 {"timestamps",{{"activity_wall_time",nullptr},{"activity_wall_time_reason","not_emitted_by_source"},{"observed_at",observed},{"observation","native_decode"}}},{"normalized",mapped(native,k,id,observed)}};
 validate(j,source,source.at("mode").get<std::string>());return j;
}
std::string observed_time(const timespec& value){
 if(value.tv_nsec<0||value.tv_nsec>=1000000000)throw Invalid("observation_clock_failed");
 std::tm tm{};const std::time_t seconds=value.tv_sec;
 if(!gmtime_r(&seconds,&tm)||tm.tm_year < -1899||tm.tm_year>8099)throw Invalid("observation_clock_failed");
 char out[40]{};const int n=std::snprintf(out,sizeof(out),"%04d-%02d-%02dT%02d:%02d:%02d.%06lldZ",tm.tm_year+1900,tm.tm_mon+1,tm.tm_mday,tm.tm_hour,tm.tm_min,tm.tm_sec,static_cast<long long>(value.tv_nsec/1000));
 if(n!=27)throw Invalid("observation_clock_failed");
 pilot::timestamp_valid(std::string(out));return out;
}
void Queue::on_event(const process::NativeEvent& event)noexcept{
 if(owned_fixture>0&&(event.tid!=owned_fixture||event.tgid!=owned_fixture))return;
 if(failed)return;
 if(owned_fixture>0){
  switch(event.kind){case process::Lifecycle::forked:fixture_bits|=1;break;case process::Lifecycle::executed:fixture_bits|=2;break;case process::Lifecycle::exited:fixture_bits|=4;break;}
 }
 if(size_==slots_.size()){failed=true;reason="queue_full";return;}
 timespec now{};if(clock_(CLOCK_REALTIME,&now)!=0||now.tv_nsec<0||now.tv_nsec>=1000000000){failed=true;reason="clock_failed";return;}
 slots_[(head_+size_)%slots_.size()]={event,now};++size_;
}
void Queue::on_diagnostic(const process::Diagnostic& value)noexcept{
 const auto index=static_cast<std::size_t>(value.reason);
 if(index<diagnostics.size()&&diagnostics[index]!=4294967295U)++diagnostics[index];
}
bool Queue::pop(Slot& value)noexcept{
 if(!size_)return false;
 value=slots_[head_];head_=(head_+1)%slots_.size();--size_;return true;
}
}
