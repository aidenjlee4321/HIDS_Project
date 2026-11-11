#include "hids/audit/execution.hpp"
#include "hids/audit/plugin_session.hpp"
#ifdef HIDS_M3_AUPARSE
#include "hids/audit/auparse_execution.hpp"
#include <auparse.h>
#endif
#include <cassert>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <new>
#include <string>

// Test executable only. Inject one failed C++ allocation at each reachable point;
// ordinary allocation resumes during cleanup/reporting. C-library malloc calls
// are not intercepted by this operator.
namespace { long fail_after=-1; }
void* operator new(std::size_t size) {
    if(fail_after==0) {fail_after=-1;throw std::bad_alloc();}
    if(fail_after>0) --fail_after;
    if(void* value=std::malloc(size ? size : 1)) return value;
    throw std::bad_alloc();
}
void* operator new[](std::size_t size) {return ::operator new(size);}
void operator delete(void* value) noexcept {std::free(value);}
void operator delete[](void* value) noexcept {std::free(value);}
void operator delete(void* value,std::size_t) noexcept {std::free(value);}
void operator delete[](void* value,std::size_t) noexcept {std::free(value);}

#ifdef HIDS_M3_AUPARSE
namespace {
enum class Fault {none,init,event,extra_event,record,next_record,field,next_field,text,type,name,value};
Fault fault=Fault::none;
unsigned event_calls=0;
}
extern "C" {
auparse_state_t* __real_auparse_init(ausource_t,const void*);
int __real_auparse_next_event(auparse_state_t*);
int __real_auparse_first_record(auparse_state_t*);
int __real_auparse_next_record(auparse_state_t*);
int __real_auparse_first_field(const auparse_state_t*);
int __real_auparse_next_field(const auparse_state_t*);
const char* __real_auparse_get_record_text(const auparse_state_t*);
const char* __real_auparse_get_type_name(const auparse_state_t*);
const char* __real_auparse_get_field_name(const auparse_state_t*);
const char* __real_auparse_get_field_str(const auparse_state_t*);
auparse_state_t* __wrap_auparse_init(ausource_t source,const void* bytes) {return fault==Fault::init ? nullptr : __real_auparse_init(source,bytes);}
int __wrap_auparse_next_event(auparse_state_t* state) {
    ++event_calls;
    if(fault==Fault::event) return -1;
    if(fault==Fault::extra_event && event_calls>1) return 1;
    return __real_auparse_next_event(state);
}
int __wrap_auparse_first_record(auparse_state_t* state) {return fault==Fault::record ? -1 : __real_auparse_first_record(state);}
int __wrap_auparse_next_record(auparse_state_t* state) {return fault==Fault::next_record ? -1 : __real_auparse_next_record(state);}
int __wrap_auparse_first_field(const auparse_state_t* state) {return fault==Fault::field ? -1 : __real_auparse_first_field(state);}
int __wrap_auparse_next_field(const auparse_state_t* state) {return fault==Fault::next_field ? -1 : __real_auparse_next_field(state);}
const char* __wrap_auparse_get_record_text(const auparse_state_t* state) {return fault==Fault::text ? nullptr : __real_auparse_get_record_text(state);}
const char* __wrap_auparse_get_type_name(const auparse_state_t* state) {return fault==Fault::type ? nullptr : __real_auparse_get_type_name(state);}
const char* __wrap_auparse_get_field_name(const auparse_state_t* state) {return fault==Fault::name ? nullptr : __real_auparse_get_field_name(state);}
const char* __wrap_auparse_get_field_str(const auparse_state_t* state) {return fault==Fault::value ? nullptr : __real_auparse_get_field_str(state);}
}
#endif

