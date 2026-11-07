#include "../integration/m1_native_fixture.hpp"
#include <cassert>
#include <fstream>
#include <iostream>

int main(int argc,char** argv) {
    using namespace hids::pilot;
    assert(argc==2);
    std::ifstream in(argv[1]);std::string text(event_limit+1,'\0');
    in.read(text.data(),text.size());text.resize(static_cast<std::size_t>(in.gcount()));
    auto input=parse(text,event_limit,true);
    auto native=decode_fixture(input);
    assert(native.kind==hids::process::Lifecycle::executed && !native.parent);
    assert(native.tid==4242 && native.tgid==4242 && native.cpu==3 && native.sequence==2);
    assert(native.kernel_monotonic_ns==12345678901234567ULL);
    const auto event=normalize(native,"2026-11-07T20:00:00.000000Z",
        "15729e8d-54b8-4cd0-a74f-09e7492ad870","84990d10-90c8-4ed5-a96a-9dbaebf3cfba");
    assert(event["native"]==input && event["timestamps"]["activity_wall_time"].is_null());
    input["pid"]=7;input["tgid"]=8;input["cpu"]=4294967295U;
    input["connector_sequence"]=0;input["timestamp_ns"]="18446744073709551615";
    native=decode_fixture(input);
    assert(native.tid==7 && native.tgid==8 && native.cpu==4294967295U && native.sequence==0);
    assert(native.kernel_monotonic_ns==18446744073709551615ULL);
    input["parent"]=Json::object();bool failed=false;
    try {decode_fixture(input);} catch (const Invalid&) {failed=true;}
    assert(failed);
    std::cout<<"PASS: synthetic UAPI EXEC -> existing native parser -> independent normalization (no socket)\n";
}
