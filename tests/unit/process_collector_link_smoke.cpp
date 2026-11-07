// Link all three real production translation units, without opening a socket.
#include "hids/linux_process_connector.hpp"
#include <cassert>

class SilentSink final : public hids::process::Sink {
public:
    void on_event(const hids::process::NativeEvent&) noexcept override {}
    void on_diagnostic(const hids::process::Diagnostic&) noexcept override {}
    void on_status(const hids::process::Status&) noexcept override {}
};
int main() {
    hids::process::LinuxConnectorIo io;
    SilentSink sink;
    hids::process::Collector collector(io, sink);
    assert(collector.status().state == hids::process::State::stopped);
    collector.poll_once(); // Stopped adapter: must not open/read a socket.
    collector.stop();
    // Deliberately never call start(); constructor/destructor/link check only.
}
