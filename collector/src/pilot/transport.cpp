#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE
#endif
#include "hids/pilot/transport.hpp"
#include <algorithm>
#include <cerrno>
#include <cstring>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>
#include <thread>

namespace hids::pilot {
void Channel::sleep(std::chrono::milliseconds ms) { std::this_thread::sleep_for(ms); }
Delivery transmit(Channel& io, const std::string& line, bool prior_uncertain) {
    Delivery out{prior_uncertain ? "unconfirmed" : "local_failure", "not_submitted",0,false};
    if (line.empty() || line.back() != '\n' || line.size() > event_limit+1) return out;
    Json event;
    try {event = parse(std::string_view(line).substr(0,line.size()-1)); validate_event(event);}
    catch (const std::exception&) {return out;}
    const std::string id = event["event_id"].get<std::string>();
    const auto total = io.now()+std::chrono::seconds(30);
    bool unresolved = prior_uncertain;
    for (unsigned attempt=0;attempt<3 && io.now()<total && !io.cancelled();++attempt) {
        if (attempt) {
            const auto delay=std::chrono::milliseconds(attempt==1?100:500);
            if (io.now()+delay>=total) break;
            io.sleep(delay);
        }
        if (io.now() >= total || io.cancelled()) break;
        ++out.attempts;
        const auto stage = [&] {return std::min(total,io.now()+std::chrono::seconds(5));};
        const int connected = io.connect(stage());
        if (connected != 0) {
            io.close();
            if (connected == EPERM || connected == EACCES || connected == EINVAL || connected == ENOTSUP) {
                out.outcome=unresolved || out.any_sent ? "unconfirmed" : "local_failure";
                out.code = out.outcome=="local_failure" ? "not_submitted" : "delivery_unconfirmed"; return out;
            }
            continue;
        }
        auto deadline = stage();
        std::size_t offset=0;
        bool failed=false;
        while (offset<line.size() && !io.cancelled()) {
            if (io.now()>=deadline) {failed=true; break;}
            const auto n = io.write(line.data()+offset,line.size()-offset);
            if (n > 0 && static_cast<std::size_t>(n) <= line.size()-offset) {
                offset+=static_cast<std::size_t>(n); out.any_sent=true;
            } else if (n<0 && errno==EINTR) continue;
            else if (n<0 && (errno==EAGAIN || errno==EWOULDBLOCK)) {
                if (!io.wait(true,deadline)) {failed=true;break;}
            } else {failed=true;break;}
        }
        if (io.cancelled()) failed=true;
        if (failed || offset!=line.size()) {
            unresolved = unresolved || out.any_sent;
            io.close(); continue;
        }
        deadline=stage(); std::string payload; payload.reserve(response_limit);
        bool complete=false, malformed=false;
        while (!io.cancelled() && io.now()<deadline) {
            char c{}; const auto n=io.read(&c,1);
            if (n==1) {
                if (c=='\n') {complete=true;break;}
                if (payload.size()==response_limit) {malformed=true;break;}
                payload+=c;
            } else if (n<0 && errno==EINTR) continue;
            else if (n<0 && (errno==EAGAIN || errno==EWOULDBLOCK)) {
                if (!io.wait(false,deadline)) break;
            } else break;
        }
        io.close();
        if (complete || malformed) {
            try {
                if (malformed) throw Invalid();
                const auto response=validate_response(parse(payload,response_limit),id);
                out.outcome=response.outcome;out.code=response.code;
                if (unresolved && out.outcome=="rejected") out.outcome="unconfirmed";
                return out;
            } catch (const std::exception&) {
                out.outcome="unconfirmed";out.code="response_protocol_error";return out;
            }
        }
        unresolved=true;
    }
    io.close();out.outcome=unresolved || out.any_sent ? "unconfirmed" : "local_failure";
    out.code=out.outcome=="local_failure" ? "not_submitted" : "delivery_unconfirmed";
    return out;
}
UnixChannel::UnixChannel(std::string path,int pid,const std::function<bool()>& stopped)
    : path_(std::move(path)),peer_pid_(pid),stopped_(stopped) {}
UnixChannel::~UnixChannel() {close();}
bool UnixChannel::cancelled() const {return stopped_();}
void UnixChannel::close() noexcept {if (fd_>=0) {::close(fd_);fd_=-1;}}
int UnixChannel::connect(Deadline deadline) {
    close();
#ifdef __linux__
    if (getuid()==0 || getuid()!=geteuid() || getgid()!=getegid() || peer_pid_<=0) return EPERM;
    const auto slash=path_.find_last_of('/');
    if (path_.empty() || path_[0]!='/' || slash==path_.npos || path_.size()>=sizeof(sockaddr_un::sun_path)) return EINVAL;
    const std::string parent=path_.substr(0,slash);
    char resolved[4096]{};
    if (!realpath(parent.c_str(),resolved) || parent!=resolved) return EACCES;
    struct stat directory{},endpoint{};
    if (lstat(parent.c_str(),&directory)!=0 || !S_ISDIR(directory.st_mode) || directory.st_uid!=getuid() || (directory.st_mode&0777)!=0700) return EACCES;
    if (lstat(path_.c_str(),&endpoint)!=0) return errno;
    if (!S_ISSOCK(endpoint.st_mode) || endpoint.st_uid!=getuid() || (endpoint.st_mode&0777)!=0600) return EACCES;
    fd_=socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC|SOCK_NONBLOCK,0);
    if (fd_<0) return errno;
    sockaddr_un address{};address.sun_family=AF_UNIX;
    std::memcpy(address.sun_path,path_.c_str(),path_.size()+1);
    if (::connect(fd_,reinterpret_cast<const sockaddr*>(&address),sizeof(address))!=0) {
        if (errno!=EINPROGRESS && errno!=EAGAIN) return errno;
        if (!wait(true,deadline)) return ETIMEDOUT;
        int error=0;socklen_t size=sizeof(error);
        if (getsockopt(fd_,SOL_SOCKET,SO_ERROR,&error,&size)!=0) return errno;
        if (error!=0) return error;
    }
    ucred peer{};socklen_t size=sizeof(peer);
    if (getsockopt(fd_,SOL_SOCKET,SO_PEERCRED,&peer,&size)!=0) return errno;
    if (size!=sizeof(peer) || peer.pid!=peer_pid_ || peer.uid!=getuid() || peer.gid!=getgid()) return EPERM;
    return 0;
#else
    (void)deadline;(void)peer_pid_;return ENOTSUP;
#endif
}
ssize_t UnixChannel::write(const void* p,std::size_t n) {
#ifdef __linux__
    return ::send(fd_,p,n,MSG_NOSIGNAL);
#else
    (void)p;(void)n;errno=ENOTSUP;return -1;
#endif
}
ssize_t UnixChannel::read(void* p,std::size_t n) {return ::recv(fd_,p,n,0);}
bool UnixChannel::wait(bool writing,Deadline deadline) {
    while (!cancelled()) {
        const auto remaining=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-now()).count();
        if (remaining<=0) return false;
        pollfd p{fd_,static_cast<short>(writing?POLLOUT:POLLIN),0};
        const auto result=::poll(&p,1,static_cast<int>(std::min<std::int64_t>(remaining,100)));
        if (result<0 && errno!=EINTR) return false;
        if (result>0) return (p.revents&(POLLIN|POLLOUT|POLLHUP|POLLERR))!=0;
    }
    return false;
}
} // namespace hids::pilot