using namespace hids::audit;
int main() {
    std::ifstream input("tests/fixtures/audit/structural-exec.log");assert(input);
    Limits limits;limits.profile=RecordProfile::auditd_string;
    Reconstructor reconstruction(0,limits);
    std::string fixture;
    for(std::string line;std::getline(input,line);) {
        if(line.starts_with("type=EOE ")) line+=' ';
        line+='\n';fixture+=line;
        assert(reconstruction.feed(reconstruction.next_offset(),line,0)==FeedResult::accepted);
    }
    const auto event=reconstruction.take_ready();assert(event);
    unsigned total=0;
    const auto allocations=[&](auto validate,std::string_view expected) {
        bool completed=false;
        unsigned failures=0;
        for(long index=0;index<1000;++index) {
            fail_after=index;
            ExecutionResult result;
            try {result=validate(*event);}
            catch(const std::bad_alloc&) {
                fail_after=-1;
                std::cerr << "FAIL: allocation escaped typed parser result at point " << index << '\n';
                return false;
            }
            fail_after=-1;
            if(result.execution) {completed=true;break;}
            assert(result.error==expected || result.error=="execution_allocation");
            ++failures;
        }
        assert(completed && failures>0);
        total+=failures;
        return true;
    };
    const auto raw=event->records.front()->raw+"\n";
    bool parsed_all=false;
    for(long index=0;index<1000;++index) {
        fail_after=index;
        ParseResult result;
        try {result=parse_record(raw,0,65536,RecordProfile::auditd_string);}
        catch(const std::bad_alloc&) {fail_after=-1;std::cerr << "FAIL: framing allocation escaped\n";return 1;}
        fail_after=-1;
        if(result.record) {parsed_all=true;break;}
        assert(result.error=="allocation_failure");++total;
    }
    assert(parsed_all);
    if(!allocations(validate_execution,"execution_allocation")) return 1;
#ifdef HIDS_M3_AUPARSE
    if(!allocations(validate_auparse_execution,"auparse_allocation")) return 1;
    unsigned api_faults=0;
    for(const auto mode : {Fault::init,Fault::event,Fault::extra_event,Fault::record,Fault::next_record,
                           Fault::field,Fault::next_field,Fault::text,Fault::type,Fault::name,Fault::value}) {
        fault=mode;event_calls=0;
        const auto result=validate_auparse_execution(*event);
        assert(!result.execution && !result.error.empty());
        fault=Fault::none;event_calls=0;
        assert(validate_auparse_execution(*event).execution);
        ++api_faults;
    }
    std::cout << "PASS: " << api_faults << " libauparse API failures yield no execution and fresh-state recovery succeeds\n";
#endif
    for(const auto error : {"execution_allocation","auparse_allocation","auparse_init","auparse_unavailable"}) {
        unsigned finalized=0;
        PluginSession session([](const Record&) {return PluginSession::Admission::admitted;},
            [&](const Event&,const ExecutionResult&) {++finalized;return true;},
            [error](const Event&) {return ExecutionResult{{},error};});
        assert(!session.consume(fixture,0));
        const auto expected=std::string_view(error).starts_with("auparse_i") || std::string_view(error)=="auparse_unavailable" ? "parser_failure" : "allocation_failure";
        assert(session.error()==expected && finalized==0);
    }
    bool session_completed=false;
    for(long index=0;index<1000;++index) {
        unsigned finalized=0;
        PluginSession session([](const Record&) {return PluginSession::Admission::admitted;},
            [&](const Event&,const ExecutionResult& result) {assert(result.execution);++finalized;return true;},
#ifdef HIDS_M3_AUPARSE
            validate_auparse_execution);
#else
            validate_execution);
#endif
        fail_after=index;
        bool consumed;
        try {consumed=session.consume(fixture,0);}
        catch(const std::bad_alloc&) {fail_after=-1;std::cerr << "FAIL: session allocation escaped\n";return 1;}
        fail_after=-1;
        if(consumed) {assert(finalized==1);session_completed=true;break;}
        assert(finalized==0 && session.error()=="allocation_failure");++total;
    }
    assert(session_completed);
    std::cout << "PASS: " << total << " C++ allocation cuts return typed failure without partial output; session stops before event finalization\n";
}
