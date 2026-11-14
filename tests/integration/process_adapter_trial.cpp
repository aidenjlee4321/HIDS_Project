// Test-only native adapter trial. Default mode uses doubles and opens no source.
// Live mode requires the reviewed account AND a fresh root-private write-only FD.
#include "hids/linux_process_connector.hpp"
#include <array>
#include <cassert>
#include <cerrno>
#include <charconv>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <fcntl.h>
#include <limits>
#include <optional>
#include <pwd.h>
#include <sstream>
#include <string>
#include <string_view>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>
#include <fstream>

using namespace hids::process;
namespace {
volatile std::sig_atomic_t cancelled=0;
void cancel(int) { cancelled=1; }
struct Capture final : Sink {
    int owned=0;
    std::array<NativeEvent,8> events{};
    std::size_t count=0;
    bool overflow=false;
    std::array<std::uint64_t,64> reasons{};
    std::array<int,64> last_errno{};
    Status latest{};
    void on_event(const NativeEvent& event) noexcept override {
        if (owned<=0 || event.tid!=owned || event.tgid!=owned) return;
        if (count==events.size()) { overflow=true; return; }
        events[count++]=event;
    }
    void on_diagnostic(const Diagnostic& value) noexcept override {
        const auto index=static_cast<std::size_t>(value.reason);
        if(index<reasons.size()) {
            if(reasons[index]!=std::numeric_limits<std::uint64_t>::max()) ++reasons[index];
            if(value.error>0)last_errno[index]=value.error;
        }
        // Native CPU/sequence payloads from unrelated traffic are not retained.
        // Typed errno values are bounded diagnostics, never raw event text.
    }
    void on_status(const Status& value) noexcept override { latest=value; }
    bool lifecycle() const noexcept {
        bool fork=false,exec=false,exit=false;
        for(std::size_t i=0;i<count;++i) {
            fork|=events[i].kind==Lifecycle::forked;
            exec|=events[i].kind==Lifecycle::executed;
            exit|=events[i].kind==Lifecycle::exited;
        }
        return fork&&exec&&exit&&!overflow;
    }
};
struct TracedIo final : ConnectorIo {
    ConnectorIo& inner;
    unsigned opens=0,sends=0,closes=0;
    int open_error=0,listen_error=0,ignore_error=0,close_error=0;
    explicit TracedIo(ConnectorIo& io):inner(io){}
    OpenResult open() noexcept override { ++opens;const auto value=inner.open();open_error=value.error;return value; }
    int send(std::span<const std::byte> bytes) noexcept override {
        const int error=inner.send(bytes);++sends;
        if(sends==1)listen_error=error;else ignore_error=error;
        return error;
    }
    ReadResult receive(std::span<std::byte> bytes,std::chrono::milliseconds timeout) noexcept override { return inner.receive(bytes,timeout); }
    int close() noexcept override { ++closes;close_error=inner.close();return close_error; }
};
const char* kind(Lifecycle value) {
    switch(value) {case Lifecycle::forked:return "fork";case Lifecycle::executed:return "exec";case Lifecycle::exited:return "exit";}
    return "unknown";
}
std::string report(const Capture& capture,const Status& before,const TracedIo& io,bool observed,int child_status,bool forced) {
    std::ostringstream out;
    out<<"{\"format\":\"hids.process-adapter-trial/1\",\"owned_lifecycle_observed\":"<<(observed?"true":"false")
       <<",\"activity_wall_time\":null,\"normalization\":\"not_performed\",\"subscription_acknowledged\":"<<(before.subscription_acknowledged?"true":"false")
       <<",\"any_delivery_observed\":"<<(before.delivery_observed?"true":"false")<<",\"incomplete_interval\":"<<(capture.latest.incomplete_interval?"true":"false")
       <<",\"capture_overflow\":"<<(capture.overflow?"true":"false")<<",\"child_wait_status\":"<<child_status<<",\"child_cleanup_forced\":"<<(forced?"true":"false")
       <<",\"open_calls\":"<<io.opens<<",\"control_send_calls\":"<<io.sends<<",\"close_calls\":"<<io.closes
       <<",\"open_errno\":"<<io.open_error<<",\"listen_send_errno\":"<<io.listen_error<<",\"ignore_send_errno\":"<<io.ignore_error<<",\"close_errno\":"<<io.close_error
       <<",\"ignore_completion\":\"unconfirmed\",\"events\":[";
    for(std::size_t i=0;i<capture.count;++i) {
        if(i)out<<',';
        const auto& e=capture.events[i];
        out<<"{\"kind\":\""<<kind(e.kind)<<"\",\"tid\":"<<e.tid<<",\"tgid\":"<<e.tgid<<",\"parent\":";
        if(e.parent)out<<"{\"tid\":"<<e.parent->tid<<",\"tgid\":"<<e.parent->tgid<<'}';else out<<"null";
        out<<",\"cpu\":"<<e.cpu<<",\"sequence\":"<<e.sequence<<",\"kernel_monotonic_ns\":\""<<e.kernel_monotonic_ns<<"\",\"native_exit_status\":";
        if(e.native_exit_status)out<<*e.native_exit_status;else out<<"null";
        out<<",\"native_exit_signal\":";
        if(e.native_exit_signal)out<<*e.native_exit_signal;else out<<"null";
        out<<'}';
    }
    out<<"],\"diagnostic_counts\":[";
    for(std::size_t i=0;i<capture.reasons.size();++i) { if(i)out<<',';out<<capture.reasons[i]; }
    out<<"],\"diagnostic_last_errno\":[";
    for(std::size_t i=0;i<capture.last_errno.size();++i) {if(i)out<<',';out<<capture.last_errno[i];}
    out<<"]}";return out.str();
}
struct FakeIo final : ConnectorIo {
    int send_error=0;
    OpenResult open() noexcept override { return {0,1234}; }
    int send(std::span<const std::byte>) noexcept override { return send_error; }
    ReadResult receive(std::span<std::byte>,std::chrono::milliseconds) noexcept override { return {ReadKind::timeout}; }
    int close() noexcept override { return 0; }
};
NativeEvent event(int pid,Lifecycle value) {
    return {value,pid,pid,{},0,1,std::uint64_t{1}<<63,{},{}};
}
bool private_grant(const struct stat& s,int flags,off_t position) {
    return S_ISREG(s.st_mode)&&s.st_uid==0&&s.st_nlink==1&&(s.st_mode&07777)==0600&&s.st_size==0&&
           (flags&O_ACCMODE)==O_WRONLY&&position==0;
}
int self_test() {
    Capture sink;
    sink.on_event(event(12,Lifecycle::executed));assert(sink.count==0);
    sink.owned=15;sink.on_event(event(12,Lifecycle::executed));assert(sink.count==0);
    auto thread=event(16,Lifecycle::executed);thread.tgid=15;sink.on_event(thread);assert(sink.count==0);
    sink.on_event(event(15,Lifecycle::forked));sink.on_event(event(15,Lifecycle::executed));assert(!sink.lifecycle());
    sink.on_event(event(15,Lifecycle::exited));assert(sink.lifecycle());
    FakeIo fake;TracedIo traced(fake);
    { Collector collector(traced,sink);assert(collector.start());collector.poll_once();collector.stop();collector.stop(); }
    assert(traced.opens==1&&traced.sends==2&&traced.closes==1);
    const auto encoded=report(sink,sink.latest,traced,true,0,false);
    assert(encoded.find("\"kernel_monotonic_ns\":\"9223372036854775808\"")!=std::string::npos);
    assert(encoded.find("\"activity_wall_time\":null")!=std::string::npos);
    assert(encoded.find("\"parent\":null")!=std::string::npos);
    for(unsigned i=0;i<8;++i)sink.on_event(event(15,Lifecycle::exited));
    assert(sink.count==8&&sink.overflow&&!sink.lifecycle());
    struct stat s{};s.st_mode=S_IFREG|0600;s.st_uid=0;s.st_nlink=1;
    assert(private_grant(s,O_WRONLY,0));assert(!private_grant(s,O_RDWR,0));assert(!private_grant(s,O_WRONLY,1));
    s.st_uid=1000;assert(!private_grant(s,O_WRONLY,0));s.st_uid=0;s.st_mode=S_IFREG|0644;assert(!private_grant(s,O_WRONLY,0));
    std::puts("process adapter trial: 12 offline invariant groups passed");return 0;
}
bool credentials() {
    const passwd* role=getpwnam("hids-process");
    if(!role||role->pw_uid==0||role->pw_gid==0||getuid()!=role->pw_uid||geteuid()!=role->pw_uid||getgid()!=role->pw_gid||getegid()!=role->pw_gid||getgroups(0,nullptr)!=0) return false;
    if(prctl(PR_GET_NO_NEW_PRIVS,0,0,0,0)!=1)return false;
    std::ifstream input("/proc/self/status");std::string line;unsigned checked=0;
    while(std::getline(input,line)) {
        if(line.starts_with("CapInh:")||line.starts_with("CapPrm:")||line.starts_with("CapEff:")||line.starts_with("CapBnd:")||line.starts_with("CapAmb:")) {
            const auto colon=line.find(':');
            for(const char c:line.substr(colon+1))if(c!='0'&&c!=' '&&c!='\t'&&c!='\r')return false;
            ++checked;
        }
    }
    return checked==5;
}
bool write_report(int fd,const std::string& data) {
    if(data.size()>16384)return false;
    std::size_t offset=0;
    while(offset<data.size()) {
        const auto n=write(fd,data.data()+offset,data.size()-offset);
        if(n<0&&errno==EINTR)continue;
        if(n<=0)return false;
        offset+=static_cast<std::size_t>(n);
    }
    return fsync(fd)==0;
}
pid_t wait_owned(pid_t child,int* status,int options) {
    pid_t result;
    do {result=waitpid(child,status,options);} while(result<0&&errno==EINTR);
    return result;
}
int live(int fd) {
    // All authorization checks precede constructing/opening the real backend.
    struct stat s{};
    const int flags=fcntl(fd,F_GETFL);
    if(fd<3||fd>1024||flags<0||fstat(fd,&s)!=0||!private_grant(s,flags,lseek(fd,0,SEEK_CUR))||!credentials())return 2;
    if(fcntl(fd,F_SETFD,FD_CLOEXEC)!=0)return 2;
    if(std::signal(SIGINT,cancel)==SIG_ERR||std::signal(SIGTERM,cancel)==SIG_ERR||std::signal(SIGHUP,cancel)==SIG_ERR)return 2;
    LinuxConnectorIo native;TracedIo io(native);Capture sink;Collector collector(io,sink);
    pid_t child=-1;int child_status=-1;bool forced=false;
    if(collector.start()) {
        auto until=std::chrono::steady_clock::now()+std::chrono::seconds(1);
        unsigned polls=0;
        while(!cancelled&&std::chrono::steady_clock::now()<until&&polls++<10000&&collector.status().state!=State::unavailable)collector.poll_once(std::chrono::milliseconds(5));
        if(!cancelled&&collector.status().state!=State::unavailable)child=fork();
        if(child==0) {
            // No controller/report descriptors survive into the owned test child.
            if(syscall(SYS_close_range,3U,std::numeric_limits<unsigned>::max(),0U)!=0)_exit(126);
            execl("/usr/bin/sleep","sleep","0.25",static_cast<char*>(nullptr));_exit(127);
        }
        if(child>0) {
            sink.owned=child;until=std::chrono::steady_clock::now()+std::chrono::seconds(5);polls=0;
            while(!cancelled&&!sink.lifecycle()&&std::chrono::steady_clock::now()<until&&polls++<10000&&collector.status().state!=State::unavailable)collector.poll_once(std::chrono::milliseconds(5));
        }
    }
    const Status before=collector.status();collector.stop(); // One IGNORE attempt; no wait/retry/root fallback.
    if(child>0) {
        auto waited=wait_owned(child,&child_status,WNOHANG);
        const auto natural_until=std::chrono::steady_clock::now()+std::chrono::milliseconds(500);
        while(waited==0&&std::chrono::steady_clock::now()<natural_until) {usleep(10000);waited=wait_owned(child,&child_status,WNOHANG);}
        if(waited==0) {
            forced=true;kill(child,SIGTERM);
            const auto until=std::chrono::steady_clock::now()+std::chrono::seconds(1);
            while(waited==0&&std::chrono::steady_clock::now()<until) {usleep(10000);waited=wait_owned(child,&child_status,WNOHANG);}
            if(waited==0) {kill(child,SIGKILL);waited=wait_owned(child,&child_status,0);}
        }
        if(waited!=child)child_status=-1;
    }
    const bool observed=!cancelled&&!forced&&child>0&&child_status==0&&sink.lifecycle()&&!sink.latest.incomplete_interval&&io.listen_error==0&&io.ignore_error==0&&io.close_error==0&&io.opens==1&&io.sends==2&&io.closes==1;
    return write_report(fd,report(sink,before,io,observed,child_status,forced))?(observed?0:1):3;
}
} // namespace
int main(int argc,char** argv) {
    if(argc==1||(argc==2&&std::string_view(argv[1])=="--self-test"))return self_test();
    if(argc==4&&std::string_view(argv[1])=="--live"&&std::string_view(argv[2])=="--report-fd") {
        int fd=-1;const std::string_view text(argv[3]);const auto result=std::from_chars(text.data(),text.data()+text.size(),fd);
        if(result.ec==std::errc{}&&result.ptr==text.data()+text.size())return live(fd);
    }
    std::fputs("process adapter trial refused\n",stderr);return 2;
}
