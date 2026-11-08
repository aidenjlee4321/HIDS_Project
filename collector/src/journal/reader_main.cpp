#include "hids/journal/runtime.hpp"
#include <cerrno>
#include <algorithm>
#include <csignal>
#include <fcntl.h>
#include <grp.h>
#include <iostream>
#include <pwd.h>
#include <sys/stat.h>
#include <unistd.h>
#ifdef __linux__
#include <sys/random.h>
#endif
namespace {
volatile std::sig_atomic_t stopping=0;
void stop(int){stopping=1;}
#ifdef __linux__
hids::journal::Json config(const std::string& path){
    char resolved[4096]{};
    if(!realpath(path.c_str(),resolved)||path!=resolved)throw std::runtime_error("config_path");
    std::string parent=path.substr(0,path.find_last_of('/'));
    while(!parent.empty()){
        struct stat st{};
        if(lstat(parent.c_str(),&st)||!S_ISDIR(st.st_mode)||st.st_uid!=0||(st.st_mode&0022))throw std::runtime_error("config_parent");
        if(parent=="/")break;
        auto slash=parent.find_last_of('/');parent=slash==0?"/":parent.substr(0,slash);
    }
    const int fd=open(path.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if(fd<0)throw std::runtime_error("config_open");
    std::string raw;struct stat st{};
    try{
        if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_uid!=0||st.st_nlink!=1||(st.st_mode&0022)||st.st_size<0||st.st_size>4096)throw std::runtime_error("config_policy");
        char block[4097];
        for(;;){auto n=read(fd,block,sizeof(block));if(n<0&&errno==EINTR)continue;if(n<0)throw std::runtime_error("config_read");if(!n)break;raw.append(block,static_cast<std::size_t>(n));if(raw.size()>4096)throw std::runtime_error("config_size");}
        close(fd);
    }catch(...){close(fd);throw;}
    // Pretty-printed root-owned config is not an event frame. Preserve strict
    // duplicate/depth validation by removing whitespace only outside strings.
    std::string compact;bool quote=false,escaped=false;
    for(char c:raw){if(quote){compact+=c;if(escaped)escaped=false;else if(c=='\\')escaped=true;else if(c=='"')quote=false;}else if(c=='"'){quote=true;compact+=c;}else if(c!=' '&&c!='\t'&&c!='\r'&&c!='\n')compact+=c;}
    auto j=hids::journal::parse(compact,4096);
    if(j.size()!=3||!j.contains("source_id")||!j.contains("max_records")||!j.contains("max_pages")||!hids::pilot::uuid_valid(j["source_id"]))throw std::runtime_error("config_shape");
    for(auto name:{"max_records","max_pages"}){
        if(!j[name].is_number_integer()||(!j[name].is_number_unsigned()&&j[name].get<std::int64_t>()<1)||j[name].get<std::uint64_t>()==0||j[name].get<std::uint64_t>()>9223372036854775807ULL)throw std::runtime_error("config_budget");
    }
    if(j["max_pages"].get<std::uint64_t>()<16||j["max_pages"].get<std::uint64_t>()>2147483646ULL)throw std::runtime_error("config_budget");
    return j;
}
hids::journal::Peer policy(){
    auto* me=getpwnam("hids-journal");
    if(!me||me->pw_uid!=997||me->pw_gid==0||getuid()!=997||geteuid()!=997||getgid()!=me->pw_gid||getegid()!=me->pw_gid)throw std::runtime_error("reader_identity");
    auto primary=getgid();auto* ingest=getpwnam("hids-ingest");
    if(!ingest||ingest->pw_uid==0||ingest->pw_uid==997||ingest->pw_gid==0)throw std::runtime_error("ingest_identity");
    const auto uid=ingest->pw_uid,gid=ingest->pw_gid;
    auto* ipc=getgrnam("hids-ipc");if(!ipc)throw std::runtime_error("ipc_group");const auto ipc_gid=ipc->gr_gid;
    auto* journal=getgrnam("systemd-journal");if(!journal)throw std::runtime_error("journal_group");const auto journal_gid=journal->gr_gid;
    int count=getgroups(0,nullptr);if(count<0||count>256)throw std::runtime_error("group_policy");
    std::vector<gid_t> groups(static_cast<std::size_t>(count));if(getgroups(count,groups.data())!=count)throw std::runtime_error("group_policy");
    for(auto g:groups)if(g!=primary&&g!=ipc_gid&&g!=journal_gid)throw std::runtime_error("group_policy");
    if(std::find(groups.begin(),groups.end(),ipc_gid)==groups.end()||std::find(groups.begin(),groups.end(),journal_gid)==groups.end())throw std::runtime_error("group_policy");
    for(auto path:{"/usr/lib/openssh/sshd-session","/usr/sbin/sshd"}){
        char resolved[4096]{};struct stat st{};
        if(!realpath(path,resolved)||std::string(path)!=resolved||stat(path,&st)||!S_ISREG(st.st_mode)||st.st_uid!=0||(st.st_mode&0022)||!(st.st_mode&0111))throw std::runtime_error("ssh_executable_identity");
    }
    return {uid,gid,ipc_gid};
}
#endif
}
int main(int argc,char** argv){
    if(argc==2&&std::string_view(argv[1])=="--help"){
        std::cout<<"m2-reader [--config /etc/hids/m2.json]; requires service identity and explicit backend activation\n";return 0;
    }
    if(argc!=1&&(argc!=3||std::string_view(argv[1])!="--config"))return 64;
#ifdef __linux__
    try{
        auto peer=policy();auto settings=config(argc==3?argv[2]:"/etc/hids/m2.json");
        std::signal(SIGINT,stop);std::signal(SIGTERM,stop);
        auto producer=hids::pilot::uuid_v4([](void* p,std::size_t n){return getrandom(p,n,GRND_NONBLOCK);});
        hids::journal::LinuxJournalIo journal;
        hids::journal::UnixChannel channel("/run/hids/ingest/journal.sock",peer,[]{return stopping!=0;});
        hids::journal::ReaderRuntime runtime(journal,channel,settings["source_id"].get<std::string>(),producer);
        if(!runtime.start())return 0;
        while(!stopping&&runtime.step()){}
        runtime.stop();return 0;
    }catch(const std::exception&){if(stopping)return 0;std::cerr<<"m2_reader_startup_or_runtime_failure\n";return 1;}
#else
    (void)argv;(void)stop;std::cerr<<"m2_reader_requires_linux\n";return 77;
#endif
}
