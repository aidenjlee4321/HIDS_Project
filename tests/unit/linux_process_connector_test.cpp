// Compile the actual OS backend with syscall test doubles. No AF_NETLINK socket
// is opened; owned placeholder file descriptors exercise real close behavior.
#include "hids/linux_process_connector.hpp"
#include <linux/connector.h>
#include <linux/netlink.h>
#include <sys/socket.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <atomic>
#include <algorithm>
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstring>

int fake_socket(int,int,int);
int fake_bind(int,const sockaddr*,socklen_t);
int fake_getsockname(int,sockaddr*,socklen_t*);
ssize_t fake_sendto(int,const void*,size_t,int,const sockaddr*,socklen_t);
int fake_poll(pollfd*,nfds_t,int);
ssize_t fake_recvmsg(int,msghdr*,int);
#define socket fake_socket
#define bind fake_bind
#define getsockname fake_getsockname
#define sendto fake_sendto
#define poll fake_poll
#define recvmsg fake_recvmsg
#include "../../collector/src/linux_process_connector.cpp"
#undef socket
#undef bind
#undef getsockname
#undef sendto
#undef poll
#undef recvmsg

using namespace hids::process;
int socket_error=0,bind_error=0,address_error=0,send_error=0;
int last_fd=-1,socket_calls=0,send_calls=0,recv_calls=0,poll_result=1,poll_error=0,recv_error=0;
int receive_flags=0; short poll_events=POLLIN;
bool bad_port=false,foreign=false,short_send=false,empty_receive=false,huge_receive=false;
int fake_socket(int domain,int type,int protocol) {
    ++socket_calls;
    assert(domain==AF_NETLINK && type==(SOCK_DGRAM | SOCK_CLOEXEC) && protocol==NETLINK_CONNECTOR);
    if (socket_error) {errno=socket_error;return -1;}
    // The double creates an actual CLOEXEC descriptor atomically, without a
    // socket. The assertion above checks the production socket's creation flags.
    last_fd=::fcntl(STDIN_FILENO,F_DUPFD_CLOEXEC,0);return last_fd;
}
int fake_bind(int,const sockaddr* address,socklen_t len) {
    const auto* n=reinterpret_cast<const sockaddr_nl*>(address);
    assert(len==sizeof(*n) && n->nl_groups==(1U<<(CN_IDX_PROC-1)) && n->nl_pid==0);
    if (bind_error) {errno=bind_error;return -1;} return 0;
}
int fake_getsockname(int,sockaddr* address,socklen_t* len) {
    if (address_error) {errno=address_error;return -1;}
    auto* n=reinterpret_cast<sockaddr_nl*>(address);
    n->nl_pid=bad_port?0:42;*len=sizeof(*n);return 0;
}
ssize_t fake_sendto(int,const void*,size_t size,int flags,const sockaddr* address,socklen_t len) {
    ++send_calls; const auto* n=reinterpret_cast<const sockaddr_nl*>(address);
    assert(flags==MSG_DONTWAIT && len==sizeof(*n) && n->nl_pid==0 && n->nl_groups==0);
    if(send_error){errno=send_error;return -1;}
    return static_cast<ssize_t>(size)-(short_send?1:0);
}
int fake_poll(pollfd* p,nfds_t count,int timeout) {
    assert(count==1 && timeout>=0 && timeout<=100);p->revents=poll_events;
    if (poll_result < 0) errno = poll_error;
    return poll_result;
}
ssize_t fake_recvmsg(int,msghdr* msg,int flags) {
    ++recv_calls; assert(flags==MSG_DONTWAIT);
    if(recv_error){errno=recv_error;return -1;}
    auto* n=static_cast<sockaddr_nl*>(msg->msg_name);
    n->nl_family=AF_NETLINK;n->nl_pid=foreign?999:0;
    msg->msg_namelen=sizeof(*n);msg->msg_flags=receive_flags;
    if(empty_receive)return 0;
    if(huge_receive)return static_cast<ssize_t>(msg->msg_iov->iov_len)+1;
    std::memset(msg->msg_iov->iov_base,0,8);return 8;
}
int main() {
    for(int stage=0;stage<4;++stage){
        socket_error=stage==0?EPROTONOSUPPORT:0;
        bind_error=stage==1?EACCES:0;
        address_error=stage==2?EIO:0;
        bad_port=stage==3;
        LinuxConnectorIo io;assert(io.open().error!=0);
        if(stage!=0)assert(::fcntl(last_fd,F_GETFD)==-1 && errno==EBADF);
    }
    socket_error=EINVAL;bind_error=address_error=0;bad_port=false;
    const int attempted=socket_calls;
    { LinuxConnectorIo rejected; assert(rejected.open().error==EINVAL); }
    assert(socket_calls==attempted+1); // No non-CLOEXEC fallback on flag rejection.
    socket_error=0;
    LinuxConnectorIo a,b;assert(a.open().error==0 && b.open().error==EBUSY);
    const int descriptor_flags=::fcntl(last_fd,F_GETFD);
    assert(descriptor_flags>=0 && (descriptor_flags&FD_CLOEXEC));
    const auto request=control_packet(true,42,123);
    assert(a.send(request)==0);const int count=send_calls;
    send_error=EINTR;assert(a.send(request)==EINTR && send_calls==count+1);send_error=0;
    short_send=true;assert(a.send(request)==EIO);short_send=false;
    assert(a.send(std::span<const std::byte>{request.data(),3})==EINVAL);
    std::array<std::byte,32> bytes{};
    assert(a.receive(bytes,std::chrono::milliseconds{10000}).kind==ReadKind::data);
    poll_result=0;const int before=recv_calls;
    assert(a.receive(bytes,std::chrono::milliseconds{0}).kind==ReadKind::timeout && recv_calls==before);
    poll_result=-1;poll_error=EINTR;
    assert(a.receive(bytes,std::chrono::milliseconds{0}).kind==ReadKind::interrupted);
    poll_result=1;poll_events=POLLHUP;
    assert(a.receive(bytes,std::chrono::milliseconds{0}).kind==ReadKind::closed);poll_events=POLLIN;
    for(const auto& [error,kind] : {
        std::pair{ENOBUFS,ReadKind::no_buffer},std::pair{EINTR,ReadKind::interrupted},
        std::pair{EAGAIN,ReadKind::timeout},std::pair{EACCES,ReadKind::error}}){
        recv_error=error;assert(a.receive(bytes,std::chrono::milliseconds{0}).kind==kind);
    }
    recv_error=0;
    // POLLERR is readiness for a socket error, not an automatic terminal state.
    for (short events : {static_cast<short>(POLLERR), static_cast<short>(POLLIN | POLLERR)}) {
        poll_events=events;
        const int calls=recv_calls;
        auto readable=a.receive(bytes,std::chrono::milliseconds{0});
        assert(readable.kind==ReadKind::data && readable.size==8 && recv_calls==calls+1);
        recv_error=ENOBUFS;
        auto loss=a.receive(bytes,std::chrono::milliseconds{0});
        assert(loss.kind==ReadKind::no_buffer && loss.error==ENOBUFS);
        // The pending error did not dequeue/lose the next readable message.
        recv_error=0;poll_events=POLLIN;
        assert(a.receive(bytes,std::chrono::milliseconds{0}).kind==ReadKind::data);
        poll_events=events;recv_error=EACCES;
        auto terminal=a.receive(bytes,std::chrono::milliseconds{0});
        assert(terminal.kind==ReadKind::error && terminal.error==EACCES);
        recv_error=EINTR;
        assert(a.receive(bytes,std::chrono::milliseconds{0}).kind==ReadKind::interrupted);
        recv_error=EAGAIN;
        assert(a.receive(bytes,std::chrono::milliseconds{0}).kind==ReadKind::timeout);
        recv_error=0;
    }
    poll_events=POLLNVAL;
    auto invalid=a.receive(bytes,std::chrono::milliseconds{0});
    assert(invalid.kind==ReadKind::error && invalid.error==EBADF);
    poll_events=POLLOUT;const int irrelevant=recv_calls;
    assert(a.receive(bytes,std::chrono::milliseconds{0}).kind==ReadKind::timeout && recv_calls==irrelevant);
    poll_events=POLLIN;
    for(int flags : {MSG_TRUNC,MSG_CTRUNC}){
        receive_flags=flags;assert(a.receive(bytes,std::chrono::milliseconds{0}).kind==ReadKind::truncated);
    }
    receive_flags=0;foreign=true;
    assert(a.receive(bytes,std::chrono::milliseconds{0}).kind==ReadKind::foreign_sender);foreign=false;
    empty_receive=true;assert(a.receive(bytes,std::chrono::milliseconds{0}).kind==ReadKind::error);empty_receive=false;
    huge_receive=true;assert(a.receive(bytes,std::chrono::milliseconds{0}).kind==ReadKind::error);huge_receive=false;
    const int fd=last_fd;assert(a.close()==0 && a.close()==0);
    assert(::fcntl(fd,F_GETFD)==-1 && errno==EBADF);
    assert(b.open().error==0 && b.close()==0); // Guard released after all failures/close.
    std::puts("PASS: production OS backend syscall doubles; atomic CLOEXEC request/descriptor flags, POLLERR recovery/error propagation, bounded reads and descriptor cleanup; no live socket");
}
