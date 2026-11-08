// Test-only lifecycle executable. Fake journal exclusively; never links LinuxJournalIo.
#include "hids/journal/runtime.hpp"
#include <csignal>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <poll.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <thread>
#include <unistd.h>
using namespace hids::journal;
namespace {
volatile std::sig_atomic_t stopping=0;
void stop(int){stopping=1;}
class Socket final:public Channel{
public:
    explicit Socket(std::string path):path_(std::move(path)){}
    ~Socket()override{close();}
    int connect(Deadline end)override{
        close();fd_=socket(AF_UNIX,SOCK_STREAM,0);if(fd_<0)return errno;
        (void)fcntl(fd_,F_SETFD,FD_CLOEXEC);
        sockaddr_un a{};a.sun_family=AF_UNIX;if(path_.size()>=sizeof(a.sun_path))return EINVAL;
        std::memcpy(a.sun_path,path_.c_str(),path_.size()+1);
        if(::connect(fd_,reinterpret_cast<sockaddr*>(&a),sizeof(a)))return errno;
#ifdef __linux__
        ucred peer{};socklen_t size=sizeof(peer);
        if(getsockopt(fd_,SOL_SOCKET,SO_PEERCRED,&peer,&size)||peer.uid!=getuid()||peer.gid!=getgid())return EPERM;
#else
        // macOS fixture seam: production UnixChannel remains Linux-only.
#endif
        if(fcntl(fd_,F_SETFL,O_NONBLOCK)<0)return errno;
        return now()<end?0:ETIMEDOUT;
    }
    ssize_t read(void* p,std::size_t n)override{return recv(fd_,p,n,0);}
    ssize_t write(const void* p,std::size_t n)override{return ::write(fd_,p,n);}
    bool cancelled()const override{return stopping!=0;}
    bool wait(bool writing,Deadline end)override{
        while(!cancelled()&&now()<end){pollfd p{fd_,static_cast<short>(writing?POLLOUT:POLLIN),0};auto rc=poll(&p,1,50);if(rc>0)return true;if(rc<0&&errno!=EINTR)return false;}return false;
    }
    void close()noexcept override{if(fd_>=0)::close(fd_);fd_=-1;}
private:std::string path_;int fd_=-1;
};
class FixtureJournal final:public JournalIo{
public:
    Entry event;std::string mode;unsigned opens=0;bool emitted=false;
    void open()override{++opens;}void filter()override{}
    std::optional<std::string> tail()override{return mode=="empty"?std::nullopt:std::optional<std::string>("baseline");}
    bool seek_exact(const std::string& cursor)override{if(cursor==event.cursor){emitted=true;return true;}return cursor=="baseline";}
    std::optional<Entry> next()override{if(mode!="once"||emitted)return {};emitted=true;return event;}
    int wait(unsigned ms)override{std::this_thread::sleep_for(std::chrono::milliseconds(ms));return 0;}
    void close()noexcept override{}
};
}
int main(int argc,char** argv){
    if(argc!=4||getuid()==0)return 77;
    FixtureJournal journal;journal.mode=argv[3];
    if(journal.mode!="once"&&journal.mode!="empty"&&journal.mode!="idle")return 64;
    try{
        std::signal(SIGINT,stop);std::signal(SIGTERM,stop);std::signal(SIGPIPE,SIG_IGN);
        std::ifstream in(argv[1]);Json f;in>>f;validate(f);
        journal.event.cursor=f["cursor"];journal.event.boot=f["journal"]["boot_id"];journal.event.realtime_us=f["journal"]["realtime_us"];journal.event.monotonic_us=f["journal"]["monotonic_us"];
        for(auto it=f["fields"].begin();it!=f["fields"].end();++it)if(!it.value().is_null())journal.event.fields.emplace_back(it.key(),it.value().get<std::string>());
        Socket channel(argv[2]);ReaderRuntime runtime(journal,channel,f["source_id"],f["observation"]["producer_instance_id"],[]{return std::string("2026-11-07T00:00:00.000000Z");});
        if(!runtime.start()){std::cout<<Json({{"state","inactive"},{"opens",journal.opens}}).dump()<<'\n';return 0;}
        const auto end=std::chrono::steady_clock::now()+std::chrono::seconds(20);
        do{if(!runtime.step())break;if(journal.mode=="once")break;}while(!stopping&&std::chrono::steady_clock::now()<end);
        runtime.stop();std::cout<<Json({{"state","stopped"},{"opens",journal.opens},{"emitted",journal.emitted}}).dump()<<'\n';return 0;
    }catch(const std::exception&){std::cout<<Json({{"state","failed"},{"opens",journal.opens}}).dump()<<'\n';return stopping?0:1;}
}
