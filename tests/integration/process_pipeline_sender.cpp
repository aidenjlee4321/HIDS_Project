// Synthetic native packets -> actual parser/normalizer/runtime/Unix stream.
#include "hids/process/runtime.hpp"
#include <linux/cn_proc.h>
#include <linux/connector.h>
#include <linux/netlink.h>
#include <cstring>
#include <charconv>
#include <unistd.h>
using namespace hids;
struct Io final:process::ConnectorIo{
 unsigned count=0,opens=0,sends=0,closes=0;
 process::OpenResult open()noexcept override{++opens;return {0,123};}
 int send(std::span<const std::byte>)noexcept override{++sends;return 0;}
 int close()noexcept override{++closes;return 0;}
 process::ReadResult receive(std::span<std::byte> bytes,std::chrono::milliseconds)noexcept override{
  if(count==3)return {process::ReadKind::timeout};
  proc_event e{};e.cpu=1;e.timestamp_ns=18446744073709551615ULL;
  if(count==0){e.what=PROC_EVENT_FORK;e.event_data.fork={30,29,42,41};}
  else if(count==1){e.what=PROC_EVENT_EXEC;e.event_data.exec={42,41};}
  else{e.what=PROC_EVENT_EXIT;e.event_data.exit.process_pid=42;e.event_data.exit.process_tgid=41;e.event_data.exit.parent_pid=30;e.event_data.exit.parent_tgid=29;e.event_data.exit.exit_code=7U<<8;e.event_data.exit.exit_signal=17;}
  nlmsghdr n{};n.nlmsg_type=NLMSG_DONE;n.nlmsg_len=sizeof(n)+sizeof(cn_msg)+sizeof(e);
  cn_msg c{};c.id.idx=CN_IDX_PROC;c.id.val=CN_VAL_PROC;c.len=sizeof(e);c.seq=++count;
  std::memcpy(bytes.data(),&n,sizeof(n));std::memcpy(bytes.data()+sizeof(n),&c,sizeof(c));std::memcpy(bytes.data()+sizeof(n)+sizeof(c),&e,sizeof(e));
  return {process::ReadKind::data,n.nlmsg_len};
 }
};
int main(int argc,char** argv){
 if(argc!=3)return 2;
 try{
  unsigned peer=0;const std::string_view arg=argv[2];const auto p=std::from_chars(arg.data(),arg.data()+arg.size(),peer);if(p.ec!=std::errc{}||p.ptr!=arg.data()+arg.size())return 2;
  const processlive::Json source={{"adapter","linux.cn_proc"},{"mode","synthetic"},{"source_id","11000000-0000-4000-8000-000000000001"},{"activation_id","22000000-0000-4000-8000-000000000002"},{"boot_id","33000000-0000-4000-8000-000000000003"},{"profile","linux.cn_proc.lifecycle/1"}};
  processlive::Stream stream(argv[1],peer,[](){return false;});Io io;processlive::Queue queue;
  const int result=processlive::run(io,stream,queue,source,"44000000-0000-4000-8000-000000000004",[](){return false;},{},[&](){return io.count==3&&queue.size()==0;});
  if(io.opens!=1||io.sends!=2||io.closes!=1)return 3;
  return result;
 }catch(...){return 2;}
}
