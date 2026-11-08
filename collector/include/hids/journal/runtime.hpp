#pragma once
#include "hids/journal_collector.hpp"
#include "hids/journal/transport.hpp"
namespace hids::journal {
// Serialized production lifecycle; JournalIo/Channel are replaceable only in tests.
class ReaderRuntime {
public:
    ReaderRuntime(JournalIo&,Channel&,std::string source,std::string producer,
                  std::function<std::string()> clock=pilot::utc_now);
    ~ReaderRuntime(){stop();}
    bool start(); // false = explicitly inactive; never opens journal in that case.
    bool step();  // false = cancelled. No automatic restart or activation switch.
    void stop() noexcept;
    const std::string& failure() const{return failure_;}
private:
    JournalCollector collector_;
    Channel& channel_;
    std::string source_,producer_,activation_,failure_;
    std::function<std::string()> clock_;
    std::uint64_t revision_=0;
    bool connected_=false,active_=false;
    Json progress(Deadline);
    void connect(Deadline);
    Json exchange(const Json&);
    void report_gap(const std::string&) noexcept;
};
}
