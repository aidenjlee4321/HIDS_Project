#include "hids/health/snapshot.hpp"
#include <cassert>
#include <iostream>
#include <string>
namespace {
const std::string report = "Number of active plugins = 1\ncurrent plugin queue depth = 3\nplugin queue size = 2000\nplugin queue overflow detected = no\nplugin queueing suspended = no\n";
}
int main() {
    using hids::health::parse_dispatcher;
    const auto snapshot = parse_dispatcher(report, 100, 200);
    assert(snapshot["state"] == "observed" && snapshot["queue_depth"] == 3 && snapshot["overflow"] == false);
    assert(parse_dispatcher(report, 100, 15000000101ULL)["state"] == "stale");
    assert(parse_dispatcher(report, 201, 200)["state"] == "clock_uncertain");
    assert(parse_dispatcher(report, 0, 200)["state"] == "clock_uncertain");
    assert(parse_dispatcher(report+"plugin queue size = 4\n",100,200)["state"] == "invalid");
    for (const auto& invalid : {std::string{}, std::string(65537, 'x'), report+std::string(1,'\0'),
                               std::string("Number of active plugins = 1\n")})
        assert(parse_dispatcher(invalid,100,200)["state"] == "invalid");
    auto malformed=report;
    malformed.replace(malformed.find("2000"),4,"2");
    assert(parse_dispatcher(malformed,100,200)["state"] == "invalid");
    malformed=report;
    malformed.replace(malformed.find("no"),2,"maybe");
    assert(parse_dispatcher(malformed,100,200)["state"] == "invalid");
    malformed=report;
    malformed.replace(malformed.find("= 3"),3,"= -1");
    assert(parse_dispatcher(malformed,100,200)["state"] == "invalid");
    assert(hids::health::read_dispatcher("/tmp/never-trusted-health")["state"] != "observed");
    std::cout << "PASS: bounded Audit metadata parsing, duplicates, freshness and trust rejection\n";
}
