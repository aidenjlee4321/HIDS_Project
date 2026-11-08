#pragma once
#include "hids/journal/contract.hpp"
#include "hids/pilot/transport.hpp"
namespace hids::journal {
using Channel=pilot::Channel;
using Delivery=pilot::Delivery;
using Deadline=pilot::Deadline;
Delivery transmit(Channel&,const std::string& frozen,bool prior_uncertain=false);
// M2 handshake uses the same bounded authenticated channel. It cannot activate.
Json request(Channel&,const Json&,Deadline,std::size_t response_cap=response_limit);
Json exchange_line(Channel&,const std::string& frozen,Deadline);
struct Peer {unsigned uid,gid,ipc_gid;};
class UnixChannel final:public Channel {
public:
    UnixChannel(std::string path,Peer peer,std::function<bool()> cancel):path_(std::move(path)),peer_(peer),cancel_(std::move(cancel)){}
    UnixChannel(const UnixChannel&)=delete;
    UnixChannel& operator=(const UnixChannel&)=delete;
    ~UnixChannel() override{close();}
    int connect(Deadline) override;
    ssize_t write(const void*,std::size_t) override;
    ssize_t read(void*,std::size_t) override;
    bool wait(bool,Deadline) override;
    void close() noexcept override;
    bool cancelled() const override{return cancel_();}
private:
    std::string path_;Peer peer_;std::function<bool()> cancel_;int fd_=-1;
};
}
