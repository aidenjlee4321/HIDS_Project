#include "hids/pilot/contract.hpp"
#include "hids/pilot/transport.hpp"
#include <cassert>
#include <cerrno>
#include <cstring>
#include <deque>
#include <fstream>
#include <iostream>
using namespace hids::pilot;

struct Fake final : Channel {
    Deadline time{};int connections=0,fail_connect=0;
    unsigned waits=0;bool short_io=false,interrupt=false,would_block=false;
    int connect_ms=0,write_ms=0;bool deadline_reads=false;
    bool read_interrupt=false,read_block=false;
    std::string response,written;std::size_t pos=0;
    Deadline now() const override {return time;}
    void sleep(std::chrono::milliseconds ms) override {time+=ms;}
    int connect(Deadline) override {++connections;pos=0;time+=std::chrono::milliseconds(connect_ms);return fail_connect;}
    void close() noexcept override {}
    bool wait(bool writing,Deadline d) override {
        ++waits;
        if (deadline_reads && !writing) {time=d;return false;}
        time=std::min(d,time+std::chrono::milliseconds(1));return true;
    }
    ssize_t write(const void* p,std::size_t n) override {
        if (interrupt) {interrupt=false;errno=EINTR;return -1;}
        if (would_block) {would_block=false;errno=EAGAIN;return -1;}
        time+=std::chrono::milliseconds(write_ms);
        const auto count=short_io?std::min<std::size_t>(n,3):n;
        written.append(static_cast<const char*>(p),count);return static_cast<ssize_t>(count);
    }
    ssize_t read(void* p,std::size_t n) override {
        if (read_interrupt) {read_interrupt=false;errno=EINTR;return -1;}
        if (read_block) {read_block=false;errno=EAGAIN;return -1;}
        if (pos==response.size()) {if (deadline_reads) {errno=EAGAIN;return -1;} return 0;}
        const auto count=std::min(n,response.size()-pos);
        std::memcpy(p,response.data()+pos,count);pos+=count;return static_cast<ssize_t>(count);
    }
};
template<class F> void bad(F f) {bool failed=false;try {f();} catch (const std::exception&) {failed=true;} assert(failed);}
int main(int argc,char** argv) {
    assert(argc==2 || argc==3);
    std::ifstream input(argv[1]);std::string raw((std::istreambuf_iterator<char>(input)),{});
    auto base=parse(raw,event_limit,true);validate_event(base);
    const auto id=base["event_id"].get<std::string>();
    for (const auto* key : {"protocol_version","message_type","contract_version","ecs_reference_version","event_id","producer_instance_id","source","native","timestamps"}) {
        auto j=base;j.erase(key);bad([&] {validate_event(j);});
    }
    for (const auto& wrong : {Json(true),Json(1.0),Json("1"),Json(nullptr)}) {
        auto j=base;j["protocol_version"]=wrong;bad([&] {validate_event(j);});
    }
    for (const auto* text : {"", "{}\n", "{\"a\":1,\"a\":2}", "{\"a\":1,\"\\u0061\":2}", "{\"a\":NaN}", "{} {}", "[]"}) bad([&] {parse(text);});
    auto t=base;t["native"]["timestamp_ns"]="18446744073709551615";validate_event(t);
    t["native"]["timestamp_ns"]="18446744073709551616";bad([&] {validate_event(t);});
    t=base;t["native"]["pid"]=true;bad([&] {validate_event(t);});
    t=base;t["native"]["pid"]=7;t["native"]["tgid"]=8;t["native"]["cpu"]=0;t["native"]["connector_sequence"]=0;validate_event(t);
    for (const auto* date : {"0000-01-01T00:00:00.000000Z","2026-02-29T00:00:00.000000Z","2026-01-01T00:00:60.000000Z"}) bad([&] {timestamp_valid(date);});
    timestamp_valid("2000-02-29T00:00:00.000000Z");
    timestamp_valid(utc_now());
    unsigned calls=0;
    const auto generated=uuid_v4([&](void* p,std::size_t n)->ssize_t {
        if (++calls==1) {errno=EINTR;return -1;}
        const auto size=std::min<std::size_t>(3,n);std::memset(p,0,size);return static_cast<ssize_t>(size);
    });assert(uuid_valid(generated) && calls>2);
    for (const int error : {EAGAIN,EIO}) bad([&] {uuid_v4([&](void*,std::size_t)->ssize_t {errno=error;return -1;});});
    bad([] {uuid_v4([](void*,std::size_t)->ssize_t {return 0;});});
    unsigned partial_calls=0;
    bad([&] {uuid_v4([&](void* p,std::size_t)->ssize_t {
        if (++partial_calls==1) {std::memset(p,0,4);return 4;}
        errno=EIO;return -1;
    });});assert(partial_calls==2);
    hids::process::NativeEvent native{};native.kind=hids::process::Lifecycle::executed;native.tid=4242;native.tgid=4242;
    unsigned identifiers=0;
    const auto ids=[&] {++identifiers;return id;};
    bad([&] {prepare_line(native,[]()->std::string {throw std::runtime_error("clock");},ids);});
    assert(identifiers==0);
    bad([&] {prepare_line(native,[] {return std::string("invalid");},ids);});assert(identifiers==0);
    const auto clock=[] {return std::string("2026-11-07T20:00:00.000000Z");};
    bad([&] {prepare_line(native,clock,ids,[](const Json&)->std::string {throw std::runtime_error("serialize");});});
    native.kind=hids::process::Lifecycle::forked;bad([&] {prepare_line(native,clock,ids);});
    for (const auto* type : {"ack","reject","error"}) {
        Json r={{"protocol_version",1},{"message_type",type},{"event_id",id}};
        if (std::string(type)=="ack") r["result"]="stored";
        else r["code"]=std::string(type)=="reject"?"id_conflict":"storage_error";
        validate_response(r,id);
        for (const auto* field : {"protocol_version","message_type","event_id"}) {auto x=r;x.erase(field);bad([&] {validate_response(x,id);});}
        auto x=r;x["extra"]=0;bad([&] {validate_response(x,id);});
        x=r;x["protocol_version"]=true;bad([&] {validate_response(x,id);});
        x=r;x[std::string(type)=="ack"?"result":"code"]="unknown";bad([&] {validate_response(x,id);});
        x=r;x["event_id"]=nullptr;
        if (std::string(type)=="reject") validate_response(x,id);else bad([&] {validate_response(x,id);});
        x=r;x["event_id"]="15729e8d-54b8-4cd0-a74f-09e7492ad870";bad([&] {validate_response(x,id);});
    }
    const Json ack={{"protocol_version",1},{"message_type","ack"},{"event_id",id},{"result","stored"}};
    Fake io;io.response=ack.dump()+"\n";io.short_io=true;io.interrupt=true;io.would_block=true;
    auto delivery=transmit(io,base.dump()+"\n");assert(delivery.outcome=="acknowledged" && io.written==base.dump()+"\n" && io.waits==1);
    Fake interrupted_read;interrupted_read.response=ack.dump()+"\n";interrupted_read.read_interrupt=true;interrupted_read.read_block=true;
    delivery=transmit(interrupted_read,base.dump()+"\n");assert(delivery.outcome=="acknowledged" && interrupted_read.waits==1);
    Fake unavailable;unavailable.fail_connect=ECONNREFUSED;
    delivery=transmit(unavailable,base.dump()+"\n");assert(delivery.outcome=="local_failure" && delivery.attempts==3 && unavailable.time==Deadline{}+std::chrono::milliseconds(600));
    Fake denied;denied.fail_connect=EPERM;delivery=transmit(denied,base.dump()+"\n");assert(delivery.outcome=="local_failure" && delivery.code=="not_submitted" && delivery.attempts==1);
    Fake lost;delivery=transmit(lost,base.dump()+"\n");assert(delivery.outcome=="unconfirmed" && delivery.attempts==3);
    Fake malformed;malformed.response="{}\n";delivery=transmit(malformed,base.dump()+"\n");assert(delivery.outcome=="unconfirmed" && delivery.attempts==1);
    for (const auto& raw_response : {std::string("{\n"),std::string("{\"v\":\"\xff\"}\n"),std::string("{\"protocol_version\":1,\"protocol_version\":1}\n")}) {
        Fake invalid;invalid.response=raw_response;delivery=transmit(invalid,base.dump()+"\n");
        assert(delivery.code=="response_protocol_error" && delivery.attempts==1);
    }
    Fake oversized;oversized.response=std::string(response_limit+1,'x')+"\n";
    delivery=transmit(oversized,base.dump()+"\n");assert(delivery.code=="response_protocol_error" && delivery.attempts==1);
    Fake exact;exact.response=ack.dump()+"\n";
    const auto padded=base.dump()+std::string(event_limit-base.dump().size(),' ')+"\n";
    delivery=transmit(exact,padded);assert(delivery.outcome=="acknowledged" && exact.written.size()==event_limit+1);
    Fake exact_response;exact_response.response=ack.dump()+std::string(response_limit-ack.dump().size(),' ')+"\n";
    delivery=transmit(exact_response,base.dump()+"\n");assert(delivery.outcome=="acknowledged");
    Fake too_big;delivery=transmit(too_big,padded+" ");assert(delivery.outcome=="local_failure" && delivery.attempts==0);
    Fake slow;slow.connect_ms=5000;slow.write_ms=5000;slow.deadline_reads=true;
    delivery=transmit(slow,base.dump()+"\n");assert(delivery.outcome=="unconfirmed" && delivery.attempts==2 && slow.time==Deadline{}+std::chrono::seconds(30));
    Fake rejected;rejected.response=Json({{"protocol_version",1},{"message_type","reject"},{"event_id",nullptr},{"code","invalid_event"}}).dump()+"\n";
    delivery=transmit(rejected,base.dump()+"\n");assert(delivery.outcome=="rejected" && delivery.attempts==1);
    delivery=transmit(rejected,base.dump()+"\n",true);assert(delivery.outcome=="unconfirmed");
    if (argc==3) {
        std::ifstream vectors(argv[2]);const auto corpus=Json::parse(vectors);
        for (const auto& item : corpus) {
            std::string outcome="valid";
            try {validate_event(parse(item.at("input").get<std::string>()));}
            catch (const Invalid& e) {outcome=e.what();}
            if (outcome!=item.at("expected").get<std::string>()) {
                std::cerr<<"FAIL corpus "<<item.at("name")<<" got "<<outcome<<'\n';return 1;
            }
        }
        std::cout<<"PASS: "<<corpus.size()<<" shared contract vectors\n";
    }
    std::cout<<"PASS: M1 C++ contract, responses, calendar, UUID partial/EINTR/failure, short I/O and bounded retry\n";
}
