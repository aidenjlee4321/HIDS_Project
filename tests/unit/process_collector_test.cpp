// Offline only: fake I/O and in-memory kernel-format packets, no live socket.
#include "hids/process_collector.hpp"
#include <linux/cn_proc.h>
#include <linux/connector.h>
#include <linux/netlink.h>
#include <cassert>
#include <cerrno>
#include <climits>
#include <cstring>
#include <deque>
#include <vector>
#include <algorithm>
#include <cstdio>
using namespace hids::process;
using Bytes = std::vector<std::byte>;
constexpr auto nh = sizeof(nlmsghdr), ch = sizeof(cn_msg);
Bytes packet(const proc_event& event, std::uint32_t seq = 1, std::uint32_t ack = 0) {
    Bytes bytes(nh + ch + sizeof(event));
    nlmsghdr n{}; n.nlmsg_type = NLMSG_DONE; n.nlmsg_len = bytes.size();
    cn_msg c{}; c.id.idx = CN_IDX_PROC; c.id.val = CN_VAL_PROC;
    c.len = sizeof(event); c.seq = seq; c.ack = ack;
    std::memcpy(bytes.data(), &n, nh); std::memcpy(bytes.data()+nh, &c, ch);
    std::memcpy(bytes.data()+nh+ch, &event, sizeof(event));
    return bytes;
}
proc_event lifecycle(proc_cn_event kind, std::uint32_t cpu = 3) {
    proc_event e{}; e.what = kind; e.cpu = cpu; e.timestamp_ns = 3468495538951ULL;
    if (kind == PROC_EVENT_FORK) e.event_data.fork = {13178, 13178, 13184, 13184};
    else if (kind == PROC_EVENT_EXEC) e.event_data.exec = {13184, 13184};
    else if (kind == PROC_EVENT_EXIT) {
        e.event_data.exit.process_pid = 13184; e.event_data.exit.process_tgid = 13184;
        e.event_data.exit.parent_pid = 13178; e.event_data.exit.parent_tgid = 13178;
        e.event_data.exit.exit_code = 7U << 8; e.event_data.exit.exit_signal = 17;
    }
    return e;
}
struct Capture final : Sink {
    std::vector<NativeEvent> events;
    std::vector<Diagnostic> diagnostics;
    std::vector<Status> statuses;
    void on_event(const NativeEvent& e) noexcept override { events.push_back(e); }
    void on_diagnostic(const Diagnostic& d) noexcept override { diagnostics.push_back(d); }
    void on_status(const Status& s) noexcept override { statuses.push_back(s); }
    int count(Reason reason) const {
        return static_cast<int>(std::count_if(diagnostics.begin(),diagnostics.end(),
            [reason](const auto& d){ return d.reason == reason; }));
    }
};
struct FakeIo final : ConnectorIo {
    int open_error = 0, listen_error = 0, ignore_error = 0, close_error = 0;
    unsigned opens = 0, closes = 0;
    std::vector<Bytes> writes;
    struct Item { ReadResult result; Bytes bytes; };
    std::deque<Item> reads;
    std::chrono::milliseconds last_timeout{};
    OpenResult open() noexcept override { ++opens; return {open_error,42}; }
    int send(std::span<const std::byte> b) noexcept override {
        writes.emplace_back(b.begin(),b.end());
        proc_input in{}; std::memcpy(&in,b.data()+nh+ch,sizeof(in));
        return in.mcast_op == PROC_CN_MCAST_LISTEN ? listen_error : ignore_error;
    }
    int close() noexcept override { ++closes; return close_error; }
    ReadResult receive(std::span<std::byte> b, std::chrono::milliseconds t) noexcept override {
        last_timeout=t;
        if (reads.empty()) return {ReadKind::timeout};
        auto item=reads.front(); reads.pop_front();
        if (item.bytes.size() <= b.size()) std::copy(item.bytes.begin(),item.bytes.end(),b.begin());
        return item.result;
    }
    void data(Bytes b) { reads.push_back({{ReadKind::data,b.size()},std::move(b)}); }
    void result(ReadKind k,int error=0) { reads.push_back({{k,0,error},{}}); }
    std::uint32_t cookie() const {
        cn_msg c{}; std::memcpy(&c,writes.front().data()+nh,ch); return c.ack;
    }
};
struct Decoded final : DecodeSink {
    std::vector<NativeEvent> events;
    int bad = 0, overruns = 0, acks = 0, kernel_errors = 0, unexpected = 0;
    void native_event(const NativeEvent& e) noexcept override { events.push_back(e); }
    void acknowledgement(std::uint32_t,std::uint32_t) noexcept override { ++acks; }
    void protocol_diagnostic(Reason r,int = 0) noexcept override {
        if (r==Reason::malformed) ++bad;
        if (r==Reason::receive_overrun) ++overruns;
        if (r==Reason::kernel_error) ++kernel_errors;
        if (r==Reason::unexpected_event) ++unexpected;
    }
};
void parser_tests() {
    Decoded d;
    auto b=packet(lifecycle(PROC_EVENT_FORK));
    // Exhaustively truncate a valid datagram; never deliver a partial event.
    for (std::size_t n=0;n<b.size();++n) decode({b.data(),n},d);
    assert(d.bad==static_cast<int>(b.size()) && d.events.empty());
    Bytes unaligned(1); unaligned.insert(unaligned.end(),b.begin(),b.end());
    decode({unaligned.data()+1,b.size()},d);
    assert(d.events.size()==1 && d.events[0].parent->tgid==13178);
    auto exec=packet(lifecycle(PROC_EVENT_EXEC));
    decode(exec,d); assert(!d.events.back().parent && !d.events.back().native_exit_status);
    auto exited=packet(lifecycle(PROC_EVENT_EXIT)); decode(exited,d);
    assert(d.events.back().native_exit_status==(7U<<8)); // Do not silently reinterpret raw encoding.
    assert(d.events.back().kernel_monotonic_ns==3468495538951ULL);
    b.insert(b.end(),exec.begin(),exec.end()); decode(b,d); assert(d.events.size()==5);
    auto invalid=lifecycle(PROC_EVENT_EXEC); invalid.event_data.exec.process_pid=-1;
    decode(packet(invalid),d); assert(d.events.size()==5);
    invalid=lifecycle(PROC_EVENT_EXEC); invalid.event_data.exec.process_tgid=12345;
    decode(packet(invalid),d); assert(d.events.back().tid!=d.events.back().tgid); // Threads preserved.
    auto wrong=exec; cn_msg c{}; std::memcpy(&c,wrong.data()+nh,ch); c.len=39;
    std::memcpy(wrong.data()+nh,&c,ch); const auto before=d.bad; decode(wrong,d); assert(d.bad==before+1);
    wrong=exec; std::memcpy(&c,wrong.data()+nh,ch); c.id.val=999;
    std::memcpy(wrong.data()+nh,&c,ch); decode(wrong,d); assert(d.bad==before+2);
    nlmsghdr n{}; n.nlmsg_len=nh; n.nlmsg_type=NLMSG_OVERRUN;
    decode({reinterpret_cast<std::byte*>(&n),nh},d); assert(d.overruns==1);
    n.nlmsg_type=NLMSG_ERROR; n.nlmsg_len=nh+sizeof(nlmsgerr);
    Bytes err(n.nlmsg_len); nlmsgerr e{}; e.error=INT_MIN;
    std::memcpy(err.data(),&n,nh); std::memcpy(err.data()+nh,&e,sizeof(e));
    decode(err,d); assert(d.kernel_errors==1);
    e.error=0; std::memcpy(err.data()+nh,&e,sizeof(e)); decode(err,d); assert(d.acks==0);
    proc_event unknown{}; unknown.what=PROC_EVENT_UID;
    decode(packet(unknown),d); assert(d.unexpected==1);
    // Deterministic offline fuzz-like prefix/length mutations, never transmitted.
    for (std::uint32_t length : {0U,1U,15U,17U,UINT_MAX}) {
        wrong=exec; std::memcpy(&n,wrong.data(),nh); n.nlmsg_len=length;
        std::memcpy(wrong.data(),&n,nh); decode(wrong,d);
    }
    for (bool listen : {false,true}) {
        const auto bytes=control_packet(listen,42,1234);
        proc_input in{}; std::memcpy(&in,bytes.data()+nh+ch,sizeof(in));
        assert(in.mcast_op==(listen?PROC_CN_MCAST_LISTEN:PROC_CN_MCAST_IGNORE));
        assert(static_cast<std::uint32_t>(in.event_type)==0x80000003U);
    }
}
void lifecycle_tests() {
    FakeIo io; Capture out;
    {
        Collector c(io,out); assert(c.start()); assert(!c.start()); assert(io.writes.size()==1);
        assert(c.status().state==State::unconfirmed && !c.status().delivery_observed);
        c.poll_once(std::chrono::milliseconds{500}); assert(io.last_timeout.count()==100);
        c.poll_once(std::chrono::milliseconds{-1}); assert(io.last_timeout.count()==0);
        io.data(packet(lifecycle(PROC_EVENT_FORK,2),1)); c.poll_once();
        io.data(packet(lifecycle(PROC_EVENT_EXEC,3),2)); c.poll_once();
        io.data(packet(lifecycle(PROC_EVENT_EXIT,3),3)); c.poll_once();
        assert(out.events.size()==3 && out.count(Reason::sequence_discontinuity)==0);
        assert(c.status().delivery_observed && !c.status().subscription_acknowledged);
        // Unrelated process data is collected in production; no hidden child-only assumption.
        auto other=lifecycle(PROC_EVENT_EXEC,0); other.event_data.exec={555,555};
        io.data(packet(other,10)); c.poll_once(); io.data(packet(other,12)); c.poll_once();
        assert(out.count(Reason::sequence_discontinuity)==1 && !c.status().incomplete_interval);
        auto& diag=out.diagnostics.back(); assert(diag.cpu==0 && diag.previous_sequence==10 && diag.current_sequence==12);
        other.cpu=1; io.data(packet(other,UINT_MAX)); c.poll_once();
        io.data(packet(other,0)); c.poll_once(); assert(out.count(Reason::sequence_discontinuity)==1);
        io.data(packet(other,0)); c.poll_once(); assert(out.count(Reason::sequence_discontinuity)==2);
        other.cpu=4096; io.data(packet(other,1)); c.poll_once();
        assert(out.count(Reason::sequence_tracking_unavailable)==1);
        proc_event ack{}; ack.what=PROC_EVENT_NONE;
        io.data(packet(ack,999,io.cookie()+2)); c.poll_once(); assert(!c.status().subscription_acknowledged);
        io.data(packet(ack,999,io.cookie()+1)); c.poll_once(); assert(c.status().subscription_acknowledged);
        io.result(ReadKind::no_buffer,ENOBUFS); c.poll_once();
        io.result(ReadKind::truncated); c.poll_once();
        io.result(ReadKind::foreign_sender); c.poll_once();
        assert(c.status().state==State::degraded && c.status().incomplete_interval);
        other.cpu=1; io.data(packet(other,1)); c.poll_once(); assert(c.status().state==State::degraded);
        io.result(ReadKind::interrupted,EINTR); c.poll_once(); assert(io.writes.size()==1);
        assert(out.count(Reason::receive_interrupted)==1);
        c.stop(); c.stop(); assert(io.writes.size()==2 && io.closes==1);
        c.poll_once(); assert(out.events.size()==10);
        assert(c.start()); assert(c.status().session==2 && !c.status().delivery_observed);
        assert(!c.status().subscription_acknowledged && !c.status().incomplete_interval);
        io.data(packet(lifecycle(PROC_EVENT_EXEC,1),100)); c.poll_once();
        assert(out.count(Reason::sequence_discontinuity)==2); // Restart establishes new baseline.
    }
    assert(io.writes.size()==4 && io.closes==2);
}
void acknowledgement_state_tests() {
    {
        FakeIo io; Capture out; Collector c(io,out); assert(c.start());
        assert(c.status().state==State::unconfirmed && !c.status().subscription_acknowledged);
        assert(!c.status().delivery_observed);
        proc_event ack{}; ack.what=PROC_EVENT_NONE;
        io.data(packet(ack,999,io.cookie()+1)); c.poll_once();
        assert(c.status().state==State::acknowledged && c.status().subscription_acknowledged);
        assert(!c.status().delivery_observed && out.events.empty());
        assert(out.statuses.back().state==State::acknowledged);
        io.data(packet(lifecycle(PROC_EVENT_EXEC))); c.poll_once();
        assert(c.status().state==State::observing && c.status().subscription_acknowledged);
        assert(c.status().delivery_observed && out.events.size()==1);
    }
    {
        FakeIo io; Capture out; Collector c(io,out); assert(c.start());
        io.data(packet(lifecycle(PROC_EVENT_EXEC))); c.poll_once();
        assert(c.status().state==State::observing && c.status().delivery_observed);
        assert(!c.status().subscription_acknowledged);
        proc_event ack{}; ack.what=PROC_EVENT_NONE;
        io.data(packet(ack,999,io.cookie()+1)); c.poll_once();
        assert(c.status().state==State::observing && c.status().subscription_acknowledged);
    }
    {
        FakeIo io; Capture out; Collector c(io,out); assert(c.start());
        io.result(ReadKind::no_buffer,ENOBUFS); c.poll_once();
        proc_event ack{}; ack.what=PROC_EVENT_NONE;
        io.data(packet(ack,999,io.cookie()+1)); c.poll_once();
        assert(c.status().state==State::degraded && c.status().subscription_acknowledged);
        assert(!c.status().delivery_observed && c.status().incomplete_interval);
        io.data(packet(lifecycle(PROC_EVENT_EXEC))); c.poll_once();
        assert(c.status().state==State::degraded && c.status().delivery_observed);
    }
    {
        FakeIo io; Capture out; Collector c(io,out); assert(c.start());
        proc_event ack{}; ack.what=PROC_EVENT_NONE; ack.event_data.ack.err=EPERM;
        io.data(packet(ack,999,io.cookie()+1)); c.poll_once();
        assert(c.status().state==State::unavailable && !c.status().subscription_acknowledged);
        assert(!c.status().delivery_observed && out.events.empty());
        assert(out.count(Reason::kernel_error)==1 && io.writes.size()==2 && io.closes==1);
    }
}
void failure_tests() {
    for (int error : {EACCES,EPROTONOSUPPORT,ENOENT}) {
        FakeIo io; Capture out; io.open_error=error;
        Collector c(io,out); assert(!c.start());
        assert(c.status().state==State::unavailable && io.writes.empty());
        assert(out.diagnostics.back().error==error);
        c.poll_once(); assert(io.opens==1); // no automatic reconnect
    }
    {
        FakeIo io; Capture out; io.listen_error=EINTR; io.ignore_error=EIO;
        Collector c(io,out); assert(!c.start());
        assert(io.writes.size()==2 && io.closes==1);
        assert(out.count(Reason::unsubscribe_failed)==1 && c.status().incomplete_interval);
    }
    {
        FakeIo io; Capture out; Collector c(io,out); assert(c.start());
        proc_event ack{}; ack.what=PROC_EVENT_NONE; ack.event_data.ack.err=EPERM;
        io.data(packet(ack,999,io.cookie()+1)); c.poll_once();
        assert(c.status().state==State::unavailable && io.writes.size()==2 && io.closes==1);
        io.result(ReadKind::timeout); c.poll_once(); assert(io.opens==1);
    }
    {
        FakeIo io; Capture out; Collector c(io,out); assert(c.start());
        io.result(ReadKind::error,EIO); c.poll_once();
        assert(c.status().state==State::unavailable && io.writes.size()==2 && io.closes==1);
    }
    {
        FakeIo io; Capture out; io.close_error=EIO;
        Collector c(io,out); assert(c.start()); c.stop();
        assert(out.count(Reason::close_failed)==1 && c.status().incomplete_interval);
    }
    {
        FakeIo io; Capture out; Collector c(io,out); assert(c.start());
        io.data(Bytes{std::byte{0}}); c.poll_once();
        assert(out.count(Reason::malformed)==1 && c.status().state==State::degraded);
        nlmsghdr n{}; n.nlmsg_type=NLMSG_OVERRUN; n.nlmsg_len=nh;
        Bytes b(nh); std::memcpy(b.data(),&n,nh); io.data(b); c.poll_once();
        assert(out.count(Reason::receive_overrun)==1);
    }
    // Source isolation: one unavailable adapter cannot stop an independent healthy caller.
    FakeIo broken,healthy; Capture a,b; broken.open_error=EACCES;
    Collector x(broken,a),y(healthy,b); assert(!x.start() && y.start());
    healthy.data(packet(lifecycle(PROC_EVENT_EXEC))); y.poll_once(); assert(b.events.size()==1);
}
int main() {
    parser_tests(); lifecycle_tests(); acknowledgement_state_tests(); failure_tests();
    std::puts("PASS: native decoder, bounded lifecycle, per-CPU sequences, ACK/delivery separation, degradation, cleanup and isolation (offline)");
}
