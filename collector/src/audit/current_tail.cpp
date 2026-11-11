#include "hids/audit/current_tail.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <fcntl.h>
#include <limits>
#include <unistd.h>

namespace hids::audit {
bool discard_queued_input(int descriptor, std::size_t maximum,
                          const std::function<bool()>& cancelled) {
    if (!maximum || maximum == std::numeric_limits<std::size_t>::max()) return false;
    const int flags = ::fcntl(descriptor, F_GETFL);
    if (flags < 0 || ::fcntl(descriptor, F_SETFL, flags | O_NONBLOCK) < 0) return false;
    std::array<char, 4096> bytes{};
    std::size_t discarded = 0;
    bool boundary = false;
    while (!cancelled()) {
        // At the budget, one extra byte distinguishes a full queue from EAGAIN.
        // An over-budget read ends the stream without accepting source records.
        const auto count = ::read(descriptor, bytes.data(),
                                  std::min(bytes.size(), maximum - discarded + 1));
        if (count > 0) {
            if (static_cast<std::size_t>(count) > maximum - discarded) break;
            discarded += static_cast<std::size_t>(count);
        } else if (count < 0 && errno == EINTR) {
            continue;
        } else {
            boundary = count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK);
            break;
        }
    }
    return ::fcntl(descriptor, F_SETFL, flags) == 0 && boundary;
}
}
