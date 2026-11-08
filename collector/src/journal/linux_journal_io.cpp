#include "hids/journal_collector.hpp"
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <system_error>
#include <set>
#include <algorithm>
#ifdef __linux__
#include <systemd/sd-journal.h>
#include <systemd/sd-id128.h>
#include <unistd.h>
#include <grp.h>
#include <pwd.h>
#endif
namespace hids::journal {
namespace {
#ifndef __linux__
[[noreturn]] void unsupported(){throw std::system_error(ENOTSUP,std::generic_category(),"libsystemd_requires_linux");}
#endif
#ifdef __linux__
void check(int rc){if(rc<0)throw std::system_error(-rc,std::generic_category(),"journal_api");}
sd_journal* handle(void* p){if(!p)throw std::logic_error("journal_closed");return static_cast<sd_journal*>(p);}
std::string cursor(sd_journal* j){char* raw=nullptr;check(sd_journal_get_cursor(j,&raw));std::string result;
    const auto length=strnlen(raw,513);
    if(length==0||length>512){free(raw);throw std::runtime_error("unusable_cursor");}
    try{result.assign(raw,length);}catch(...){free(raw);throw;}free(raw);
    if(result.empty()||result.size()>512) {
        throw std::runtime_error("unusable_cursor");
    }
    return result;
}
#endif
}
void LinuxJournalIo::open(){
#ifdef __linux__
    if(journal_||getuid()!=997||getuid()!=geteuid()||getgid()!=getegid())throw std::runtime_error("reader_identity");
    const auto* account=getpwnam("hids-journal");
    if(!account||account->pw_uid!=997||account->pw_gid==0||account->pw_gid!=getgid())throw std::runtime_error("reader_identity");
    const auto* journal_group=getgrnam("systemd-journal");
    if(!journal_group)throw std::runtime_error("journal_group_missing");
    const auto journal_gid=journal_group->gr_gid;
    const auto* ipc_group=getgrnam("hids-ipc");
    if(!ipc_group)throw std::runtime_error("ipc_group_missing");
    const auto ipc_gid=ipc_group->gr_gid;
    const int count=getgroups(0,nullptr);
    if(count<0||count>256)throw std::runtime_error("group_policy");
    std::vector<gid_t> raw(static_cast<std::size_t>(count));
    if(getgroups(count,raw.data())!=count)throw std::runtime_error("group_policy");
    std::set<gid_t> actual(raw.begin(),raw.end());actual.insert(getgid());
    if(actual!=std::set<gid_t>{getgid(),journal_gid,ipc_gid})throw std::runtime_error("group_policy");
    sd_journal* j=nullptr;check(sd_journal_open(&j,SD_JOURNAL_LOCAL_ONLY|SD_JOURNAL_SYSTEM));journal_=j;
    try{check(sd_journal_set_data_threshold(j,8192));}catch(...){close();throw;}
#else
    unsupported();
#endif
}
void LinuxJournalIo::match(std::string_view s){
#ifdef __linux__
    check(sd_journal_add_match(handle(journal_),s.data(),s.size()));
#else
    (void)s;unsupported();
#endif
}
void LinuxJournalIo::disjunction(){
#ifdef __linux__
    check(sd_journal_add_disjunction(handle(journal_)));
#else
    unsupported();
#endif
}
void LinuxJournalIo::filter(){ssh_filter(*this);}
std::optional<std::string> LinuxJournalIo::tail(){
#ifdef __linux__
    auto* j=handle(journal_);check(sd_journal_seek_tail(j));const int rc=sd_journal_previous(j);check(rc);
    if(!rc) {
        return std::nullopt;
    }
    return cursor(j);
#else
    unsupported();
#endif
}
bool LinuxJournalIo::seek_exact(const std::string& saved){
#ifdef __linux__
    auto* j=handle(journal_);check(sd_journal_seek_cursor(j,saved.c_str()));const int rc=sd_journal_next(j);check(rc);
    if(!rc) {
        return false;
    }
    const int same=sd_journal_test_cursor(j,saved.c_str());
    check(same);
    return same>0;
#else
    (void)saved;unsupported();
#endif
}
std::optional<Entry> LinuxJournalIo::next(){
#ifdef __linux__
    auto* j=handle(journal_);int rc=sd_journal_next(j);check(rc);if(!rc)return std::nullopt;
    Entry e;e.cursor=cursor(j);std::uint64_t realtime=0,monotonic=0;sd_id128_t boot{};
    if(sd_journal_get_realtime_usec(j,&realtime)<0||sd_journal_get_monotonic_usec(j,&monotonic,&boot)<0)e.rejection="missing_required";
    else{char b[SD_ID128_STRING_MAX];sd_id128_to_string(boot,b);e.boot=b;e.realtime_us=std::to_string(realtime);e.monotonic_us=std::to_string(monotonic);}
    const std::set<std::string,std::less<>> allowed={"_COMM","_EXE","MESSAGE","_PID","_UID","_GID","_SYSTEMD_UNIT","PRIORITY","_TRANSPORT","MESSAGE_ID"};
    sd_journal_restart_data(j);const void* data=nullptr;std::size_t size=0;unsigned count=0;
    while((rc=sd_journal_enumerate_data(j,&data,&size))>0){
        if(++count>256){e.rejection="too_many_fields";break;}
        const auto bytes=std::string_view(static_cast<const char*>(data),size);auto split=bytes.substr(0,std::min<std::size_t>(65,size)).find('=');
        if(split==bytes.npos)throw std::runtime_error("journal_field_encoding");
        const auto key=bytes.substr(0,split);if(!allowed.contains(key))continue;
        if(size>=8192){e.rejection="field_too_large";break;}
        e.fields.emplace_back(key,bytes.substr(split+1));
    }
    check(rc);return e;
#else
    unsupported();
#endif
}
int LinuxJournalIo::wait(unsigned ms){
#ifdef __linux__
    int rc=sd_journal_wait(handle(journal_),static_cast<std::uint64_t>(ms>100?100:ms)*1000);check(rc);
    return rc==SD_JOURNAL_INVALIDATE?2:(rc==SD_JOURNAL_APPEND?1:0);
#else
    (void)ms;unsupported();
#endif
}
void LinuxJournalIo::close() noexcept{
#ifdef __linux__
    if(journal_)sd_journal_close(static_cast<sd_journal*>(journal_));
#endif
    journal_=nullptr;
}
}
