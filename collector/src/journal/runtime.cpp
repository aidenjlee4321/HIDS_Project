#include "hids/journal/runtime.hpp"
#include <algorithm>
#include <system_error>
namespace hids::journal {
namespace {
void keys(const Json& j,std::initializer_list<const char*> names){
    if(!j.is_object()||j.size()!=names.size())throw Invalid();
    for(auto name:names)if(!j.contains(name))throw Invalid();
}
std::uint64_t revision(const Json& j){
    if(!j.is_number_integer()||(!j.is_number_unsigned()&&j.get<std::int64_t>()<0)||j.get<std::uint64_t>()>9223372036854775807ULL)throw Invalid();
    return j.get<std::uint64_t>();
}
bool rejected(const Json& j){return j.is_object()&&j.contains("message_type")&&j["message_type"]=="reject";}
}
ReaderRuntime::ReaderRuntime(JournalIo& io,Channel& channel,std::string source,std::string producer,std::function<std::string()> clock)
    :collector_(io),channel_(channel),source_(std::move(source)),producer_(std::move(producer)),clock_(std::move(clock)){
    if(!pilot::uuid_valid(source_)||!pilot::uuid_valid(producer_))throw Invalid();
}
void ReaderRuntime::connect(Deadline deadline){
    const int error=channel_.connect(deadline);
    if(error)throw std::system_error(error,std::generic_category(),"ipc_connect");
    connected_=true;
}
Json ReaderRuntime::progress(Deadline deadline){
    auto p=request(channel_,{{"protocol_version",2},{"message_type","reconcile"}},deadline);
    if(rejected(p)){
        validate_response(p,"");
        if(p["code"]=="inactive_source")return p;
        throw Invalid();
    }
    keys(p,{"protocol_version","message_type","source_id","activation_id","state","revision","cursor","boundary_start","boundary_end"});
    if(!p["protocol_version"].is_number_integer()||p["protocol_version"]!=2||p["message_type"]!="progress"||p["source_id"]!=source_||!pilot::uuid_valid(p["activation_id"]))throw Invalid();
    (void)revision(p["revision"]);
    if(!p["cursor"].is_null()){
        if(!p["cursor"].is_string())throw Invalid();
        (void)identity(source_,p["cursor"].get<std::string>());
    }
    if(p["state"]!="initializing"&&p["state"]!="anchored"&&p["state"]!="empty_unanchored")throw Invalid();
    for(auto name:{"boundary_start","boundary_end"}){
        if(p["state"]=="initializing"){if(!p[name].is_null())throw Invalid();}
        else pilot::timestamp_valid(p[name]);
    }
    if(p["state"]=="anchored"&&p["cursor"].is_null())throw Invalid();
    if(p["state"]!="anchored"&&!p["cursor"].is_null())throw Invalid();
    return p;
}
Json ReaderRuntime::exchange(const Json& obj){
    const auto frozen=obj.dump(-1,' ',true)+"\n";
    const auto end=channel_.now()+std::chrono::seconds(30);
    for(unsigned attempt=0;attempt<3&&!channel_.cancelled()&&channel_.now()<end;++attempt){
        if(attempt){
            auto delay=std::chrono::milliseconds(attempt==1?100:500);
            if(channel_.now()+delay>=end)break;
            channel_.sleep(delay);
        }
        try{
            if(!connected_){
                connect(std::min(end,channel_.now()+std::chrono::seconds(5)));
                auto p=progress(std::min(end,channel_.now()+std::chrono::seconds(5)));
                if(rejected(p)||p["activation_id"]!=activation_)throw Invalid("inactive_source");
                // Resume transport, not journal: the pending bytes and observation remain frozen.
            }
            auto response=exchange_line(channel_,frozen,std::min(end,channel_.now()+std::chrono::seconds(5)));
            if(obj["message_type"]=="journal_event"||obj["message_type"]=="journal_rejection"){
                validate_response(response,obj["event_id"].get<std::string>());
                if(response["message_type"]!="ack")throw Invalid("delivery_unconfirmed");
            }
            return response;
        }catch(const Invalid&){throw;}
        catch(...){channel_.close();connected_=false;}
    }
    throw std::runtime_error("delivery_unconfirmed");
}
bool ReaderRuntime::start(){
    if(active_)throw std::runtime_error("already_started");
    try{
        const auto end=channel_.now()+std::chrono::seconds(30);
        bool opened=false;
        for(unsigned i=0;i<3&&!channel_.cancelled()&&channel_.now()<end;++i){
            if(i)channel_.sleep(std::chrono::milliseconds(i==1?100:500));
            if(channel_.now()>=end)break;
            try{connect(std::min(end,channel_.now()+std::chrono::seconds(5)));opened=true;break;}
            catch(const std::system_error& e){
                channel_.close();connected_=false;
                if(e.code().value()==EPERM||e.code().value()==EACCES||e.code().value()==ENOTSUP)throw;
            }
        }
        if(!opened||channel_.cancelled())throw std::runtime_error("startup_cancelled_or_unavailable");
        auto p=progress(std::min(end,channel_.now()+std::chrono::seconds(5)));
        if(rejected(p)){stop();return false;}
        activation_=p["activation_id"].get<std::string>();revision_=revision(p["revision"]);
        Activation a{true,p["state"]!="initializing",source_,activation_,revision_,{}};
        if(!p["cursor"].is_null())a.cursor=p["cursor"].get<std::string>();
        auto started=clock_();pilot::timestamp_valid(started);
        if(channel_.cancelled()){stop();return false;}
        collector_.start(a);
        if(collector_.boundary_pending()){
            if(channel_.cancelled()){stop();return false;}
            auto ended=clock_();pilot::timestamp_valid(ended);
            Json boundary=collector_.boundary()?Json(*collector_.boundary()):Json(nullptr);
            auto ack=exchange({{"protocol_version",2},{"message_type","boundary"},{"cursor",boundary},{"started_at",started},{"ended_at",ended}});
            keys(ack,{"protocol_version","message_type","cursor"});
            if(!ack["protocol_version"].is_number_integer()||ack["protocol_version"]!=2||ack["message_type"]!="boundary_ack"||ack["cursor"]!=boundary)throw Invalid();
            collector_.boundary_committed();
        }
        active_=true;return true;
    }catch(const std::exception& e){
        if(channel_.cancelled()){stop();return false;}
        failure_=std::string(e.what())=="unanchored_restart_gap"?"unanchored_restart_gap":std::string(e.what())=="cursor_gap"?"cursor_gap":"read_failure";
        report_gap(failure_);stop();throw;
    }
}
bool ReaderRuntime::step(){
    bool journal_poll_started=false;
    if(channel_.cancelled()){stop();return false;}
    if(!active_)throw std::runtime_error("not_active");
    try{
        // Revocation and lease check precedes each bounded journal poll.
        auto p=progress(channel_.now()+std::chrono::seconds(5));
        if(rejected(p)||p["activation_id"]!=activation_){stop();return false;}
        if(revision(p["revision"])!=revision_)throw Invalid("stale_revision");
        if(channel_.cancelled()){stop();return false;}
        journal_poll_started=true;
        auto event=collector_.poll_with_observation([&]{
            return Json{{"producer_instance_id",producer_},{"observed_at",clock_()}};
        });
        if(channel_.cancelled()){stop();return false;}
        if(event){
            auto response=exchange(*event);
            const auto next=revision(response["checkpoint_revision"]);
            if(next!=revision_+1)throw Invalid("stale_revision");
            collector_.committed((*event)["event_id"].get<std::string>(),next);revision_=next;
        }
        return true;
    }catch(const std::exception& e){
        if(channel_.cancelled()){stop();return false;}
        if(!journal_poll_started && dynamic_cast<const Invalid*>(&e)==nullptr){
            // A root deactivation closes the lease. Reconcile once without reading
            // the journal to distinguish that from an unexplained interruption.
            try{
                channel_.close();connected_=false;
                connect(channel_.now()+std::chrono::seconds(5));
                auto p=progress(channel_.now()+std::chrono::seconds(5));
                if(rejected(p)||p["activation_id"]!=activation_){stop();return false;}
            }catch(...){/* No new collection on an unexplained failure. */}
        }
        const std::string reason=e.what();
        failure_=reason=="cursor_gap"?"cursor_gap":reason=="delivery_unconfirmed"?"delivery_unconfirmed":"read_failure";
        report_gap(failure_);stop();throw;
    }
}
void ReaderRuntime::report_gap(const std::string& code) noexcept{
    if(activation_.empty()||channel_.cancelled())return;
    try{
        if(!connected_)connect(channel_.now()+std::chrono::seconds(5));
        (void)request(channel_,{{"protocol_version",2},{"message_type","gap"},{"code",code}},channel_.now()+std::chrono::seconds(5));
    }catch(...){/* Local failure code remains available; no durability claim. */}
}
void ReaderRuntime::stop() noexcept{collector_.stop();channel_.close();connected_=false;active_=false;}
}
