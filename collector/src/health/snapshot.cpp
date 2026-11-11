#include "hids/health/snapshot.hpp"
#include <array>
#include <cerrno>
#include <charconv>
#include <chrono>
#include <fcntl.h>
#include <map>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
namespace hids::health {
namespace {
struct Fd {
    int value;
    explicit Fd(int v) : value(v) {}
    ~Fd() { if (value >= 0) ::close(value); }
    Fd(const Fd&) = delete;
};
Json unavailable(int error) { return {{"state", error == ENOENT ? "missing" : error == EACCES ? "inaccessible" : "invalid"}}; }
bool trusted(const struct stat& info, bool directory) {
    return info.st_uid == 0 && !(info.st_mode & 0022) &&
        (directory ? S_ISDIR(info.st_mode) : S_ISREG(info.st_mode) && info.st_nlink == 1 && info.st_size >= 0 && info.st_size <= 65536);
}
std::uint64_t mtime(const struct stat& info) {
#ifdef __APPLE__
    const auto t = info.st_mtimespec;
#else
    const auto t = info.st_mtim;
#endif
    if (t.tv_sec < 0 || t.tv_sec > 9000000000LL) return 0;
    return static_cast<std::uint64_t>(t.tv_sec)*1000000000ULL + t.tv_nsec;
}
}
Json parse_dispatcher(std::string_view data, std::uint64_t stamp, std::uint64_t now) {
    if (!stamp || stamp > now) return {{"state", "clock_uncertain"}};
    if (data.size() > 65536 || data.find('\0') != data.npos) return {{"state", "invalid"}};
    const std::map<std::string_view, std::string_view> names{
        {"Number of active plugins", "active_plugins"}, {"current plugin queue depth", "queue_depth"},
        {"plugin queue size", "queue_capacity"}, {"plugin queue overflow detected", "overflow"},
        {"plugin queueing suspended", "suspended"}};
    Json result = {{"state", now-stamp <= fresh_ns ? "observed" : "stale"},
                   {"age_ns", now-stamp}, {"report_mtime_ns", stamp}};
    while (!data.empty()) {
        const auto end = data.find('\n');
        const auto line = data.substr(0, end);
        data = end == data.npos ? std::string_view{} : data.substr(end+1);
        const auto delimiter = line.find(" = ");
        if (delimiter == line.npos) continue;
        const auto name = names.find(line.substr(0, delimiter));
        if (name == names.end()) continue;
        const auto key = std::string(name->second);
        if (result.contains(key)) return {{"state", "invalid"}};
        const auto value = line.substr(delimiter+3);
        if (key == "overflow" || key == "suspended") {
            if (value != "yes" && value != "no") return {{"state", "invalid"}};
            result[key] = value == "yes";
        } else {
            std::uint64_t count = 0;
            const auto [p, error] = std::from_chars(value.data(), value.data()+value.size(), count);
            if (error != std::errc{} || p != value.data()+value.size() || value.empty() || count > 9223372036854775807ULL)
                return {{"state", "invalid"}};
            result[key] = count;
        }
    }
    if (result.size() != 8 || result["queue_depth"].get<std::uint64_t>() > result["queue_capacity"].get<std::uint64_t>())
        return {{"state", "invalid"}};
    return result;
}
Json read_dispatcher(const char* path) {
    std::string remaining(path);
    if (remaining.empty() || remaining[0] != '/') return {{"state", "invalid"}};
    Fd directory(::open("/", O_RDONLY|O_DIRECTORY|O_CLOEXEC));
    if (directory.value < 0) return unavailable(errno);
    std::size_t begin = 1;
    while (true) {
        const auto slash = remaining.find('/', begin);
        if (slash == remaining.npos) break;
        const auto component = remaining.substr(begin, slash-begin);
        if (component.empty() || component == "." || component == "..") return {{"state", "invalid"}};
        Fd next(::openat(directory.value, component.c_str(), O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC));
        if (next.value < 0) return unavailable(errno);
        struct stat info{};
        if (::fstat(next.value, &info) || !trusted(info, true)) return {{"state", "invalid"}};
        ::close(directory.value); directory.value = next.value; next.value = -1;
        begin = slash+1;
    }
    const auto name = remaining.substr(begin);
    if (name.empty() || name == "." || name == "..") return {{"state", "invalid"}};
    Fd file(::openat(directory.value, name.c_str(), O_RDONLY|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK));
    if (file.value < 0) return unavailable(errno);
    struct stat before{}, after{};
    if (::fstat(file.value, &before) || !trusted(before, false)) return {{"state", "invalid"}};
    std::string data;
    std::array<char, 4096> bytes{};
    while (true) {
        const auto count = ::read(file.value, bytes.data(), bytes.size());
        if (count < 0 && errno == EINTR) continue;
        if (count < 0) return {{"state", "invalid"}};
        if (count == 0) break;
        data.append(bytes.data(), static_cast<std::size_t>(count));
        if (data.size() > 65536) return {{"state", "invalid"}};
    }
    if (::fstat(file.value, &after) || !trusted(after, false) || before.st_dev != after.st_dev ||
        before.st_ino != after.st_ino || before.st_size != after.st_size || mtime(before) != mtime(after) ||
        data.size() != static_cast<std::size_t>(after.st_size)) return {{"state", "invalid"}};
    const auto now = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
    return parse_dispatcher(data, mtime(after), now < 0 ? 0 : static_cast<std::uint64_t>(now));
}
}
