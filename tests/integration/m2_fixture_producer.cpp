// Synthetic fixtures only. Inherited private socketpair supplied by test harness;
// never constructs LinuxJournalIo or opens any journal/netlink source.
#include "hids/journal_collector.hpp"
#include "hids/journal/transport.hpp"
#include <charconv>
#include <csignal>
#include <fstream>
#include <iostream>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>
using namespace hids::journal;
class FixtureChannel final:public Channel {
public:
    explicit FixtureChannel(int fd):fd_(fd){}
    int connect(Deadline)override{return 0;}
    ssize_t write(const void* p,std::size_t n)override{return ::write(fd_,p,n);}
    ssize_t read(void* p,std::size_t n)override{return ::read(fd_,p,n);}
    bool wait(bool writing,Deadline end)override{
        while(now()<end){pollfd p{fd_,static_cast<short>(writing?POLLOUT:POLLIN),0};if(::poll(&p,1,100)>0)return true;}return false;
    }
    void close()noexcept override{}
private:int fd_;
};
int main(int argc,char** argv){
    try{
        if(argc!=3||getuid()==0)return 77;
        int fd=-1;auto parsed=std::from_chars(argv[2],argv[2]+std::char_traits<char>::length(argv[2]),fd);
        if(parsed.ec!=std::errc{}||*parsed.ptr!='\0'||fd<0)return 64;
        std::signal(SIGPIPE,SIG_IGN);
        std::ifstream input(argv[1]);Json source;input>>source;validate(source);
        Entry e;e.cursor=source["cursor"];e.boot=source["journal"]["boot_id"];e.realtime_us=source["journal"]["realtime_us"];e.monotonic_us=source["journal"]["monotonic_us"];
        for(auto it=source["fields"].begin();it!=source["fields"].end();++it)if(!it.value().is_null())e.fields.emplace_back(it.key(),it.value().get<std::string>());
        auto normalized=normalize(e,source["source_id"],source["activation_id"],source["expected_revision"].get<std::uint64_t>(),source["observation"]);
        FixtureChannel io(fd);auto response=request(io,normalized,io.now()+std::chrono::seconds(5));
        validate_response(response,normalized["event_id"].get<std::string>());
        if(response["message_type"]!="ack")return 1;
        std::cout<<response.dump()<<'\n';return 0;
    }catch(const std::exception& e){std::cerr<<"synthetic_fixture_failure: "<<e.what()<<'\n';return 1;}
}
