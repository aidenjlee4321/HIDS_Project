#include "hids/audit/execution.hpp"
#include "hids/audit/plugin_session.hpp"
#include "hids/audit/current_tail.hpp"
#ifdef HIDS_M3_AUPARSE
#include "hids/audit/auparse_execution.hpp"
#endif

#include <cassert>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
#include <fcntl.h>
#include <unistd.h>

using namespace hids::audit;
namespace {
void current_tail() {
    int descriptors[2];
    assert(::pipe(descriptors) == 0);
    const auto no_cancel = [] { return false; };
    assert(::write(descriptors[1], "old\n", 4) == 4);
    assert(discard_queued_input(descriptors[0], 4, no_cancel));
    assert((::fcntl(descriptors[0], F_GETFL) & O_NONBLOCK) == 0);
    assert(::write(descriptors[1], "new\n", 4) == 4);
    char bytes[4];
    assert(::read(descriptors[0], bytes, sizeof(bytes)) == 4);
    assert(std::string_view(bytes, 4) == "new\n");
    assert(::write(descriptors[1], "12345", 5) == 5);
    assert(!discard_queued_input(descriptors[0], 4, no_cancel));
    assert(::write(descriptors[1], "keep", 4) == 4);
    assert(!discard_queued_input(descriptors[0], 4, [] { return true; }));
    assert(::read(descriptors[0], bytes, sizeof(bytes)) == 4);
    assert(std::string_view(bytes, 4) == "keep");
    ::close(descriptors[1]);
    assert(!discard_queued_input(descriptors[0], 4, no_cancel));
    ::close(descriptors[0]);
}
std::string line(std::string_view type, unsigned serial, std::string_view payload = "x=fixture") {
    return "type="+std::string(type)+" msg=audit(1794096000.123:"+std::to_string(serial)+"):"+
        (payload.empty() ? "" : " "+std::string(payload))+"\n";
}
void append(Reconstructor& r, const std::string& value, std::uint64_t now = 0) {
    assert(r.feed(r.next_offset(), value, now) == FeedResult::accepted);
}
void observation_clocks() {
    std::ifstream stream("tests/fixtures/audit/structural-exec.log"); assert(stream);
    std::string fixture_bytes;
    for (std::string raw; std::getline(stream,raw);) {
        if (raw.starts_with("type=EOE ")) raw += ' ';
        fixture_bytes += raw+'\n';
    }
    unsigned seen=0,finalized=0,admissions=0;
    PluginSession session([&](const Record&) { ++admissions;return PluginSession::Admission::admitted; },
        [&](const Event& event,const ExecutionResult& result) {
            ++finalized;
            assert(event.first_observed_unix_ns && *event.first_observed_unix_ns==100);
            assert(event.key.seconds=="1794096000" && event.key.fraction=="123");
            assert(result.execution && result.execution->arch==0xc00000b7u);
            return true;
        },validate_execution,{}, {}, {}, {}, [&]() -> std::optional<std::uint64_t> {return 100-seen++;});
    assert(session.consume(fixture_bytes,0) && finalized==1 && admissions==6 && seen==6);
    PluginSession unavailable([&](const Record&) { ++admissions;return PluginSession::Admission::admitted; },
        [&](const Event&,const ExecutionResult&) { ++finalized;return true; },validate_execution,
        {}, {}, {}, {}, []() -> std::optional<std::uint64_t> {return {};});
    assert(!unavailable.consume(fixture_bytes,0));
    assert(unavailable.error()=="observation_clock_unavailable" && admissions==6 && finalized==1);
}
void fixture() {
    std::ifstream stream("tests/fixtures/audit/structural-exec.log"); assert(stream);
    Reconstructor r;
    std::string raw;
    while (std::getline(stream, raw)) append(r, raw+"\n");
    auto e = r.take_ready(); assert(e && !r.take_ready());
    assert(e->records.size() == 6 && e->syscall_seen && e->execve_seen && e->cwd_seen);
    assert(e->path_records == 1 && e->proctitle_seen && e->eoe_seen);
    assert(e->basis == Basis::eoe && e->terminal_seen && e->key.serial == "100");
    assert(validate_execve(*e).empty());
    const auto result = validate_execution(*e);
    assert(result.execution && result.error.empty());
#ifdef HIDS_M3_AUPARSE
    const auto parsed = validate_auparse_execution(*e);
    if (!parsed.execution) std::cerr << parsed.error << '\n';
    assert(parsed.execution && parsed.execution->key == e->key);
    assert(parsed.execution->exe_base64 == result.execution->exe_base64);
#endif
    const auto& execution = *result.execution;
    assert(execution.exe_base64 == "L3Vzci9iaW4vc2xlZXA=" && execution.comm_base64 == "c2xlZXA=");
    assert(execution.uid == 1000 && !execution.auid && execution.session == 7);
    assert(execution.success && execution.path_count == 1 &&
           execution.cwd_present && execution.proctitle_present);

    stream.clear();
    stream.seekg(0);
    Limits limits;
    limits.profile = RecordProfile::auditd_string;
    Reconstructor plugin(0, limits);
    while (std::getline(stream, raw)) {
        if (raw.starts_with("type=SYSCALL")) raw += " tty=(none) subj=unconfined";
        if (raw.starts_with("type=PATH")) raw += " inode=42 dev=08:01 mode=0100755 ouid=0 ogid=0 cap_fe=0";
        if (raw.starts_with("type=EOE")) raw += ' ';
        append(plugin, raw + '\n');
    }
    const auto native = plugin.take_ready();
    assert(native && validate_execution(*native).execution);
    Limits continuation_limits;
    continuation_limits.profile = RecordProfile::auditd_string;
    Reconstructor continuation(0, continuation_limits);
    append(continuation, line("EXECVE", 12, "argc=1 a0_len=4 a0[0]=\"ab\""));
    append(continuation, line("EXECVE", 12, " a0[1]=\"cd\""));
    auto terminal = line("EOE", 12, "");
    terminal.insert(terminal.size() - 1, " ");
    append(continuation, terminal);
    const auto fragmented = continuation.take_ready();
    assert(fragmented && validate_execve(*fragmented).empty());
#ifdef HIDS_M3_AUPARSE
    assert(validate_auparse_execution(*native).execution);
#endif

    const auto bad_record = std::make_shared<Record>(*e->records.front());
    auto invalid = *e;
    invalid.records.front() = bad_record;
    bad_record->raw += " uid=1000";
    assert(validate_execution(invalid).error == "invalid_execution_fields");
    bad_record->raw = e->records.front()->raw + " unknown=1";
    assert(validate_execution(invalid).error == "invalid_syscall");
    bad_record->raw = e->records.front()->raw;
    bad_record->raw.replace(bad_record->raw.find("items=1"), 7, "items=2");
    assert(validate_execution(invalid).error == "incomplete_execution");
    bad_record->raw = e->records.front()->raw;
    bad_record->raw.replace(bad_record->raw.find("success=yes exit=0"), 18, "success=no exit=-2");
    const auto failure = validate_execution(invalid);
    assert(failure.execution && !failure.execution->success && failure.execution->result == -2);
    invalid.records.erase(invalid.records.begin() + 1);
    assert(validate_execution(invalid).error == "execve_missing_argc");
    assert(r.volatile_frontier() == 0);
    assert(r.acknowledge(e->token) && r.volatile_frontier() == r.next_offset());
}
void execve_validation() {
    const auto check = [](std::initializer_list<std::string_view> records, bool close = true) {
        Reconstructor r;
        for (auto fields : records) append(r, line("EXECVE", 1, fields));
        if (close) append(r, line("EOE", 1, ""));
        else assert(r.finish());
        const auto event = r.take_ready();
        assert(event);
        return validate_execve(*event);
    };
    assert(check({"argc=2 a0_len=6 a0[0]=4142", R"(a0[1]=43 a1="")"}).empty());
    assert(check({R"(argc=1 a0_len=3 a0[0]="AB")", R"(a0[1]="C")"}).empty());
    assert(check({"argc=1 a0_len=2 a0[0]=4142"}) == "execve_invalid_fragment");
    assert(check({"argc=1 a0_len=3 a0[0]=41", R"(a0[1]="B")"}) == "execve_invalid_fragment");
    assert(check({"argc=0"}).empty());
    assert(check({}) == "execve_missing_argc");
    assert(check({"argc=1"}) == "execve_incomplete");
    assert(check({"argc=1 a0_len=6 a0[0]=4142"}) == "execve_incomplete");
    assert(check({"argc=1 a0_len=1 a0[0]=4142"}) == "execve_invalid_fragment");
    assert(check({"argc=1 a0_len=1 a0[1]=41"}) == "execve_invalid_fragment");
    assert(check({"argc=2 a0=41 a0=42"}) == "execve_argument_order");
    assert(check({"argc=1 a0=4a"}) == "execve_invalid_argument");
    assert(check({"argc=1 a0=4"}) == "execve_invalid_argument");
    assert(check({"argc=1 a0=0x41"}) == "execve_invalid_argument");
    assert(check({"argc=0 argc=0"}) == "execve_unexpected_field");
    assert(check({"argc=0"}, false) == "execve_unclosed_event");
}
void plugin_input() {
    using Result = PluginInput::Result;
    PluginInput input;
    const auto event = line("EXECVE", 12, "argc=0");
    const auto native_eoe = line("EOE", 12, "");
    auto eoe = native_eoe;
    eoe.insert(eoe.size() - 1, " ");
    assert(!parse_record(eoe, 0).record);
    assert(!parse_record(native_eoe, 0, 65536, RecordProfile::auditd_string).record);
    const auto data = event + line("PROCTITLE", 12, "proctitle=00") + eoe;
    Limits limits;
    limits.profile = RecordProfile::auditd_string;
    limits.proctitle_terminal = true;
    Reconstructor reader(0, limits);
    for (const char& byte : data) {
        std::string_view chunk(&byte, 1);
        if (input.consume(chunk) == Result::record) {
            assert(reader.feed(reader.next_offset(), input.record(), 0) == FeedResult::accepted);
        }
        assert(chunk.empty());
    }
    assert(input.complete());
    const auto ready = reader.take_ready();
    assert(ready && ready->basis == Basis::eoe && validate_execve(*ready).empty());
    assert(ready->records.back()->raw == eoe.substr(0, eoe.size() - 1));

    PluginInput coalesced;
    const auto pair = event + eoe;
    std::string_view chunk(pair);
    assert(coalesced.consume(chunk) == Result::record && coalesced.record() == event);
    assert(chunk == eoe);
    assert(coalesced.consume(chunk) == Result::record && coalesced.record() == eoe);
    assert(chunk.empty());

    std::string_view partial("unfinished");
    assert(coalesced.consume(partial) == Result::partial && !coalesced.complete());
    const std::string oversized(65536, 'a');
    std::string_view too_large(oversized);
    assert(coalesced.consume(too_large) == Result::invalid && !coalesced.complete());
    std::string_view valid(eoe);
    assert(coalesced.consume(valid) == Result::invalid);

    for (std::string_view invalid : std::initializer_list<std::string_view>{"\n", "bad\r\n", std::string_view("bad\0\n", 5)}) {
        PluginInput broken;
        assert(broken.consume(invalid) == Result::invalid);
        assert(!broken.complete());
    }
}
void plugin_session() {
    auto eoe = line("EOE", 12, "");
    eoe.insert(eoe.size() - 1, " ");
    const auto data = line("EXECVE", 12, "argc=0") + eoe;
    int registered = 0;
    int finalized = 0;
    const auto admit = [&](const Record&) { return ++registered != 2; };
    const auto finalize = [&](const Event&, const ExecutionResult&) {
        ++finalized;
        return true;
    };
    PluginSession lost_registration(admit, finalize, validate_execution);
    assert(!lost_registration.consume(data, 0));
    assert(registered == 2 && finalized == 0);
    assert(!lost_registration.consume(eoe, 1));

    registered = 0;
    PluginSession lost_commit([&](const Record&) { ++registered; return true; },
        [&](const Event& event, const ExecutionResult& result) {
            assert(registered == 2 && event.eoe_seen && result.error == "incomplete_execution");
            ++finalized;
            return false;
        }, validate_execution);
    assert(!lost_commit.consume(data, 0));
    assert(finalized == 1 && !lost_commit.finish());

    PluginSession interrupted([](const Record&) { return true; }, finalize, validate_execution);
    assert(interrupted.consume(line("EXECVE", 12, "argc=0"), 0));
    assert(!interrupted.finish() && finalized == 1);

    PluginSession timed_out([](const Record&) { return true; }, finalize, validate_execution);
    assert(timed_out.consume(line("EXECVE", 12, "argc=0"), 0));
    assert(timed_out.tick(9999));
    assert(!timed_out.tick(10000) && timed_out.error() == "assembly_timeout");
    assert(!timed_out.consume(eoe, 10001) && finalized == 1);
}
void plugin_backpressure() {
    std::uint64_t now = 0;
    unsigned finalized = 0;
    PluginSession session([&](const Record&) { now += 1500; return true; },
        [&](const Event&, const ExecutionResult&) { now += 1500; ++finalized; return true; },
        validate_execution, [&] { return now; });
    assert(session.consume(line("EXECVE", 1, "argc=0"), now));
    for (unsigned i=0; i<8; ++i)
        assert(session.consume(line("PATH", 2), now));
    auto eoe = line("EOE", 2, ""); eoe.insert(eoe.size()-1, " ");
    assert(session.consume(eoe, now) && finalized == 1);
    // More than 10 s passed while durable callbacks deliberately stopped input.
    // A remains open and may still close with EOE; B's wait cannot age A out.
    assert(now > 10000 && session.tick(now));
    now += 9999;
    assert(session.tick(now));
    eoe = line("EOE", 1, ""); eoe.insert(eoe.size()-1, " ");
    assert(session.consume(eoe, now) && finalized == 2 && session.finish());

    PluginSession timeout_after_pause([&](const Record&) { now += 1500; return true; },
        [](const Event&, const ExecutionResult&) { return true; },
        validate_execution, [&] { return now; });
    assert(timeout_after_pause.consume(line("EXECVE", 3, "argc=0"), now));
    now += 10000;
    assert(!timeout_after_pause.tick(now) && timeout_after_pause.error() == "assembly_timeout");
}
void individual_timeout_and_late_suppression() {
    bool timed = false;
    unsigned finalized = 0;
    PluginSession session([&](const Record& record) -> PluginSession::Admission {
        if (timed && record.key.serial == "1") return PluginSession::Admission::suppressed;
        return true;
    }, [&](const Event& event, const ExecutionResult&) {
        assert(event.key.serial != "1" && event.eoe_seen); ++finalized; return true;
    }, validate_execution, {}, [&](const Event& event) {
        assert(event.key.serial == "1" && !event.eoe_seen && event.timeout);
        const auto& t = *event.timeout;
        assert(t.reason == "lifetime" && t.observed_active_ms == 10000 && t.paused_ms == 0);
        timed = true;
        return true;
    });
    assert(session.consume(line("EXECVE", 1, "argc=0"), 0));
    assert(session.consume(line("EXECVE", 2, "argc=0"), 9000));
    auto eoe = line("EOE", 2, ""); eoe.insert(eoe.size()-1, " ");
    assert(session.consume(eoe, 9001) && finalized == 1);
    assert(session.tick(10000) && timed);
    eoe = line("EOE", 1, ""); eoe.insert(eoe.size()-1, " ");
    assert(session.consume(eoe, 10001));
    assert(session.consume(line("EXECVE", 3, "argc=0"), 10002));
    eoe = line("EOE", 3, ""); eoe.insert(eoe.size()-1, " ");
    assert(session.consume(eoe, 10003) && finalized == 2 && session.finish());

    PluginSession uncertain([](const Record&) { return true; },
        [](const Event&, const ExecutionResult&) { return true; }, validate_execution, {},
        [](const Event&) { return false; });
    assert(uncertain.consume(line("EXECVE", 1, "argc=0"), 0));
    assert(!uncertain.tick(10000) && uncertain.error() == "finalization_unconfirmed");
    assert(!uncertain.consume(eoe, 10001));
}
void retired_payloads_and_suppressed_positions() {
    Limits limits; limits.retain_history = false;
    limits.tracked_records = 2; limits.finalized_groups = 1;
    Reconstructor r(0, limits);
    for (unsigned id=1; id<=2000; ++id) {
        append(r, line("SYSCALL", id)); append(r, line("EOE", id, ""));
        auto event = r.take_ready();
        assert(event && r.acknowledge(event->token));
        assert(event->records.size() == 2); // Delivered immutable data was not changed.
        assert(r.retained_bytes() == 0 && r.tracked_records() == 0);
    }
    const auto late = parse_record(line("EOE", 1, ""), r.next_offset());
    assert(late.record && r.skip(*late.record, 0));
    assert(r.volatile_frontier() == r.next_offset() && r.retained_bytes() == 0);
}
void resource_discard_and_live_retirement() {
    Limits limits;
    limits.retain_history = false; limits.resource_recovery = true;
    limits.group_bytes = 200; limits.total_bytes = 32768;
    limits.open_groups = 2; limits.finalized_groups = 2; limits.tracked_records = 64;
    limits.records_per_group = 64;
    unsigned incidents=0;
    Reconstructor r(0,limits,[&](const Key& key,const ResourceEvidence& e) {
        assert(key.serial == "1" && e.reason == "event_bytes" && e.event_records_before == 1);
        assert(e.incoming_for_event && e.trigger_end > e.trigger_begin);
        ++incidents;
        return true;
    });
    const auto baseline=r.retained_bytes();
    const auto large=line("PATH",1,"x="+std::string(100,'a'));
    append(r,large); assert(r.retained_bytes()>baseline);
    append(r,large); assert(incidents==1 && r.retained_bytes()==baseline && !r.take_ready());
    append(r,line("PATH",2)); append(r,line("EOE",2,""));
    auto independent=r.take_ready();
    assert(independent && !independent->resource && r.acknowledge(independent->token));
    assert(independent->records.size()==2 && r.retained_bytes()==baseline && r.volatile_frontier()==0);
    for(unsigned i=0;i<100;++i) append(r,large);
    assert(incidents==1 && r.retained_bytes()==baseline);
    append(r,line("EOE",1,"")); auto discarded=r.take_ready();
    assert(discarded && discarded->resource && discarded->records.empty() && discarded->eoe_seen);
    assert(r.acknowledge(discarded->token) && r.volatile_frontier()==r.next_offset());
    assert(r.retained_bytes()==baseline);

    Limits live;live.retain_history=false;live.tracked_records=4;live.finalized_groups=1;
    Reconstructor stable(0,live);
    append(stable,line("PATH",1)); const auto held=stable.retained_bytes();
    for(unsigned id=2;id<2002;++id) {
        append(stable,line("PATH",id));append(stable,line("EOE",id,""));
        auto event=stable.take_ready();assert(event && stable.acknowledge(event->token));
        assert(event->records.size()==2 && stable.retained_bytes()==held && stable.volatile_frontier()==0);
    }
    append(stable,line("EOE",1,""));auto first=stable.take_ready();assert(first && stable.acknowledge(first->token));
    assert(stable.volatile_frontier()==stable.next_offset() && stable.retained_bytes()==0);
}
void resource_aggregate_gate_and_metadata_exhaustion() {
    Limits limits;limits.retain_history=false;limits.resource_recovery=true;
    limits.group_bytes=15000;limits.total_bytes=32768;limits.records_per_group=64;
    limits.open_groups=2;limits.finalized_groups=2;limits.tracked_records=64;
    unsigned incidents=0;
    Reconstructor r(0,limits,[&](const Key& key,const ResourceEvidence& e) {
        assert(key.serial=="1" && e.reason=="aggregate_bytes" && !e.incoming_for_event);
        assert(e.retained_accounted_bytes<=e.aggregate_limit && e.retained_accounted_bytes+e.requested_accounted_bytes>e.aggregate_limit);
        ++incidents;return true;
    });
    const auto baseline=r.retained_bytes();
    append(r,line("PATH",1,"x="+std::string(9000,'a')));
    append(r,line("PATH",2,"x="+std::string(9000,'b')));
    append(r,line("PATH",2));assert(incidents==1 && r.retained_bytes()<limits.total_bytes);
    append(r,line("EOE",2,""));auto b=r.take_ready();assert(b && !b->resource && r.acknowledge(b->token));
    assert(r.retained_bytes()==baseline && r.volatile_frontier()==0);
    append(r,line("EOE",1,""));auto a=r.take_ready();assert(a && a->resource && r.acknowledge(a->token));
    assert(r.volatile_frontier()==r.next_offset());

    Reconstructor unconfirmed(0,limits,[](const Key&,const ResourceEvidence&) { return false; });
    append(unconfirmed,line("PATH",1,"x="+std::string(9000,'a')));
    append(unconfirmed,line("PATH",2,"x="+std::string(9000,'b')));
    const auto retained=unconfirmed.retained_bytes();
    assert(unconfirmed.feed(unconfirmed.next_offset(),line("PATH",2),0)==FeedResult::failed);
    assert(unconfirmed.error()=="resource_report_unconfirmed" && unconfirmed.retained_bytes()==retained);

    limits.tracked_records=2;
    Reconstructor bounded(0,limits,[](const Key&,const ResourceEvidence& e) { return e.reason=="aggregate_records"; });
    append(bounded,line("PATH",1));append(bounded,line("PATH",2));append(bounded,line("PATH",2));
    assert(bounded.retained_bytes()<limits.total_bytes);
    assert(bounded.feed(bounded.next_offset(),line("PATH",1),0)==FeedResult::failed);
    assert(bounded.error()=="assembly_metadata_capacity");
}
void resource_record_limit_and_timeout() {
    Limits limits;limits.retain_history=false;limits.resource_recovery=true;
    limits.group_bytes=8192;limits.total_bytes=32768;limits.open_groups=2;limits.finalized_groups=2;
    limits.tracked_records=64;limits.records_per_group=1;
    unsigned incidents=0;
    Reconstructor r(0,limits,[&](const Key&,const ResourceEvidence& e) { ++incidents;return e.reason=="event_records"; });
    append(r,line("PATH",1));append(r,line("PATH",1));assert(incidents==1);
    assert(r.expire(2000));auto expired=r.take_ready();
    assert(expired && expired->resource && expired->timeout && !expired->eoe_seen && expired->records.empty());
    assert(r.acknowledge(expired->token) && r.volatile_frontier()==r.next_offset());
}
void parsing() {
    auto p = parse_record(line("EXECVE", 1, "argc=2 a0=\"msg=audit(bogus)\""), 42);
    assert(p.record && p.record->begin == 42 && p.record->key.fraction == "123");
    assert(p.record->end == 42+p.record->raw.size()+1);
    for (auto raw : {std::string{}, std::string("type=EOE msg=audit(1.001:1):"),
                    std::string("type=SYSCALL msg=audit(1.001:1):\n"),
                    std::string("node=remote type=EOE msg=audit(1.001:1):\n"),
                    std::string("type=EOE msg=audit(1.x:1):\n"),
                    std::string("type=EOE msg=audit(1.001:01):\n"),
                    std::string("type=EOE msg=audit(18446744073709551616.001:1):\n"),
                    std::string("type=EOE msg=audit(1.1234567890:1):\n"),
                    std::string("type=EOE msg=audit(1.001:1):\r\n"),
                    std::string("type=EOE msg=audit(1.001:1):\n\n")}) assert(!parse_record(raw, 0).record);
    auto nul = line("EXECVE", 1); nul[20] = '\0'; assert(!parse_record(nul, 0).record);
    auto raw = line("EOE", 1, "");
    assert(parse_record(raw, 0, raw.size()-1).record);
    assert(!parse_record(raw, 0, raw.size()-2).record);
    assert(!parse_record(raw, std::numeric_limits<std::uint64_t>::max()).record);
    assert(parse_record(line("EXECVE", 1, R"(argc=1 a0="literal\backslash")"), 0).record);
    assert(parse_record(line("EXECVE", 1, R"(argc=1 a0="")"), 0).record);
    for (const auto* malformed : {"argc=1  a0=value", "argc=1 ", "argc=1\ta0=value",
                                  "argc=", "=1", "argc=1 stray", "a0=\"unterminated",
                                  "a0=\"contains spaces\"", "a0=\"quoted\"suffix"}) {
        assert(parse_record(line("EXECVE", 1, malformed), 0).error == "invalid_payload_syntax");
    }
    // Lexical acceptance leaves field-specific semantics to the next stage.
    assert(parse_record(line("SYSCALL", 1, "pid=not-an-integer"), 0).record);
}
void eoe_payload_validation() {
    const auto valid = line("EOE", 7, "");
    const auto parsed = parse_record(valid, 0);
    assert(parsed.record && parsed.record->type == "EOE");

    for (const auto& invalid : {line("EOE", 7), line("EOE", 7, " "),
                                line("EOE", 7, "res=1"), line("EOE", 7, "\t")}) {
        const auto result = parse_record(invalid, 0);
        assert(!result.record && result.error == "unexpected_eoe_payload");
    }

    // A malformed EOE must fail closed rather than finalizing the open event.
    Reconstructor r;
    append(r, line("SYSCALL", 7));
    const auto bad_terminator = line("EOE", 7, "res=1");
    assert(r.feed(r.next_offset(), bad_terminator, 0) == FeedResult::failed);
    assert(r.error() == "unexpected_eoe_payload");
    assert(!r.take_ready());
    assert(r.volatile_frontier() == 0);
}
void frontier() {
    Reconstructor r(100);
    append(r, line("SYSCALL", 1));
    const auto after_a = r.next_offset();
    append(r, line("SYSCALL", 2)); append(r, line("EOE", 2, ""));
    auto b = r.take_ready(); assert(b && b->key.serial == "2");
    assert(r.acknowledge(b->token)); assert(r.volatile_frontier() == 100);
    append(r, line("EOE", 1, "")); auto a = r.take_ready();
    assert(a && a->key.serial == "1"); assert(r.acknowledge(a->token));
    assert(r.volatile_frontier() > after_a && r.volatile_frontier() == r.next_offset());
    assert(r.acknowledge(a->token)); assert(!r.acknowledge(999));
}
void partial_frontier() {
    Reconstructor r;
    append(r, line("SYSCALL", 1));
    append(r, line("SYSCALL", 2)); append(r, line("EOE", 1, ""));
    auto a = r.take_ready(); assert(a && r.acknowledge(a->token));
    assert(r.volatile_frontier() == 0); // Do not split A around unresolved B.
    assert(r.expire(2000)); auto b = r.take_ready(); assert(b && b->basis == Basis::timeout);
    assert(!b->terminal_seen); assert(r.acknowledge(b->token));
    assert(r.volatile_frontier() == r.next_offset());
}
void duplicates_and_late() {
    Reconstructor r; const auto raw = line("PATH", 1);
    append(r, raw);
    assert(r.feed(0, raw, 0) == FeedResult::duplicate);
    assert(r.tracked_records() == 1);
    append(r, raw); append(r, line("SYSCALL", 1)); append(r, line("EOE", 1, ""));
    auto e = r.take_ready(); assert(e && e->records.size() == 4 && e->path_records == 2);
    assert(e->duplicate_content_records == 1); // Equal content at new positions preserved.
    assert(r.acknowledge(e->token)); const auto saved = r.volatile_frontier();
    assert(r.feed(r.next_offset(), line("EXECVE", 1), 0) == FeedResult::failed);
    assert(r.error() == "late_record" && r.volatile_frontier() == saved);
    assert(!r.acknowledge(e->token)); // Sticky failure cannot advance any frontier.
    Reconstructor conflict; append(conflict, raw);
    assert(conflict.feed(0, line("CWD", 1), 0) == FeedResult::failed);
    assert(conflict.error() == "conflicting_replay" && conflict.volatile_frontier() == 0);
}
void ordering_and_missing() {
    Reconstructor r;
    append(r, line("PATH", 9)); append(r, line("EXECVE", 9));
    append(r, line("CWD", 9)); append(r, line("PATH", 9, "item=1"));
    append(r, line("SYSCALL", 9)); append(r, line("EOE", 9, ""));
    auto e = r.take_ready(); assert(e && e->syscall_seen && e->records[0]->type == "PATH");
    assert(e->path_records == 2 && !e->proctitle_seen);
    Reconstructor missing; append(missing, line("EXECVE", 3)); assert(missing.finish());
    e = missing.take_ready(); assert(e && !e->syscall_seen && !e->terminal_seen);
    assert(e->basis == Basis::shutdown); assert(missing.finish());
    assert(missing.feed(missing.next_offset(), line("EOE", 3, ""), 0) == FeedResult::failed);
}
void timeout() {
    Reconstructor r;
    append(r, line("SYSCALL", 20), 0); append(r, line("SYSCALL", 10), 10);
    assert(r.expire(1999)); assert(!r.take_ready());
    assert(r.expire(2010)); auto first = r.take_ready(), second = r.take_ready();
    assert(first && second && first->key.serial == "20" && second->key.serial == "10");
    assert(first->basis == Basis::timeout && !first->terminal_seen);
    assert(r.volatile_frontier() == 0); // Expiry never acknowledges automatically.
    Reconstructor duplicate;
    const auto raw = line("SYSCALL", 1); append(duplicate, raw, 0);
    assert(duplicate.feed(0, raw, 1900) == FeedResult::duplicate);
    assert(duplicate.expire(2000) && duplicate.take_ready()); // Retry does not renew deadline.
    Reconstructor clock; append(clock, raw, 10);
    assert(!clock.expire(9) && clock.error() == "monotonic_clock_reversed");
}
void independent_paused_deadlines() {
    Limits limits; limits.timeout_ms = 100; limits.inactivity_timeout_ms = 40;
    Reconstructor r(0, limits);
    append(r, line("SYSCALL", 1), 0);
    append(r, line("SYSCALL", 2), 20);
    append(r, line("PATH", 1), 30);
    assert(r.expire(59) && !r.take_ready());
    assert(r.expire(60));
    auto inactive = r.take_ready();
    assert(inactive && inactive->key.serial == "2" && inactive->basis == Basis::timeout);
    append(r, line("PATH", 1), 69);
    assert(r.expire(99) && !r.take_ready());
    assert(r.expire(100));
    auto lifetime = r.take_ready();
    assert(lifetime && lifetime->key.serial == "1" && lifetime->basis == Basis::timeout);
    assert(r.volatile_frontier() == 0);

    Reconstructor nested(0, limits);
    append(nested, line("SYSCALL", 1), 0);
    assert(nested.pause(10) && nested.pause(20));
    assert(nested.expire(1000) && !nested.take_ready());
    assert(nested.resume(1100));
    assert(nested.expire(2000) && !nested.take_ready());
    assert(nested.resume(2100));
    assert(nested.expire(2129) && !nested.take_ready());
    assert(nested.expire(2130) && nested.take_ready());
    limits.inactivity_timeout_ms = 200;
    Reconstructor paused_lifetime(0, limits);
    append(paused_lifetime, line("SYSCALL", 1), 0);
    assert(paused_lifetime.pause(10) && paused_lifetime.resume(1000));
    append(paused_lifetime, line("PATH", 1), 1050);
    assert(paused_lifetime.expire(1089) && !paused_lifetime.take_ready());
    assert(paused_lifetime.expire(1090) && paused_lifetime.take_ready());
    Reconstructor unbalanced;
    assert(!unbalanced.resume(0) && unbalanced.error() == "pause_not_active");
    Reconstructor reading;
    assert(reading.pause(0));
    assert(reading.feed(0, line("SYSCALL", 1), 1) == FeedResult::failed);
    assert(reading.error() == "input_while_paused");
}
void proctitle() {
    Reconstructor normal; append(normal, line("PROCTITLE", 1)); assert(!normal.take_ready());
    Limits limits; limits.proctitle_terminal = true;
    Reconstructor opted(0, limits); append(opted, line("SYSCALL", 1)); append(opted, line("PROCTITLE", 1));
    auto e = opted.take_ready(); assert(e && e->basis == Basis::proctitle_terminal);
    assert(e->terminal_seen && !e->eoe_seen);
}
void capacities() {
    auto check = [](Limits limits, const std::vector<std::string>& input, std::string_view error) {
        Reconstructor r(0, limits); bool failed = false;
        for (const auto& raw : input) {
            if (r.feed(r.next_offset(), raw, 0) == FeedResult::failed) { failed = true; break; }
        }
        assert(failed && r.error() == error);
        assert(r.retained_bytes() <= limits.total_bytes && r.volatile_frontier() == 0);
        assert(!r.finish());
    };
    Limits l; l.record_bytes = 5; check(l, {line("EOE",1,"")}, "record_capacity");
    l = {}; l.group_bytes = 1; check(l, {line("SYSCALL",1)}, "group_capacity");
    l = {}; l.records_per_group = 1; check(l, {line("SYSCALL",1),line("PATH",1)}, "group_capacity");
    l = {}; l.open_groups = 1; check(l, {line("SYSCALL",1),line("SYSCALL",2)}, "open_group_capacity");
    l = {}; l.total_bytes = 1024; check(l, {line("SYSCALL",1)}, "assembly_capacity");
    l = {}; l.tracked_records = 1; check(l, {line("SYSCALL",1),line("PATH",1)}, "assembly_capacity");
    l = {}; l.finalized_groups = 1; check(l, {line("EOE",1,""),line("EOE",2,"")}, "finalized_history_capacity");
    bool threw = false; l = {}; l.timeout_ms = 0;
    try { Reconstructor invalid(0,l); } catch (const std::invalid_argument&) { threw = true; }
    assert(threw);
    Reconstructor gap; assert(gap.feed(5,line("EOE",1,""),0) == FeedResult::failed);
    assert(gap.error() == "noncontiguous_input");
    Reconstructor malformed;
    assert(malformed.feed(0,"garbage\n",0) == FeedResult::failed);
    assert(malformed.volatile_frontier() == 0);
}
void recovery() {
    const std::vector<std::string> bytes{line("SYSCALL",1),line("SYSCALL",2),
        line("EOE",2,""),line("EOE",1,"")};
    Reconstructor original;
    for (std::size_t i=0;i<3;++i) append(original,bytes[i]);
    auto b = original.take_ready(); assert(b && original.acknowledge(b->token));
    assert(original.volatile_frontier() == 0);
    // Caller replays from its last safe boundary. The previously committed B
    // must be deduplicated externally; this component never claims persistence.
    Reconstructor restarted(original.volatile_frontier());
    for (const auto& raw : bytes) append(restarted,raw);
    auto replay_b = restarted.take_ready(), a = restarted.take_ready();
    assert(replay_b && a && replay_b->key == b->key);
    assert(replay_b->records.size() == b->records.size());
    for (std::size_t i=0;i<b->records.size();++i) assert(replay_b->records[i]->raw == b->records[i]->raw);
    assert(restarted.acknowledge(replay_b->token) && restarted.volatile_frontier() == 0);
    assert(restarted.acknowledge(a->token) && restarted.volatile_frontier() == restarted.next_offset());
    // A timeout can produce different reconstruction from the same bytes after
    // restart. Make the unresolved durability problem visible, not a fake pass.
    Reconstructor timed; append(timed,bytes[0]); assert(timed.expire(2000));
    auto partial = timed.take_ready(); assert(partial && partial->basis == Basis::timeout);
    Reconstructor replay; append(replay,bytes[0]); append(replay,bytes[3]);
    auto complete = replay.take_ready(); assert(complete && complete->basis == Basis::eoe);
    assert(complete->records.size() != partial->records.size());
}
void crossing_frontier_and_fail_closed() {
    Reconstructor r;
    append(r, line("SYSCALL", 1)); append(r, line("SYSCALL", 2));
    append(r, line("EOE", 1, "")); append(r, line("SYSCALL", 3));
    append(r, line("EOE", 2, "")); append(r, line("EOE", 3, ""));
    auto a = r.take_ready(), b = r.take_ready(), c = r.take_ready();
    assert(a && b && c && r.acknowledge(c->token));
    assert(r.volatile_frontier() == 0);
    assert(r.acknowledge(a->token) && r.volatile_frontier() == 0);
    assert(r.acknowledge(b->token) && r.volatile_frontier() == r.next_offset());
    const auto committed = r.volatile_frontier();
    append(r, line("EXECVE", 4));
    assert(r.volatile_frontier() == committed && !r.acknowledge(4));
    assert(r.feed(r.next_offset(), "type=broken\n", 0) == FeedResult::failed);
    assert(r.volatile_frontier() == committed);
    assert(r.feed(r.next_offset(), line("EOE", 4, ""), 0) == FeedResult::failed);
    Reconstructor reversed;
    append(reversed, line("SYSCALL", 1)); append(reversed, line("EOE", 1, ""));
    auto done = reversed.take_ready(); assert(done && reversed.acknowledge(done->token));
    const auto boundary = reversed.volatile_frontier();
    // EOF/EOE is terminal for this epoch: later native records cannot silently
    // reopen the group, even if they would have filled a missing field.
    assert(reversed.feed(reversed.next_offset(), line("PATH", 1), 0) == FeedResult::failed);
    assert(reversed.volatile_frontier() == boundary);
}
void determinism() {
    auto run = [] {
        Reconstructor r; std::string result;
        for (unsigned id : {3,1,2}) append(r,line("PATH",id));
        assert(r.finish());
        while (auto e = r.take_ready()) {
            result += e->key.serial+":"+std::to_string(e->token)+";";
            assert(r.acknowledge(e->token));
        }
        assert(r.volatile_frontier() == r.next_offset());
        return result;
    };
    assert(run() == "3:1;1:2;2:3;" && run() == run());
}
}
int main() {
    resource_discard_and_live_retirement(); resource_aggregate_gate_and_metadata_exhaustion(); resource_record_limit_and_timeout();
    observation_clocks(); current_tail(); fixture(); execve_validation(); plugin_input(); plugin_session(); plugin_backpressure(); individual_timeout_and_late_suppression(); retired_payloads_and_suppressed_positions(); parsing(); eoe_payload_validation(); frontier(); partial_frontier(); duplicates_and_late();
    ordering_and_missing(); timeout(); independent_paused_deadlines(); proctitle(); capacities(); recovery(); crossing_frontier_and_fail_closed(); determinism();
    std::cout << "PASS: 25 offline Audit reconstruction, per-event timeouts, paused deadlines, current-tail, plugin framing, and validation test groups\n";
}
