#pragma once

#include "hids/audit/reconstruction.hpp"

namespace hids::audit {
// Internal fixture contract. Native time is copied verbatim from reconstruction.
struct Execution {
    Key key;
    std::uint32_t syscall, pid, ppid, uid, euid, suid, fsuid;
    std::optional<std::uint32_t> auid, session;
    std::int64_t result;
    bool success;
    std::string exe_base64, comm_base64;
    std::size_t path_count = 0;
    bool cwd_present = false, proctitle_present = false;
};

struct ExecutionResult {
    std::optional<Execution> execution;
    std::string_view error;
};

ExecutionResult validate_execution(const Event& event);
}
