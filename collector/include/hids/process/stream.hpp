#pragma once
#include "hids/process/pipeline.hpp"
#include <functional>
namespace hids::processlive {
// A single connection. Never reconnects or prints native/security payloads.
class Stream {
public:
 Stream(std::string path,unsigned peer_uid,const std::function<bool()>& stop);
 ~Stream();
 Json exchange(const Json&);
 void close()noexcept;
 void finishing(){stopped_=[](){return false;};}
private:
 int fd_=-1;
 std::function<bool()> stopped_;
 void ready(bool writing,const std::chrono::steady_clock::time_point&);
};
}
