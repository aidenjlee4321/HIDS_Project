#include "hids/process/runtime.hpp"
#include "hids/linux_process_connector.hpp"
#include <charconv>
#include <csignal>
#include <sys/random.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>
#include <limits>
#include <sys/socket.h>
#include <sys/un.h>
#include <cstring>
#include <poll.h>
namespace {volatile std::sig_atomic_t cancelled=0;void stop(int){cancelled=1;}}
int main(int argc,char** argv){
 using namespace hids;int result=2;pid_t child=-1;
 try{
  if((argc!=2&&argc!=3)||!processlive::role_credentials())return 2;
  int grant=-1;
  const auto config=processlive::read_config(argv[1]);
  if(!config.is_object()||config.size()!=4||!config.contains("source")||!config.contains("socket")||!config.contains("peer_uid")||!config.contains("lease_socket"))return 2;
  if(argc==3){
   const std::string_view arg=argv[2];const auto parsed=std::from_chars(arg.data(),arg.data()+arg.size(),grant);
   if(parsed.ec!=std::errc{}||parsed.ptr!=arg.data()+arg.size())return 2;
  }else{
   const auto path=config.at("lease_socket").get<std::string>();if(path.empty()||path.size()>=sizeof(sockaddr_un{}.sun_path))return 2;
   grant=::socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC|SOCK_NONBLOCK,0);if(grant<0)return 2;
   sockaddr_un address{};address.sun_family=AF_UNIX;std::memcpy(address.sun_path,path.c_str(),path.size()+1);
   if(::connect(grant,reinterpret_cast<sockaddr*>(&address),sizeof(address))!=0){
    if(errno!=EINPROGRESS)return 2;
    pollfd ready{grant,POLLOUT,0};if(::poll(&ready,1,2000)<=0)return 2;
    int error=0;socklen_t size=sizeof(error);if(getsockopt(grant,SOL_SOCKET,SO_ERROR,&error,&size)!=0||error)return 2;
   }
  }
  const auto source=config.at("source");processlive::validate_source(source,"live");
  if(config.at("peer_uid")!=0)return 2;
  processlive::verify_grant(grant,source);
  if(std::signal(SIGTERM,stop)==SIG_ERR||std::signal(SIGINT,stop)==SIG_ERR||std::signal(SIGHUP,stop)==SIG_ERR)return 2;
  auto stopped=[&](){return cancelled||processlive::grant_closed(grant);};
  const auto producer=pilot::uuid_v4([](void* p,std::size_t n)->ssize_t{return ::getrandom(p,n,0);});
  processlive::Stream stream(config.at("socket").get<std::string>(),0,stopped);
  process::LinuxConnectorIo io;processlive::Queue queue;
#ifdef HIDS_PROCESS_ACCEPTANCE
  const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(8);
  auto started=[&](){
   child=fork();if(child<0)throw pilot::Invalid("source_failed");
   if(child==0){if(syscall(SYS_close_range,3U,std::numeric_limits<unsigned>::max(),0U)!=0)_exit(126);execl("/usr/bin/sleep","sleep","0.25",static_cast<char*>(nullptr));_exit(127);}
   queue.owned_fixture=child;
  };
  auto completed=[&](){if(std::chrono::steady_clock::now()>deadline)throw pilot::Invalid("source_failed");return queue.fixture_bits==7&&queue.size()==0;};
  result=processlive::run(io,stream,queue,source,producer,stopped,started,completed);
#else
  result=processlive::run(io,stream,queue,source,producer,stopped);
#endif
 }catch(...){result=2;}
 if(child>0){
  int status=-1;pid_t waited=0;const auto end=std::chrono::steady_clock::now()+std::chrono::milliseconds(500);
  do{waited=waitpid(child,&status,WNOHANG);if(waited==0)usleep(10000);}while((waited==0|| (waited<0&&errno==EINTR))&&std::chrono::steady_clock::now()<end);
  if(waited==0){
   kill(child,SIGTERM);result=1;const auto grace=std::chrono::steady_clock::now()+std::chrono::seconds(1);
   do{waited=waitpid(child,&status,WNOHANG);if(waited==0)usleep(10000);}while((waited==0||(waited<0&&errno==EINTR))&&std::chrono::steady_clock::now()<grace);
   if(waited==0){kill(child,SIGKILL);do{waited=waitpid(child,&status,0);}while(waited<0&&errno==EINTR);}
  }
  if(waited!=child||status!=0)result=1;
 }
 return result; // No raw events or arbitrary diagnostics on stdout/stderr.
}
