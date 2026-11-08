#include "hids/journal_collector.hpp"
#include <map>
#include <stdexcept>
namespace hids::journal {
void ssh_filter(MatchIo& io) {
    io.match("_COMM=sshd-session");io.match("_EXE=/usr/lib/openssh/sshd-session");
    io.disjunction();io.match("_COMM=sshd");io.match("_EXE=/usr/sbin/sshd");
}
Json normalize(const Entry& e,const std::string& source,const std::string& activation,
               std::uint64_t rev,const Json& observation) {
    Json base={{"protocol_version",2},{"message_type","journal_rejection"},{"contract_version","m2.journal-ssh/0.1.0"},
               {"source_id",source},{"activation_id",activation},{"cursor",e.cursor},{"event_id",identity(source,e.cursor)},
               {"expected_revision",rev},{"observation",observation}};
    const auto reject=[&](const std::string& reason){auto j=base;j["reason"]=reason;validate(j);return j;};
    if(e.rejection)return reject(*e.rejection);
    if(e.fields.size()>256)return reject("too_many_fields");
    const std::map<std::string,std::size_t> limits={{"_COMM",64},{"_EXE",1024},{"MESSAGE",4096},{"_PID",10},{"_UID",10},{"_GID",10},{"_SYSTEMD_UNIT",256},{"PRIORITY",1},{"_TRANSPORT",32},{"MESSAGE_ID",32}};
    Json f=Json::object();for(const auto& [key,size]:limits){(void)size;f[key]=nullptr;}
    for(const auto& [key,value]:e.fields){
        auto limit=limits.find(key);if(limit==limits.end())continue;
        if(!f[key].is_null())return reject("duplicate_field");
        if(value.size()>limit->second)return reject("field_too_large");
        if(value.find('\0')!=value.npos)return reject("binary_field");
        try{(void)Json(value).dump();}catch(...){return reject("binary_field");}
        f[key]=value;
    }
    if(f["_COMM"].is_null()||f["_EXE"].is_null()||f["MESSAGE"].is_null()||e.boot.empty()||e.realtime_us.empty()||e.monotonic_us.empty())return reject("missing_required");
    auto event=base;event["message_type"]="journal_event";event["fields"]=f;
    event["journal"]={{"boot_id",e.boot},{"realtime_us",e.realtime_us},{"monotonic_us",e.monotonic_us}};
    event["activity_wall_time"]=nullptr;event["activity_wall_time_reason"]="not_established";
    try{validate(event);}catch(const Invalid&){return reject("malformed_field");}
    if(event.dump(-1,' ',true).size()>event_limit)return reject("event_too_large");
    return event;
}
void JournalCollector::start(const Activation& a) {
    if(open_)throw std::runtime_error("already_started");
    if(!a.authorized)throw std::runtime_error("inactive_source");
    if(!pilot::uuid_valid(a.source)||!pilot::uuid_valid(a.activation)||a.revision>9223372036854775807ULL)throw Invalid();
    if(a.initialized&&!a.cursor)throw std::runtime_error("unanchored_restart_gap");
    if(a.cursor)(void)identity(a.source,*a.cursor);
    state_=a;
    try{
        io_.open();open_=true;io_.filter();
        if(a.initialized){
            if(!a.cursor)throw std::runtime_error("unanchored_restart_gap");
            if(!io_.seek_exact(*a.cursor))throw std::runtime_error("cursor_gap");
        }else{state_.cursor=io_.tail();boundary_pending_=true;}
    }catch(...){stop();throw;}
}
void JournalCollector::boundary_committed() {
    if(!open_||!boundary_pending_)throw std::runtime_error("no_boundary");
    boundary_pending_=false;state_.initialized=true;
}
std::optional<Json> JournalCollector::poll_once(const Json& obs,unsigned timeout_ms) {
    return poll_with_observation([&]{return obs;},timeout_ms);
}
std::optional<Json> JournalCollector::poll_with_observation(const std::function<Json()>& observation,unsigned timeout_ms) {
    if(!open_||boundary_pending_)throw std::runtime_error("not_active");
    if(pending_)return pending_;
    try{
        auto e=io_.next();
        if(!e){
            const auto changed=io_.wait(timeout_ms>100?100:timeout_ms);
            if(changed==2){if(!state_.cursor||!io_.seek_exact(*state_.cursor))throw std::runtime_error("cursor_gap");}
            e=io_.next();
        }
        if(!e)return std::nullopt;
        pending_=normalize(*e,state_.source,state_.activation,state_.revision,observation());
        return pending_;
    }catch(...){stop();throw;}
}
void JournalCollector::committed(std::string_view id,std::uint64_t rev) {
    if(!open_||!pending_||(*pending_)["event_id"]!=id||state_.revision==9223372036854775807ULL||rev!=state_.revision+1)throw std::runtime_error("invalid_commit_confirmation");
    state_.revision=rev;state_.cursor=(*pending_)["cursor"].get<std::string>();pending_.reset();
}
void JournalCollector::stop() noexcept {io_.close();open_=false;boundary_pending_=false;pending_.reset();}
}
