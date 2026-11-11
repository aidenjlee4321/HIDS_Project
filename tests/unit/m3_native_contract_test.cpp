#include "hids/audit/execution.hpp"
#ifdef HIDS_M3_AUPARSE
#include "hids/audit/auparse_execution.hpp"
#endif

#include <cassert>
#include <fstream>
#include <functional>
#include <iostream>
#include <string>
#include <vector>
#include <utility>

#if defined(__linux__) && defined(__aarch64__)
#include <linux/audit.h>
#include <asm/unistd.h>
static_assert(AUDIT_ARCH_AARCH64 == 0xc00000b7u);
static_assert(__NR_execve == 221);
static_assert(__NR_execveat == 281);
#endif

using namespace hids::audit;
namespace {
using Lines = std::vector<std::string>;
using Inspect = std::function<void(const Execution&)>;
struct Case { std::string name; Lines lines; bool accepted; Inspect inspect; };

void field(Lines& lines, std::string_view type, std::string_view name, std::string_view value) {
    for (auto& line : lines) {
        if (!line.starts_with("type="+std::string(type)+" ")) continue;
        const auto begin = line.find(" "+std::string(name)+"=");
        assert(begin != std::string::npos);
        const auto end = line.find(' ', begin+1);
        line.replace(begin, end == std::string::npos ? line.size()-begin : end-begin,
                     value.empty() ? "" : " "+std::string(name)+"="+std::string(value));
        return;
    }
    assert(false);
}

ExecutionResult evaluate(const Lines& lines) {
    Limits limits; limits.profile = RecordProfile::auditd_string;
    Reconstructor reconstruction(0, limits);
    for (const auto& line : lines) {
        if (reconstruction.feed(reconstruction.next_offset(), line+"\n", 0) != FeedResult::accepted)
            return {{}, "framing_rejected"};
    }
    const auto event = reconstruction.take_ready();
    if (!event || reconstruction.take_ready()) return {{}, "unexpected_event_count"};
#ifdef HIDS_M3_AUPARSE
    return validate_auparse_execution(*event);
#else
    return validate_execution(*event);
#endif
}
}

