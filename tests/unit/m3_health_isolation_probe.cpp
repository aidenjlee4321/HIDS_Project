// Test-only binary: exercises the production syscall filter under its unit policy.
#define main hids_health_production_main
#include "../../collector/src/health/main.cpp"
#undef main
#include <fstream>
#include <iostream>
int main() {
#ifdef __linux__
    if (::getuid() != 0 || !secure()) return 1;
    Json result;
    for (const char* path : {"/run/hids/m3/control.sock", "/run/hids/m3/ingest/audit.sock", "/run/systemd/private", "/run/dbus/system_bus_socket"}) {
        struct stat info{};
        result[path] = ::lstat(path, &info) < 0;
    }
    Fd database(::open("/var/lib/hids/m3/control.sqlite", O_RDONLY|O_CLOEXEC));
    result["event_state_inaccessible"] = database.value < 0;
    Fd network(::socket(AF_INET, SOCK_STREAM|SOCK_CLOEXEC, 0));
    result["internet_socket_denied"] = network.value < 0;
    Fd file(::open("/usr/lib/hids/health-isolation-write-test", O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC, 0600));
    result["host_write_denied"] = file.value < 0;
    errno=0;
    result["signals_denied"] = ::syscall(__NR_kill, ::getpid(), 0) == -1 && errno == EPERM;
    std::ifstream status("/proc/self/status");
    std::string line;
    while (std::getline(status, line)) {
        for (const auto* key : {"CapEff:", "CapPrm:", "CapBnd:", "CapAmb:", "NoNewPrivs:"})
            if (line.starts_with(key)) result[key] = line.substr(std::strlen(key));
    }
    char name[]="true";
    char* args[]{name, nullptr};
    errno=0;
    result["exec_denied"] = ::syscall(__NR_execve, "/usr/bin/true", args, nullptr) == -1 && errno == EPERM;
    std::cout << result.dump() << '\n';
    return 0;
#else
    return 1;
#endif
}
