#include "hids/process/pipeline.hpp"
#include <cassert>
#include <iostream>
#include <limits>
using namespace hids;
namespace {
processlive::Json source(){return {{"adapter","linux.cn_proc"},{"mode","synthetic"},{"source_id","11000000-0000-4000-8000-000000000001"},{"activation_id","22000000-0000-4000-8000-000000000002"},{"boot_id","33000000-0000-4000-8000-000000000003"},{"profile","linux.cn_proc.lifecycle/1"}};}
int fixed(clockid_t,timespec* out){*out={0,123456789};return 0;}
int failed(clockid_t,timespec*){return -1;}
process::NativeEvent native(process::Lifecycle kind){
 process::NativeEvent n{kind,42,41,{},4294967295U,4294967295U,std::numeric_limits<std::uint64_t>::max(),{}, {}};
 if(kind!=process::Lifecycle::executed)n.parent=process::Parent{0,0};
 if(kind==process::Lifecycle::exited){n.native_exit_status=4294967295U;n.native_exit_signal=0;}
 return n;
}
}
int main(int argc,char** argv){
 if(argc==2&&std::string_view(argv[1])=="--validate"){
  try{
   std::string line;char c;while(std::cin.get(c)&&c!='\n'){if(line.size()==processlive::event_limit)return 1;line+=c;}
   const auto j=pilot::parse(line,processlive::event_limit);processlive::validate(j,source(),"synthetic");return 0;
  }catch(...){return 1;}
 }
 const auto s=source();unsigned index=1;
 for(auto kind:{process::Lifecycle::forked,process::Lifecycle::executed,process::Lifecycle::exited}){
  auto id=std::string("55000000-0000-4000-8000-00000000000")+std::to_string(index++);
  const auto event=processlive::normalize(native(kind),"2026-11-13T00:00:00.000000Z",s,"44000000-0000-4000-8000-000000000004",id);
  assert(event["native"]["timestamp_ns"]=="18446744073709551615");
  assert(event["normalized"]["process"]["pid"]==41);
  assert(!event["normalized"]["process"].contains("parent"));
  if(argc==2&&std::string_view(argv[1])=="--generate")std::cout<<event.dump()<<'\n';
  auto bad=event;bad["normalized"]["process"]["pid"]=41.0;bool rejected=false;
  try{processlive::validate(bad,s,"synthetic");}catch(...){rejected=true;}assert(rejected);
 }
 processlive::Queue q(fixed);const auto n=native(process::Lifecycle::executed);
 for(unsigned i=0;i<256;++i)q.on_event(n);
 assert(q.size()==256&&!q.failed);q.on_event(n);assert(q.failed&&std::string(q.reason)=="queue_full");
 processlive::Slot slot;for(unsigned i=0;i<256;++i){assert(q.pop(slot));assert(slot.observed.tv_nsec==123456789);}assert(!q.pop(slot));
 processlive::Queue broken(failed);broken.on_event(n);assert(broken.failed&&broken.size()==0);
 processlive::Queue filtered(fixed);filtered.owned_fixture=12;filtered.on_event(n);assert(filtered.size()==0);
 q.on_diagnostic({process::Reason::sequence_discontinuity,0,{},{},{}});assert(q.diagnostics[static_cast<std::size_t>(process::Reason::sequence_discontinuity)]==1);
 assert(processlive::observed_time({0,123456789})=="1970-01-01T00:00:00.123456Z");
 if(argc==1)std::cout<<"process pipeline native checks passed\n";
}