int main(int argc, char** argv) {
    if (argc != 2) return 64;
    std::ifstream input("tests/fixtures/audit/structural-exec.log");
    assert(input);
    Lines original;
    for (std::string line; std::getline(input, line);) {
        if (line.starts_with("type=EOE ")) line += ' ';
        original.push_back(std::move(line));
    }
    assert(original.size() == 6);
    std::vector<Case> cases;
    const auto add = [&](std::string name, std::string_view type, std::string_view key,
                         std::string_view value, bool accepted, Inspect inspect = {}) {
        auto lines = original; field(lines,type,key,value);
        cases.push_back({std::move(name),std::move(lines),accepted,std::move(inspect)});
    };
    cases.push_back({"baseline",original,true,{}});
    for (auto key : {"pid", "ppid", "uid", "euid", "suid", "fsuid", "auid", "ses"}) {
        add(std::string(key)+"_uint32_max","SYSCALL",key,"4294967295",true);
        add(std::string(key)+"_overflow","SYSCALL",key,"4294967296",false);
        add(std::string(key)+"_negative","SYSCALL",key,"-1",false);
        add(std::string(key)+"_positive_sign","SYSCALL",key,"+1",false);
        add(std::string(key)+"_missing","SYSCALL",key,"",false);
        add(std::string(key)+"_zero","SYSCALL",key,"0",std::string_view(key)!="pid");
    }
    add("auid_unset","SYSCALL","auid","4294967295",true,[](const Execution& e){assert(!e.auid);});
    add("auid_zero_is_known","SYSCALL","auid","0",true,[](const Execution& e){assert(e.auid && *e.auid==0);});
    add("session_unset","SYSCALL","ses","4294967295",true,[](const Execution& e){assert(!e.session);});
    add("session_zero_is_known","SYSCALL","ses","0",true,[](const Execution& e){assert(e.session && *e.session==0);});
    add("auid_below_sentinel","SYSCALL","auid","4294967294",true,[](const Execution& e){assert(e.auid && *e.auid==4294967294u);});
    add("execveat","SYSCALL","syscall","281",true,[](const Execution& e){assert(e.syscall==281);});
    for (auto syscall : {"59", "0", "-1", "+221", "4294967296", "execve"})
        add("syscall_"+std::string(syscall),"SYSCALL","syscall",syscall,false);
    for (auto arch : {"c000003e", "40000028", "c00000b", "0xc00000b7", "xxxxxxxx"})
        add("arch_"+std::string(arch),"SYSCALL","arch",arch,false);
    add("arch_uppercase","SYSCALL","arch","C00000B7",true);
    add("exit_positive","SYSCALL","exit","1",false);
    add("exit_positive_sign","SYSCALL","exit","+0",false);
    add("exit_below_int64_min","SYSCALL","exit","-9223372036854775809",false);
    add("exit_above_int64_max","SYSCALL","exit","9223372036854775808",false);
    add("success_no_with_zero","SYSCALL","success","no",false);
    add("success_unsupported","SYSCALL","success","true",false);
    for (auto result : {"-2", "-9223372036854775808"}) {
        auto lines=original;field(lines,"SYSCALL","success","no");field(lines,"SYSCALL","exit",result);
        cases.push_back({"complete_failed_"+std::string(result),lines,true,[](const Execution& e){assert(!e.success && e.result<0);}});
    }
    for (const auto& [key, limit] : std::vector<std::pair<std::string,std::size_t>>{{"exe",4096},{"comm",256}}) {
        add(key+"_quoted_limit","SYSCALL",key,"\""+std::string(limit,'x')+"\"",true);
        add(key+"_quoted_over_limit","SYSCALL",key,"\""+std::string(limit+1,'x')+"\"",false);
        std::string hexadecimal;
        for (std::size_t i=0;i<limit;++i) hexadecimal += "FF";
        add(key+"_hex_limit","SYSCALL",key,hexadecimal,true);
        add(key+"_hex_over_limit","SYSCALL",key,hexadecimal+"FF",false);
        for (auto bad : {"\"\"", "00", "410042", "4", "4a", "0x41", "(null)"})
            add(key+"_invalid_"+std::string(bad),"SYSCALL",key,bad,false);
    }
    add("exe_non_utf8","SYSCALL","exe","FF",true,[](const Execution& e){assert(e.exe_base64=="/w==");});
    add("comm_non_utf8","SYSCALL","comm","FFFE",true,[](const Execution& e){assert(e.comm_base64=="//4=");});
    add("comm_space_hex","SYSCALL","comm","612062",true,[](const Execution& e){assert(e.comm_base64=="YSBi");});
    add("comm_space_quoted","SYSCALL","comm","\"a b\"",false);
    add("cwd_nul","CWD","cwd","410042",false);
    add("proctitle_nul","PROCTITLE","proctitle","41004200",true,[](const Execution& e){assert(e.proctitle_present);});
    add("proctitle_quoted","PROCTITLE","proctitle","\"private\"",false);
    add("path_count_mismatch","SYSCALL","items","2",false);
    add("path_index_gap","PATH","item","1",false);
    add("path_parent_unsupported","PATH","nametype","PARENT",false);
    add("path_nul","PATH","name","410042",false);
    add("argc_overflow","EXECVE","argc","18446744073709551616",false);
    add("argc_mismatch","EXECVE","argc","3",false);
    for (auto fraction : {"1", "12", "123", "1234", "12345", "123456", "1234567", "12345678", "123456789"}) {
        auto lines=original;
        for(auto& line:lines) {
            const auto where=line.find(".123:100");assert(where!=std::string::npos);
            line.replace(where,4,"."+std::string(fraction));
        }
        cases.push_back({"fraction_"+std::string(fraction),lines,true,[fraction](const Execution& e){assert(e.key.fraction==fraction);}});
    }
    for(auto suffix : {" unknown=1", " uid=1000"}) {
        auto lines=original;lines.front()+=suffix;
        cases.push_back({"syscall_extra_"+std::string(suffix),lines,false,{}});
    }
    {
        auto lines=original; lines.insert(lines.end()-1,lines[2]);
        cases.push_back({"duplicate_context",lines,false,{}});
    }
    {
        auto lines=original; lines.erase(lines.begin()+1);
        cases.push_back({"missing_execve",lines,false,{}});
    }
    {
        auto lines=original;lines.pop_back();
        cases.push_back({"missing_eoe",lines,false,{}});
    }
    std::ofstream report(argv[1]);assert(report);
    report << "case\texpected\tactual\terror\n";
    unsigned failed=0;
    for(const auto& item:cases) {
        const auto result=evaluate(item.lines);
        const bool accepted=result.execution.has_value();
        report << item.name << '\t' << item.accepted << '\t' << accepted << '\t' << result.error << '\n';
        if(accepted!=item.accepted) { ++failed;std::cerr << item.name << ": " << result.error << '\n'; }
        if(accepted && item.inspect) item.inspect(*result.execution);
    }
    if(failed) return 1;
#ifdef HIDS_M3_AUPARSE
    std::cout << "PASS: " << cases.size() << " native-profile cases linked to libauparse\n";
#else
    std::cout << "PASS: " << cases.size() << " native-profile semantic cases (libauparse not exercised)\n";
#endif
}
