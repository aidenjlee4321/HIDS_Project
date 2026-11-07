// Test-only native packet builder. Never sends a packet or opens netlink.
#include "m1_native_fixture.hpp"
#include <linux/cn_proc.h>
#include <linux/connector.h>
#include <linux/netlink.h>
#include <cstring>

hids::process::NativeEvent decode_fixture(const hids::pilot::Json& j) {
    using namespace hids;
    pilot::validate_native(j);
    proc_event event{};event.what=PROC_EVENT_EXEC;
    event.cpu=j.at("cpu").get<std::uint32_t>();
    event.timestamp_ns=std::stoull(j.at("timestamp_ns").get<std::string>());
    event.event_data.exec.process_pid=j.at("pid").get<std::int32_t>();
    event.event_data.exec.process_tgid=j.at("tgid").get<std::int32_t>();
    constexpr auto nh=sizeof(nlmsghdr),ch=sizeof(cn_msg);
    std::array<std::byte,nh+ch+sizeof(event)> bytes{};
    nlmsghdr n{};n.nlmsg_type=NLMSG_DONE;n.nlmsg_len=bytes.size();
    cn_msg c{};c.id.idx=CN_IDX_PROC;c.id.val=CN_VAL_PROC;c.len=sizeof(event);
    c.seq=j.at("connector_sequence").get<std::uint32_t>();
    std::memcpy(bytes.data(),&n,nh);std::memcpy(bytes.data()+nh,&c,ch);
    std::memcpy(bytes.data()+nh+ch,&event,sizeof(event));
    struct Capture final : process::DecodeSink {
        std::optional<process::NativeEvent> value;unsigned count=0,errors=0;
        void native_event(const process::NativeEvent& e) noexcept override {value=e;++count;}
        void acknowledgement(std::uint32_t,std::uint32_t) noexcept override {++errors;}
        void protocol_diagnostic(process::Reason,int) noexcept override {++errors;}
    } sink;
    process::decode(bytes,sink);
    if (sink.count!=1 || sink.errors || !sink.value) throw pilot::Invalid("native_fixture_failed");
    return *sink.value;
}
