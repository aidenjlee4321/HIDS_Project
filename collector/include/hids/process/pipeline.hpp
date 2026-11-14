#pragma once
#include "hids/pilot/contract.hpp"
#include <array>
#include <ctime>
namespace hids::processlive {
using Json=pilot::Json;
inline constexpr std::size_t event_limit=16384,response_limit=1024;
inline constexpr const char* contract="process.lifecycle/0.1.0";
void validate_source(const Json&,std::string_view mode);
void validate(const Json&,const Json& source,std::string_view mode);
Json normalize(const process::NativeEvent&,const std::string& observed,const Json& source,
               const std::string& producer,const std::string& id);
std::string observed_time(const timespec&);
struct Slot {process::NativeEvent event{};timespec observed{};};
class Queue final:public process::Sink {
public:
    using Clock=int(*)(clockid_t,timespec*);
    explicit Queue(Clock clock=::clock_gettime):clock_(clock){}
    void on_event(const process::NativeEvent&) noexcept override;
    void on_diagnostic(const process::Diagnostic&) noexcept override;
    void on_status(const process::Status& value) noexcept override {status=value;}
    bool pop(Slot&) noexcept;
    std::size_t size()const noexcept{return size_;}
    bool failed=false;
    const char* reason="none";
    process::Status status{};
    std::array<std::uint32_t,20> diagnostics{};
    // Nonzero filtering is used only by the owned-fixture acceptance executable.
    int owned_fixture=0;
    unsigned fixture_bits=0;
private:
    Clock clock_;
    std::array<Slot,256> slots_{};
    std::size_t head_=0,size_=0;
};
}
