#pragma once
#include "hids/process/stream.hpp"
namespace hids::processlive {
// Root activation is verified by the executable before it calls this function.
int run(process::ConnectorIo&,Stream&,Queue&,const Json& source,const std::string& producer,
 const std::function<bool()>& cancelled,const std::function<void()>& started={},
 const std::function<bool()>& completed={});
bool role_credentials();
Json read_config(const std::string& path);
void verify_grant(int fd,const Json& source);
bool grant_closed(int fd)noexcept;
}
