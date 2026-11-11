#pragma once

#include "hids/audit/execution.hpp"

namespace hids::audit {
// Linux adapter. Links against libauparse and uses one BUFFER per event.
ExecutionResult validate_auparse_execution(const Event& event);
}
