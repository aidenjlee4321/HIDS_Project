#include "hids/process/stream.hpp"
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
namespace hids::processlive {
void Stream::ready(bool writing,const std::chrono::steady_clock::time_point& deadline){
 while(!stopped_()&&std::chrono::steady_clock::now()<deadline){
  pollfd p{fd_,static_cast<short>(writing?POLLOUT:POLLIN),0};const auto n=::poll(&p,1,20);
  if(n<0&&errno==EINTR)continue;
  if(n<0)throw pilot::Invalid("transport_failed");
  if(p.revents&(writing?POLLOUT:POLLIN))return;
  if(p.revents&(POLLERR|POLLHUP|POLLNVAL))throw pilot::Invalid("transport_failed");
 }throw pilot::Invalid("transport_failed");
}
Stream::Stream(std::string path,unsigned peer_uid,const std::function<bool()>& stop):stopped_(stop){
 if(path.empty()||path.size()>=sizeof(sockaddr_un{}.sun_path))throw pilot::Invalid("transport_failed");
 fd_=::socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC|SOCK_NONBLOCK,0);
 try{
  if(fd_<0)throw pilot::Invalid("transport_failed");
  sockaddr_un address{};address.sun_family=AF_UNIX;std::memcpy(address.sun_path,path.c_str(),path.size()+1);
  const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);
  if(::connect(fd_,reinterpret_cast<sockaddr*>(&address),sizeof(address))!=0){
   // AF_UNIX backlog EAGAIN does not initiate a connection. Fail, never retry.
   if(errno!=EINPROGRESS)throw pilot::Invalid("transport_failed");
   ready(true,deadline);int error=0;socklen_t size=sizeof(error);
   if(getsockopt(fd_,SOL_SOCKET,SO_ERROR,&error,&size)!=0||error)throw pilot::Invalid("transport_failed");
  }
  ucred peer{};socklen_t size=sizeof(peer);
  if(getsockopt(fd_,SOL_SOCKET,SO_PEERCRED,&peer,&size)!=0||size!=sizeof(peer)||peer.uid!=peer_uid)throw pilot::Invalid("peer_denied");
 }catch(...){close();throw;}
}
Stream::~Stream(){close();}
void Stream::close()noexcept{if(fd_>=0){::close(fd_);fd_=-1;}}
Json Stream::exchange(const Json& value){
 const auto raw=value.dump()+"\n";if(raw.size()>event_limit+1)throw pilot::Invalid("frame_too_large");
 const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);std::size_t offset=0;
 while(offset<raw.size()){
  ready(true,deadline);const auto n=::send(fd_,raw.data()+offset,raw.size()-offset,MSG_NOSIGNAL);
  if(n<0&&(errno==EINTR||errno==EAGAIN||errno==EWOULDBLOCK))continue;
  if(n<=0)throw pilot::Invalid("transport_failed");
  offset+=static_cast<std::size_t>(n);
 }
 std::string response;response.reserve(response_limit);
 while(true){
  ready(false,deadline);char byte{};const auto n=::recv(fd_,&byte,1,0);
  if(n<0&&(errno==EINTR||errno==EAGAIN||errno==EWOULDBLOCK))continue;
  if(n<=0)throw pilot::Invalid("transport_failed");
  if(byte=='\n')return pilot::parse(response,response_limit);
  if(response.size()==response_limit)throw pilot::Invalid("frame_too_large");
  response+=byte;
 }
}
}
