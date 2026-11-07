#pragma once
#include "hids/process_collector.hpp"

namespace hids::process {
// Dedicated socket only; never borrowed from or shared with another controller.
// Construct before Collector so Collector unsubscribes before backend destruction.
class LinuxConnectorIo final : public ConnectorIo {
public:
    ~LinuxConnectorIo() override;
    LinuxConnectorIo() = default;
    LinuxConnectorIo(const LinuxConnectorIo&) = delete;
    LinuxConnectorIo& operator=(const LinuxConnectorIo&) = delete;
    OpenResult open() noexcept override;
    int send(std::span<const std::byte>) noexcept override;
    ReadResult receive(std::span<std::byte>, std::chrono::milliseconds) noexcept override;
    int close() noexcept override;
private:
    int fd_ = -1;
    bool guard_owned_ = false;
};
} // namespace hids::process
