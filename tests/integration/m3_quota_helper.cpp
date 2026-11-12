// Root-only lab helper: quota changes are fenced to one private loop image.
#include <sys/quota.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <linux/loop.h>
#include <unistd.h>
#include <fcntl.h>
#include <pwd.h>
#include <charconv>
#include <cerrno>
#include <filesystem>
#include <iostream>
#include <string>

int main(int argc,char** argv) {
    if(argc!=5 || getuid()!=0 || geteuid()!=0) return 64;
    try {
        namespace fs=std::filesystem;
        const fs::path image=fs::canonical(argv[1]),mount=fs::canonical(argv[2]),device=fs::canonical(argv[3]);
        if(image!=fs::path(argv[1]) || mount!=fs::path(argv[2]) || device!=fs::path(argv[3]) ||
           image.filename()!="filesystem.ext4" || image.parent_path().parent_path()!="/root" ||
           !image.parent_path().filename().string().starts_with("hids-m3-quota.") ||
           mount.parent_path()!="/run" || !mount.filename().string().starts_with("hids-m3-quota.") ||
           device.parent_path()!="/dev" || !device.filename().string().starts_with("loop")) return 65;
        struct stat backing{},directory{},mounted{},block{};
        if(stat(image.c_str(),&backing) || stat(image.parent_path().c_str(),&directory) ||
           stat(mount.c_str(),&mounted) || stat(device.c_str(),&block) ||
           !S_ISREG(backing.st_mode) || backing.st_uid!=0 || backing.st_nlink!=1 ||
           (backing.st_mode&07777)!=0600 || backing.st_size!=64*1024*1024 ||
           directory.st_uid!=0 || (directory.st_mode&07777)!=0700 ||
           !S_ISBLK(block.st_mode) || block.st_rdev!=mounted.st_dev || mounted.st_dev==backing.st_dev) return 65;
        int fd=open(device.c_str(),O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
        if(fd<0) return 65;
        loop_info64 loop{};const int observed=ioctl(fd,LOOP_GET_STATUS64,&loop);close(fd);
        if(observed || loop.lo_inode!=backing.st_ino || loop.lo_device!=backing.st_dev) return 65;
        const passwd* account=getpwnam("hids-ingest");
        if(!account || account->pw_uid==0 || account->pw_uid>2147483647u) return 65;
        dqblk quota{};
        const auto call=[&](unsigned operation) {
            return quotactl(static_cast<int>((operation<<SUBCMDSHIFT)|USRQUOTA),device.c_str(),
                            static_cast<int>(account->pw_uid),reinterpret_cast<caddr_t>(&quota));
        };
        const std::string action=argv[4];
        if(action!="get") {
            unsigned blocks=0;const auto [end,error]=std::from_chars(action.data(),action.data()+action.size(),blocks);
            if(error!=std::errc{} || end!=action.data()+action.size() || blocks>65536) return 65;
            quota.dqb_bhardlimit=blocks;quota.dqb_bsoftlimit=0;quota.dqb_valid=QIF_BLIMITS;
            if(call(Q_SETQUOTA)) { std::cerr<<"quota_set_errno="<<errno<<'\n';return 1; }
        }
        quota={};
        if(call(Q_GETQUOTA)) { std::cerr<<"quota_get_errno="<<errno<<'\n';return 1; }
        std::cout<<"{\"quota_uid\":"<<account->pw_uid<<",\"hard_blocks\":"<<quota.dqb_bhardlimit
                 <<",\"block_bytes\":1024,\"space_bytes\":"<<quota.dqb_curspace<<"}\n";
    } catch(const std::exception&) { return 65; }
}
