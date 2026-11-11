#pragma once

#include <cstddef>
#include <functional>

namespace hids::audit {
// Called only after root authorization. Establish a stream-local current-tail
// boundary without retaining native bytes. EOF or exhaustion cannot prove one.
bool discard_queued_input(int descriptor, std::size_t maximum,
                          const std::function<bool()>& cancelled);
}
