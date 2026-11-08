#pragma once
#include "hids/journal/contract.hpp"
#include <optional>
#include <utility>
#include <vector>
namespace hids::journal {
struct Entry {
    std::string cursor,boot,realtime_us,monotonic_us;
    std::vector<std::pair<std::string,std::string>> fields;
    std::optional<std::string> rejection;
};
struct JournalIo {
    virtual ~JournalIo()=default;
    virtual void open()=0;
    virtual void filter()=0;
    virtual std::optional<std::string> tail()=0;
    virtual bool seek_exact(const std::string&)=0;
    virtual std::optional<Entry> next()=0;
    virtual int wait(unsigned timeout_ms)=0; // 0 no change, 1 append, 2 invalidation.
    virtual void close() noexcept=0;
};
// Explicit injectable match builder; AND within each branch, OR between branches.
struct MatchIo {
    virtual ~MatchIo()=default;
    virtual void match(std::string_view)=0;
    virtual void disjunction()=0;
};
void ssh_filter(MatchIo&);
Json normalize(const Entry&,const std::string& source,const std::string& activation,
               std::uint64_t revision,const Json& observation);
struct Activation {
    bool authorized=false,initialized=false;
    std::string source,activation;
    std::uint64_t revision=0;
    std::optional<std::string> cursor;
};
// One serialized owner, no background thread or automatic reopen. Caller persists
// boundary/record then confirms it; no progress/next read while pending.
class JournalCollector {
public:
    explicit JournalCollector(JournalIo& io):io_(io){}
    ~JournalCollector(){stop();}
    JournalCollector(const JournalCollector&)=delete;
    JournalCollector& operator=(const JournalCollector&)=delete;
    void start(const Activation&);
    bool boundary_pending() const{return boundary_pending_;}
    std::optional<std::string> boundary() const{return state_.cursor;}
    void boundary_committed();
    std::optional<Json> poll_once(const Json& observation,unsigned timeout_ms=100);
    std::optional<Json> poll_with_observation(const std::function<Json()>&,unsigned timeout_ms=100);
    void committed(std::string_view event_id,std::uint64_t revision);
    void stop() noexcept;
    bool running() const{return open_;}
private:
    JournalIo& io_;
    Activation state_;
    bool open_=false,boundary_pending_=false;
    std::optional<Json> pending_;
};
// Native implementation is separate and never instantiated by fixture tests.
class LinuxJournalIo final : public JournalIo,private MatchIo {
public:
    LinuxJournalIo()=default;
    LinuxJournalIo(const LinuxJournalIo&)=delete;
    LinuxJournalIo& operator=(const LinuxJournalIo&)=delete;
    ~LinuxJournalIo() override {close();}
    void open() override;
    void filter() override;
    std::optional<std::string> tail() override;
    bool seek_exact(const std::string&) override;
    std::optional<Entry> next() override;
    int wait(unsigned) override;
    void close() noexcept override;
private:
    void* journal_=nullptr;
    void match(std::string_view) override;
    void disjunction() override;
};
}
