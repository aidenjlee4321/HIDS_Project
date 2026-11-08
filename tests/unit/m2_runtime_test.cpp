#include "hids/journal/runtime.hpp"
#include <cassert>
#include <deque>
#include <cstring>
#include <fstream>
#include <iostream>
using namespace hids::journal;
struct Backend final:Channel {
    Json fixture;
    bool active=true,initialized=false,cancel=false,lose_ack=false,bad_ack=false,slow=false;
    std::string cursor="baseline",input,output;std::size_t offset=0;
    std::uint64_t rev=0;unsigned opens=0,events=0,gaps=0;
    Deadline time{};
    std::function<void()> boundary_hook=[]{};
    std::vector<std::string> deliveries;
    explicit Backend(Json f):fixture(std::move(f)){}
    int connect(Deadline)override{++opens;input.clear();output.clear();offset=0;return 0;}
    bool cancelled()const override{return cancel;}
    void close()noexcept override{input.clear();output.clear();offset=0;}
    Deadline now()const override{return time;}
    void sleep(std::chrono::milliseconds ms)override{time+=ms;}
    bool wait(bool,Deadline end)override{time=end;return false;}
    ssize_t write(const void* raw,std::size_t n)override{
        if(slow){errno=EAGAIN;return -1;}
        const auto* p=static_cast<const char*>(raw);
        for(std::size_t i=0;i<n;++i){
            if(p[i]!='\n'){input+=p[i];continue;}
            Json req=parse(input);const std::string bytes=input;input.clear();Json response;
            if(!active)response={{"protocol_version",2},{"message_type","reject"},{"event_id",nullptr},{"code","inactive_source"}};
            else if(req["message_type"]=="reconcile")response={{"protocol_version",2},{"message_type","progress"},{"source_id",fixture["source_id"]},{"activation_id",fixture["activation_id"]},{"state",initialized?(cursor.empty()?"empty_unanchored":"anchored"):"initializing"},{"revision",rev},{"cursor",initialized&&!cursor.empty()?Json(cursor):Json(nullptr)},{"boundary_start",initialized?Json("2026-11-07T00:00:00.000000Z"):Json(nullptr)},{"boundary_end",initialized?Json("2026-11-07T00:00:00.000000Z"):Json(nullptr)}};
            else if(req["message_type"]=="boundary"){
                initialized=true;cursor=req["cursor"].is_null()?"":req["cursor"].get<std::string>();
                response={{"protocol_version",2},{"message_type","boundary_ack"},{"cursor",req["cursor"]}};
                boundary_hook();
            }else if(req["message_type"]=="gap"){++gaps;response={{"protocol_version",2},{"message_type","gap_ack"},{"code",req["code"]}};}
            else{
                validate(req);deliveries.push_back(bytes);++events;
                const bool duplicate=rev>0;
                if(!duplicate){rev=1;cursor=req["cursor"].get<std::string>();}
                response={{"protocol_version",2},{"message_type","ack"},{"event_id",req["event_id"]},{"result",duplicate?"duplicate":"stored"},{"checkpoint_revision",rev},{"code",nullptr}};
                if(lose_ack){lose_ack=false;output.clear();offset=0;continue;}
                if(bad_ack)response["result"]="unknown";
            }
            output=response.dump()+"\n";offset=0;
        }
        return static_cast<ssize_t>(n);
    }
    ssize_t read(void* raw,std::size_t max)override{
        auto n=std::min(max,output.size()-offset);if(!n)return 0;
        std::memcpy(raw,output.data()+offset,n);offset+=n;return static_cast<ssize_t>(n);
    }
};
struct Journal final:JournalIo {
    unsigned opens=0,reads=0,closes=0;bool exact=true;int change=0;
    std::optional<std::string> baseline="baseline";std::deque<Entry> entries;
    std::function<void()> on_wait=[]{};
    void open()override{++opens;}void filter()override{}
    std::optional<std::string> tail()override{return baseline;}
    bool seek_exact(const std::string&)override{return exact;}
    std::optional<Entry> next()override{++reads;if(entries.empty())return {};auto e=entries.front();entries.pop_front();return e;}
    int wait(unsigned ms)override{assert(ms<=100);on_wait();return change;}
    void close()noexcept override{++closes;}
};
Entry native(const Json& f){
    Entry e;e.cursor=f["cursor"];e.boot=f["journal"]["boot_id"];e.realtime_us=f["journal"]["realtime_us"];e.monotonic_us=f["journal"]["monotonic_us"];
    for(auto it=f["fields"].begin();it!=f["fields"].end();++it)if(!it.value().is_null())e.fields.emplace_back(it.key(),it.value().get<std::string>());
    return e;
}
int main(int argc,char** argv){
    assert(argc==2);std::ifstream in(argv[1]);Json f;in>>f;
    const auto source=f["source_id"].get<std::string>(),producer=f["observation"]["producer_instance_id"].get<std::string>();
    auto clock=[] {return std::string("2026-11-07T00:00:00.000000Z");};
    {Backend b(f);b.active=false;Journal j;ReaderRuntime r(j,b,source,producer,clock);assert(!r.start());assert(j.opens==0&&j.reads==0);}
    {Backend b(f);Journal j;j.entries.push_back(native(f));ReaderRuntime r(j,b,source,producer,clock);assert(r.start());assert(r.step());assert(b.rev==1);r.stop();assert(j.closes>0);}
    {Backend b(f);b.lose_ack=true;Journal j;j.entries.push_back(native(f));ReaderRuntime r(j,b,source,producer,clock);assert(r.start());assert(r.step());assert(b.rev==1&&b.events==2&&b.deliveries[0]==b.deliveries[1]);}
    {Backend b(f);Journal j;j.baseline.reset();ReaderRuntime r(j,b,source,producer,clock);assert(r.start());r.stop();Journal restarted;ReaderRuntime next(restarted,b,source,producer,clock);try{next.start();assert(false);}catch(const std::runtime_error&){}assert(restarted.opens==0&&b.gaps==1);}
    {Backend b(f);b.initialized=true;Journal j;j.exact=false;ReaderRuntime r(j,b,source,producer,clock);try{r.start();assert(false);}catch(const std::runtime_error&){}assert(b.gaps==1);}
    {Backend b(f);Journal j;ReaderRuntime r(j,b,source,producer,clock);assert(r.start());auto reads=j.reads;b.active=false;assert(!r.step());assert(j.reads==reads);}
    {Backend b(f);Journal j;j.on_wait=[&]{b.cancel=true;};ReaderRuntime r(j,b,source,producer,clock);assert(r.start());assert(!r.step());assert(!j.opens||j.closes>0);assert(b.events==0);}
    {Backend b(f);Journal j;b.boundary_hook=[&]{b.cancel=true;};ReaderRuntime r(j,b,source,producer,clock);assert(!r.start());assert(j.reads==0&&b.events==0);}
    {Backend b(f);b.bad_ack=true;Journal j;j.entries.push_back(native(f));ReaderRuntime r(j,b,source,producer,clock);assert(r.start());try{r.step();assert(false);}catch(const Invalid&){}assert(b.events==1);}
    {Backend b(f);Journal j;ReaderRuntime r(j,b,source,producer,clock);assert(r.start());j.change=2;j.exact=false;try{r.step();assert(false);}catch(const std::runtime_error&){}assert(b.gaps==1);}
    {Backend b(f);Journal j;ReaderRuntime r(j,b,source,producer,clock);assert(r.start());b.slow=true;try{r.step();assert(false);}catch(const std::runtime_error&){}assert(j.reads==0);assert(b.time==Deadline{}+std::chrono::seconds(15)); // heartbeat, revocation reconciliation, gap report: three bounded stages.
    }
    std::cout<<"PASS: reader lifecycle denial/start/boundary/cancel/revocation/empty/restart/rotation/lost ACK/slow peer\n";
}
