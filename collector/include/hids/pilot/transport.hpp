#pragma once
#include "hids/pilot/contract.hpp"
#include <chrono>

namespace hids::pilot {
using Clock = std::chrono::steady_clock;
using Deadline = Clock::time_point;
// Injectable socket/time boundary for offline short-I/O and retry tests.
class Channel {
public:
    virtual ~Channel() = default;
    virtual int connect(Deadline) = 0;
    virtual ssize_t write(const void*, std::size_t) = 0;
    virtual ssize_t read(void*, std::size_t) = 0;
    virtual bool wait(bool writing, Deadline) = 0;
    virtual void close() noexcept = 0;
    virtual Deadline now() const { return Clock::now(); }
    virtual void sleep(std::chrono::milliseconds);
    virtual bool cancelled() const { return false; }
};
struct Delivery {
    std::string outcome, code;
    unsigned attempts = 0;
    bool any_sent = false;
};
Delivery transmit(Channel&, const std::string& frozen_line, bool prior_uncertain = false);
class UnixChannel final : public Channel {
public:
    UnixChannel(std::string path, int pid, const std::function<bool()>& cancelled);
    ~UnixChannel() override;
    int connect(Deadline) override;
    ssize_t write(const void*, std::size_t) override;
    ssize_t read(void*, std::size_t) override;
    bool wait(bool, Deadline) override;
    void close() noexcept override;
    bool cancelled() const override;
private:
    std::string path_;
    int peer_pid_, fd_ = -1;
    std::function<bool()> stopped_;
};
} // namespace hids::pilot
