#include "hids/journal_collector.hpp"
#include "hids/journal/transport.hpp"
#include <cassert>
#include <fstream>
#include <iostream>
#include <deque>
#include <type_traits>
static_assert(!std::is_copy_constructible_v<hids::journal::LinuxJournalIo>);
static_assert(!std::is_copy_constructible_v<hids::journal::UnixChannel>);
using namespace hids::journal;
struct FakeJournal final:JournalIo {
    unsigned opens=0,reads=0,closes=0;bool exact=true;int changed=0;
    std::optional<std::string> baseline="baseline";std::deque<Entry> entries;
    void open()override{++opens;}void filter()override{}
    std::optional<std::string> tail()override{return baseline;}
    bool seek_exact(const std::string&)override{return exact;}
    std::optional<Entry> next()override{++reads;if(entries.empty())return {};auto e=entries.front();entries.pop_front();return e;}
    int wait(unsigned ms)override{assert(ms<=100);return changed;}
    void close()noexcept override{++closes;}
};
struct Filter final:MatchIo {
    std::vector<std::string> calls;
    void match(std::string_view s)override{calls.emplace_back(s);}void disjunction()override{calls.emplace_back("OR");}
};
struct FakeChannel final:Channel {
    std::string response,sent;std::size_t pos=0;unsigned connections=0;int fail=0;Deadline time{};
    int connect(Deadline)override{++connections;pos=0;return fail;}
    ssize_t write(const void* p,std::size_t n)override{auto count=std::min<std::size_t>(n,7);sent.append(static_cast<const char*>(p),count);return static_cast<ssize_t>(count);}
    ssize_t read(void* p,std::size_t)override{if(pos==response.size())return 0;*static_cast<char*>(p)=response[pos++];return 1;}
    bool wait(bool,Deadline)override{return true;}void close()noexcept override{}
    Deadline now()const override{return time;}void sleep(std::chrono::milliseconds ms)override{time+=ms;}
};
int main(int argc,char** argv){
    assert(argc==3);std::ifstream input(argv[1]),corpus_file(argv[2]);Json base;input>>base;Json corpus;corpus_file>>corpus;
    validate(base);
    for(const auto& item:corpus){std::string result="valid";try{validate(parse(item.at("input").get<std::string>()));}catch(const Invalid& e){result=e.what();}
        if(result!=item.at("expected").get<std::string>()){std::cerr<<item.at("name")<<" got "<<result<<'\n';return 1;}}
    Filter f;ssh_filter(f);assert((f.calls==std::vector<std::string>{"_COMM=sshd-session","_EXE=/usr/lib/openssh/sshd-session","OR","_COMM=sshd","_EXE=/usr/sbin/sshd"}));
    Entry native;native.cursor=base["cursor"];native.boot=base["journal"]["boot_id"];native.realtime_us=base["journal"]["realtime_us"];native.monotonic_us=base["journal"]["monotonic_us"];
    for(auto it=base["fields"].begin();it!=base["fields"].end();++it)if(!it.value().is_null())native.fields.emplace_back(it.key(),it.value().get<std::string>());
    assert(normalize(native,base["source_id"],base["activation_id"],0,base["observation"])==base);
    auto bad=native;bad.fields.emplace_back("MESSAGE","duplicate");assert(normalize(bad,base["source_id"],base["activation_id"],0,base["observation"])["reason"]=="duplicate_field");
    bad=native;bad.fields.emplace_back("MESSAGE",std::string(5000,'x'));assert(normalize(bad,base["source_id"],base["activation_id"],0,base["observation"])["message_type"]=="journal_rejection");
    auto changed=base;changed["observation"]["observed_at"]="2026-11-07T00:00:01.000000Z";assert(canonical(base)==canonical(changed));
    FakeJournal io;JournalCollector c(io);Activation a{false,false,base["source_id"],base["activation_id"],0,{}};
    try{c.start(a);assert(false);}catch(const std::runtime_error&){}assert(io.opens==0);
    a.authorized=true;c.start(a);assert(c.boundary_pending());
    try{(void)c.poll_once(base["observation"]);assert(false);}catch(const std::runtime_error&){}assert(io.reads==0);
    io.entries.push_back(native); // Append while durable boundary ACK is outstanding.
    c.boundary_committed();assert(c.poll_once(base["observation"]).value()==base);
    auto reads=io.reads;assert(c.poll_once(changed["observation"]).value()==base&&io.reads==reads); // Frozen pending.
    c.committed(base["event_id"].get<std::string>(),1);io.changed=2;io.exact=false;
    try{(void)c.poll_once(base["observation"]);assert(false);}catch(const std::runtime_error&){}assert(!c.running());
    a.initialized=true;a.cursor.reset();try{c.start(a);assert(false);}catch(const std::runtime_error& e){assert(std::string(e.what())=="unanchored_restart_gap");}
    a.cursor="saved-equivalent-token";io.exact=true;c.start(a);assert(!c.boundary_pending());c.stop();
    Json ack={{"protocol_version",2},{"message_type","ack"},{"event_id",base["event_id"]},{"result","stored"},{"checkpoint_revision",1},{"code",nullptr}};
    FakeChannel channel;channel.response=ack.dump()+"\n";auto line=base.dump()+"\n";auto result=hids::journal::transmit(channel,line);assert(result.outcome=="acknowledged"&&channel.sent==line);
    channel.response="{\"malformed\":true}\n";result=hids::journal::transmit(channel,line);assert(result.outcome=="unconfirmed"&&result.attempts==1);
    channel.response.clear();result=hids::journal::transmit(channel,line);assert(result.outcome=="unconfirmed"&&result.attempts==3);
    channel.fail=EPERM;result=hids::journal::transmit(channel,line);assert(result.outcome=="local_failure"&&result.attempts==1);
    std::cout<<"PASS: "<<corpus.size()<<" M2 vectors; SSH filter pairs/AND/OR; native normalization, activation, pending identity, cursor gaps, transport\n";
}
