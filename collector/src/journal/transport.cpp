#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE
#endif
#include "hids/journal/transport.hpp"
#include <algorithm>
#include <cerrno>
#include <cstring>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>
namespace hids::journal {
namespace {
void send_line(Channel& io,const std::string& line,Deadline deadline,bool& sent){
    std::size_t offset=0;
    while(offset<line.size()){
        if(io.cancelled()||io.now()>=deadline)throw std::runtime_error("write_deadline");
        auto n=io.write(line.data()+offset,line.size()-offset);
        if(n>0&&static_cast<std::size_t>(n)<=line.size()-offset){offset+=static_cast<std::size_t>(n);sent=true;}
        else if(n<0&&errno==EINTR)continue;
        else if(n<0&&(errno==EAGAIN||errno==EWOULDBLOCK)){if(!io.wait(true,deadline))throw std::runtime_error("write_failed");}
        else throw std::runtime_error("write_failed");
    }
}
Json read_line(Channel& io,Deadline deadline,std::size_t cap){
    std::string raw; raw.reserve(cap);
    std::array<char,2049> chunk{};
    while(!io.cancelled() && io.now()<deadline){
        const auto n=io.read(chunk.data(),std::min(chunk.size(),cap+1));
        if(n>0 && static_cast<std::size_t>(n)<=chunk.size()){
            for(std::size_t i=0;i<static_cast<std::size_t>(n);++i){
                if(chunk[i]=='\n'){
                    if(i+1!=static_cast<std::size_t>(n))throw Invalid("unsolicited_response");
                    return parse(raw,cap);
                }
                if(raw.size()==cap)throw Invalid("frame_too_large");
                raw+=chunk[i];
            }
        }else if(n<0 && errno==EINTR)continue;
        else if(n<0 && (errno==EAGAIN||errno==EWOULDBLOCK)){
            if(!io.wait(false,deadline))break;
        }else break;
    }
    throw std::runtime_error("response_unconfirmed");
}
}
Json exchange_line(Channel& io,const std::string& line,Deadline deadline){
    if(line.empty()||line.back()!='\n'||line.size()>event_limit+1)throw Invalid();
    bool sent=false;send_line(io,line,deadline,sent);return read_line(io,deadline,response_limit);
}
Json request(Channel& io,const Json& obj,Deadline deadline,std::size_t cap){
    const auto line=obj.dump(-1,' ',true)+"\n";
    if(line.size()>event_limit+1||cap>response_limit)throw Invalid();
    bool sent=false;send_line(io,line,deadline,sent);return read_line(io,deadline,cap);
}
Delivery transmit(Channel& io,const std::string& frozen,bool prior){
    Delivery out{prior?"unconfirmed":"local_failure","not_submitted",0,false};Json event;
    try{if(frozen.empty()||frozen.back()!='\n')throw Invalid();event=parse(std::string_view(frozen).substr(0,frozen.size()-1));validate(event);}catch(...){return out;}
    bool unresolved=prior;
    const auto id=event["event_id"].get<std::string>();const auto end=io.now()+std::chrono::seconds(30);
    for(unsigned i=0;i<3&&!io.cancelled()&&io.now()<end;++i){
        if(i){auto delay=std::chrono::milliseconds(i==1?100:500);if(io.now()+delay>=end)break;io.sleep(delay);}
        if(io.now()>=end||io.cancelled())break;
        ++out.attempts;
        auto stage=[&]{return std::min(end,io.now()+std::chrono::seconds(5));};
        const int rc=io.connect(stage());
        if(rc){io.close();if(rc==EPERM||rc==EACCES||rc==EINVAL||rc==ENOTSUP)break;continue;}
        try{
            send_line(io,frozen,stage(),out.any_sent);
            auto response=read_line(io,stage(),response_limit);validate_response(response,id);io.close();
            if(response["message_type"]=="ack")return {"acknowledged",response["result"].get<std::string>(),out.attempts,out.any_sent};
            if(response["message_type"]=="reject")return {unresolved?"unconfirmed":"rejected",response["code"].get<std::string>(),out.attempts,out.any_sent};
            return {"unconfirmed","storage_error",out.attempts,out.any_sent};
        }catch(const Invalid&){io.close();return {"unconfirmed","protocol_error",out.attempts,out.any_sent};}
        catch(...){unresolved=unresolved||out.any_sent;io.close();}
    }
    out.outcome=prior||out.any_sent?"unconfirmed":"local_failure";out.code=out.outcome=="unconfirmed"?"delivery_unconfirmed":"not_submitted";return out;
}
int UnixChannel::connect(Deadline deadline){
    close();
#ifdef __linux__
    if(getuid()!=997||geteuid()!=997||getgid()!=getegid()||peer_.uid==0||peer_.uid==997)return EPERM;
    auto slash=path_.find_last_of('/');if(path_.empty()||path_[0]!='/'||slash==path_.npos||path_.size()>=sizeof(sockaddr_un::sun_path))return EINVAL;
    std::string parent=path_.substr(0,slash);char resolved[4096]{};struct stat d{},s{};
    if(!realpath(parent.c_str(),resolved)||parent!=resolved)return EACCES;
    if(lstat(parent.c_str(),&d)||!S_ISDIR(d.st_mode)||d.st_uid!=peer_.uid||d.st_gid!=peer_.ipc_gid||(d.st_mode&0777)!=0750)return EACCES;
    if(lstat(path_.c_str(),&s)||!S_ISSOCK(s.st_mode)||s.st_uid!=peer_.uid||s.st_gid!=peer_.ipc_gid||(s.st_mode&0777)!=0660)return EACCES;
    fd_=socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC|SOCK_NONBLOCK,0);if(fd_<0)return errno;
    sockaddr_un a{};a.sun_family=AF_UNIX;std::memcpy(a.sun_path,path_.c_str(),path_.size()+1);
    if(::connect(fd_,reinterpret_cast<sockaddr*>(&a),sizeof(a))){
        if(errno!=EINPROGRESS&&errno!=EAGAIN)return errno;
        if(!wait(true,deadline))return ETIMEDOUT;
        int rc=0;socklen_t size=sizeof(rc);if(getsockopt(fd_,SOL_SOCKET,SO_ERROR,&rc,&size))return errno;if(rc)return rc;
    }
    ucred peer{};socklen_t size=sizeof(peer);if(getsockopt(fd_,SOL_SOCKET,SO_PEERCRED,&peer,&size))return errno;
    if(size!=sizeof(peer)||peer.pid<=0||peer.uid!=peer_.uid||peer.gid!=peer_.gid)return EPERM;
    return 0;
#else
    (void)deadline;(void)peer_;return ENOTSUP;
#endif
}
ssize_t UnixChannel::write(const void* p,std::size_t n){
#ifdef __linux__
    return ::send(fd_,p,n,MSG_NOSIGNAL);
#else
    (void)p;(void)n;errno=ENOTSUP;return -1;
#endif
}
ssize_t UnixChannel::read(void* p,std::size_t n){return ::recv(fd_,p,n,0);}
bool UnixChannel::wait(bool writing,Deadline end){
    while(!cancelled()&&now()<end){
        auto remaining=std::chrono::duration_cast<std::chrono::milliseconds>(end-now()).count();
        pollfd p{fd_,static_cast<short>(writing?POLLOUT:POLLIN),0};auto rc=::poll(&p,1,static_cast<int>(std::min<std::int64_t>(100,remaining)));
        if(rc>0)return (p.revents&(POLLIN|POLLOUT|POLLHUP|POLLERR))!=0;
        if(rc<0&&errno!=EINTR)return false;
    }return false;
}
void UnixChannel::close() noexcept{if(fd_>=0)::close(fd_);fd_=-1;}
}
