#include "hids/process/runtime.hpp"
#include <fstream>
#include <fcntl.h>
#include <pwd.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>
#include <sys/random.h>
#include <cerrno>
namespace hids::processlive {
namespace {
Json status(const Queue& queue,const Json& source,const std::string& producer,bool stopped,const char* reason,bool failure){
 Json diagnostics=Json::array();for(const auto n:queue.diagnostics)diagnostics.push_back(n);
 return {{"protocol_version",1},{"message_type","status"},{"contract_version",contract},{"source",source},{"producer_instance_id",producer},{"acknowledged",queue.status.subscription_acknowledged},{"delivery",queue.status.delivery_observed},{"incomplete",failure||queue.failed||queue.status.incomplete_interval},{"stopped",stopped},{"reason",reason},{"diagnostic_counts",diagnostics}};
}
void status_ack(const Json& reply,const std::string& producer){
 const Json expected={{"protocol_version",1},{"message_type","status_ack"},{"producer_instance_id",producer}};
 if(reply.dump()!=expected.dump())throw pilot::Invalid("transport_failed");
}
std::string identifier(){return pilot::uuid_v4([](void* p,std::size_t n)->ssize_t{return ::getrandom(p,n,0);});}
}
int run(process::ConnectorIo& io,Stream& stream,Queue& queue,const Json& source,const std::string& producer,
 const std::function<bool()>& cancelled,const std::function<void()>& started,const std::function<bool()>& completed){
 process::Collector collector(io,queue);const char* reason="stopped";bool failure=false;
 try{
  status_ack(stream.exchange(status(queue,source,producer,false,"none",false)),producer);
  if(cancelled())throw pilot::Invalid("cancelled");
  if(!collector.start())throw pilot::Invalid("source_failed");
  if(started)started();
  auto heartbeat=std::chrono::steady_clock::now();
  while(!cancelled()){
   collector.poll_once(std::chrono::milliseconds(10));
   if(queue.failed)throw pilot::Invalid(queue.reason);
   if(queue.status.state==process::State::unavailable)throw pilot::Invalid("source_failed");
   if(queue.status.incomplete_interval)throw pilot::Invalid("native_gap");
   Slot slot;
   while(queue.pop(slot)){
    const auto event=normalize(slot.event,observed_time(slot.observed),source,producer,identifier());
    // Freeze exactly one validated frame until a commit acknowledgement arrives.
    const auto reply=stream.exchange(event);
    if(reply.value("message_type",std::string{})=="error"){
     if(reply.value("code",std::string{})=="capacity_exceeded")throw pilot::Invalid("capacity");
     throw pilot::Invalid("storage_failed");
    }
    const Json stored={{"protocol_version",1},{"message_type","ack"},{"event_id",event["event_id"]},{"result","stored"}};
    auto duplicate=stored;duplicate["result"]="duplicate";
    if(reply.dump()!=stored.dump()&&reply.dump()!=duplicate.dump())throw pilot::Invalid("transport_failed");
   }
   if(completed&&completed())break;
   if(std::chrono::steady_clock::now()-heartbeat>=std::chrono::seconds(1)){
    status_ack(stream.exchange(status(queue,source,producer,false,"none",false)),producer);heartbeat=std::chrono::steady_clock::now();
   }
  }
 }catch(const pilot::Invalid& e){
  const std::string code=e.what();failure=true;
  if(code=="queue_full")reason="queue_full";else if(code=="clock_failed"||code=="observation_clock_failed")reason="clock_failed";
  else if(code=="capacity")reason="capacity";else if(code=="storage_failed")reason="storage_failed";
  else if(code=="source_failed")reason="source_failed";else if(code=="native_gap")reason="native_gap";
  else if(code=="cancelled")reason="cancelled";else reason="transport_failed";
 }catch(...){failure=true;reason="transport_failed";}
 collector.stop();if(queue.status.incomplete_interval)failure=true;
 if(queue.size()!=0){failure=true;if(reason==std::string_view("stopped"))reason="cancelled";}
 stream.finishing();
 try{status_ack(stream.exchange(status(queue,source,producer,true,reason,failure)),producer);}catch(...){failure=true;}
 return failure?1:0;
}
bool role_credentials(){
 const auto* role=getpwnam("hids-process");
 if(!role||role->pw_uid==0||role->pw_gid==0||getuid()!=role->pw_uid||geteuid()!=role->pw_uid||getgid()!=role->pw_gid||getegid()!=role->pw_gid||prctl(PR_GET_NO_NEW_PRIVS,0,0,0,0)!=1)return false;
 gid_t groups[2]{};const int count=getgroups(2,groups);
 // systemd/NSS may repeat the primary GID in its supplementary-group vector.
 // That adds no group access; any other or repeated extra GID is refused.
 if(count<0||count>1||(count==1&&groups[0]!=role->pw_gid))return false;
 std::ifstream input("/proc/self/status");std::string line;unsigned checked=0;
 while(std::getline(input,line))if(line.starts_with("CapInh:")||line.starts_with("CapPrm:")||line.starts_with("CapEff:")||line.starts_with("CapBnd:")||line.starts_with("CapAmb:")){
  for(char c:line.substr(line.find(':')+1))if(c!='0'&&c!=' '&&c!='\t'&&c!='\r')return false;
  ++checked;
 }return checked==5;
}
Json read_config(const std::string& path){
 // Authorizer supplies a fixed absolute path in its root-controlled activation directory.
 if(path.empty()||path.front()!='/')throw pilot::Invalid("configuration_refused");
 const auto parent=path.substr(0,path.find_last_of('/'));struct stat ps{};
 if(lstat(parent.c_str(),&ps)!=0||!S_ISDIR(ps.st_mode)||ps.st_uid!=0||(ps.st_mode&0022))throw pilot::Invalid("configuration_refused");
 const int fd=open(path.c_str(),O_RDONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)throw pilot::Invalid("configuration_refused");
 try{
  struct stat s{};if(fstat(fd,&s)!=0||s.st_uid!=0||!S_ISREG(s.st_mode)||s.st_nlink!=1||(s.st_mode&0022)||s.st_size<=0||s.st_size>16384)throw pilot::Invalid("configuration_refused");
  std::string raw;char bytes[1024];ssize_t n;
  while((n=read(fd,bytes,sizeof(bytes)))>0){raw.append(bytes,static_cast<std::size_t>(n));if(raw.size()>16384)throw pilot::Invalid("configuration_refused");}
  if(n<0)throw pilot::Invalid("configuration_refused");
  auto value=pilot::parse(raw,16384);::close(fd);return value;
 }catch(...){::close(fd);throw;}
}
void verify_grant(int fd,const Json& source){
 ucred peer{};socklen_t size=sizeof(peer);int type=0;socklen_t typesize=sizeof(type);
 if(fd<3||getsockopt(fd,SOL_SOCKET,SO_TYPE,&type,&typesize)!=0||type!=SOCK_STREAM||getsockopt(fd,SOL_SOCKET,SO_PEERCRED,&peer,&size)!=0||peer.uid!=0)throw pilot::Invalid("activation_refused");
 if(fcntl(fd,F_SETFD,FD_CLOEXEC)!=0)throw pilot::Invalid("activation_refused");
 std::string bytes;char byte{};
 const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);
 while(true){
  const auto n=recv(fd,&byte,1,MSG_DONTWAIT);
  if(n<0&&(errno==EAGAIN||errno==EWOULDBLOCK||errno==EINTR)){
   if(std::chrono::steady_clock::now()>=deadline)throw pilot::Invalid("activation_refused");
   usleep(1000);continue;
  }
  if(n!=1)throw pilot::Invalid("activation_refused");
  if(byte=='\n')break;
  if(bytes.size()==1024)throw pilot::Invalid("activation_refused");
  bytes+=byte;
 }
 const auto value=pilot::parse(bytes,1024);
 const Json expected={{"source_id",source.at("source_id")},{"activation_id",source.at("activation_id")}};
 if(value.dump()!=expected.dump())throw pilot::Invalid("activation_refused");
}
bool grant_closed(int fd)noexcept{
 char byte;const auto n=recv(fd,&byte,1,MSG_PEEK|MSG_DONTWAIT);
 return n==0||n>0||(n<0&&errno!=EAGAIN&&errno!=EWOULDBLOCK&&errno!=EINTR);
}
}
