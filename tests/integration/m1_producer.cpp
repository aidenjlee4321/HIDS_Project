// Synthetic-only harness executable. Links the parser, never the live backend.
#include "m1_native_fixture.hpp"
#include "hids/pilot/transport.hpp"
#include <cerrno>
#include <csignal>
#include <fstream>
#include <fcntl.h>
#include <iostream>
#include <poll.h>
#include <unistd.h>
#ifdef __linux__
#include <sys/random.h>
#endif

namespace {
volatile std::sig_atomic_t stopped=0;
void signal_stop(int) {stopped=1;}
using namespace hids::pilot;
std::string line(int fd,std::size_t limit) {
    std::string out;const auto deadline=Clock::now()+std::chrono::seconds(120);
    while (!stopped && Clock::now()<deadline) {
        pollfd p{fd,POLLIN,0};
        const int ready=::poll(&p,1,100);
        if (ready<0 && errno==EINTR) continue;
        if (ready<0) throw Invalid("control_failed");
        if (!ready) continue;
        char c{};const auto n=::read(fd,&c,1);
        if (n<0 && errno==EINTR) continue;
        if (n!=1) throw Invalid("control_closed");
        if (c=='\n') return out;
        if (out.size()==limit) throw Invalid("frame_too_large");
        out+=c;
    }
    throw Invalid("control_deadline");
}
void output(int fd,const std::string& data) {
    std::size_t offset=0;const auto deadline=Clock::now()+std::chrono::seconds(5);
    while (offset<data.size() && !stopped && Clock::now()<deadline) {
        pollfd p{fd,POLLOUT,0};const int n=::poll(&p,1,100);
        if (n<0 && errno==EINTR) continue;
        if (n<0) break;
        if (!n) continue;
        const auto wrote=::write(fd,data.data()+offset,data.size()-offset);
        if (wrote<0 && errno==EINTR) continue;
        if (wrote<=0) break;
        offset+=static_cast<std::size_t>(wrote);
    }
    if (offset!=data.size()) throw Invalid("control_write_failed");
}
std::string file(const char* path) {
    std::ifstream in(path,std::ios::binary);if (!in) throw Invalid("fixture_unavailable");
    std::string data(event_limit+1,'\0');in.read(data.data(),data.size());
    data.resize(static_cast<std::size_t>(in.gcount()));
    if (data.size()>event_limit) throw Invalid("frame_too_large");
    return data;
}
std::string random_id() {
#ifdef __linux__
    return uuid_v4([](void* p,std::size_t size) {return ::getrandom(p,size,GRND_NONBLOCK);});
#else
    throw Invalid("linux_random_required");
#endif
}
} // namespace
int main(int argc,char** argv) {
    using namespace hids::pilot;
    if (getuid()==0 || getuid()!=geteuid() || getgid()!=getegid()) return 77;
    if (argc==3 && std::string(argv[1])=="--validate") {
        try {auto j=parse(file(argv[2]),event_limit,true);validate_event(j);std::cout<<"valid\n";return 0;}
        catch (const std::exception& e) {std::cout<<e.what()<<'\n';return 1;}
    }
    if (argc!=5) return 64;
    int control=-1,report=-1;bool transport_started=false,commit_acknowledged=false;
    try {
        control=std::stoi(argv[3]);report=std::stoi(argv[4]);
        if (control<0 || report<0 || control==report) return 64;
        for (int fd : {control,report}) {
            const int flags=fcntl(fd,F_GETFL);
            if (flags<0 || fcntl(fd,F_SETFL,flags|O_NONBLOCK)<0) return 1;
        }
        std::signal(SIGINT,signal_stop);std::signal(SIGTERM,signal_stop);std::signal(SIGPIPE,SIG_IGN);
        const auto first=parse(line(control,response_limit),response_limit);
        if (first.size()!=1 || !first.contains("command")) throw Invalid("bad_control");
        std::string frozen;
        if (first["command"]=="prepare") {
            const auto native=decode_fixture(parse(file(argv[1]),event_limit,true));
            frozen=prepare_line(native,utc_now,random_id);
        } else if (first["command"]=="restore") {
            frozen=line(control,event_limit)+"\n";
            validate_event(parse(std::string_view(frozen).substr(0,frozen.size()-1)));
        } else throw Invalid("bad_control");
        if (frozen.size()>event_limit+1) throw Invalid("frame_too_large");
        output(report,Json({{"stage","prepared"}}).dump()+"\n");
        output(report,frozen);
        bool uncertain=false,acknowledged=false;unsigned operations=0;
        while (!stopped) {
            const auto command=parse(line(control,response_limit),response_limit);
            if (command.size()==1 && command.value("command","")=="stop") return 0;
            if (operations>=2 || acknowledged || command.size()!=2 || command.value("command","")!="send" ||
                !command.contains("receiver_pid") || !command["receiver_pid"].is_number_integer()) throw Invalid("bad_control");
            const auto pid=command["receiver_pid"].get<std::int64_t>();
            if (pid<=0 || pid>2147483647) throw Invalid("bad_control");
            ++operations;
            UnixChannel channel(argv[2],static_cast<int>(pid),[] {return stopped!=0;});
            transport_started=true;
            const auto result=transmit(channel,frozen,uncertain);
            uncertain=result.outcome=="unconfirmed";
            acknowledged=result.outcome=="acknowledged";
            commit_acknowledged=acknowledged;
            output(report,Json({{"outcome",result.outcome},{"code",result.code},{"attempts",result.attempts},{"any_sent",result.any_sent}}).dump()+"\n");
            if (acknowledged) frozen.clear();
        }
        return 1;
    } catch (const std::exception& e) {
        if (report>=0 && !stopped) {
            const std::string reason=e.what();
            const bool known=reason=="observation_clock_failed" || reason=="uuid_generation_failed" || reason=="native_fixture_failed" || reason=="serialization_failed";
            try {output(report,Json({{"outcome",commit_acknowledged?"acknowledged":transport_started?"unconfirmed":"local_failure"},
                {"code",commit_acknowledged?"persistence_confirmed":transport_started?"delivery_unconfirmed":"not_submitted"},
                {"reason",known?reason:"local_preparation_failed"}}).dump()+"\n");}
            catch (...) {}
        }
        return 1;
    }
}
