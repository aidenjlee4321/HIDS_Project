// Test-only link wrapper. Never link into the production collector.
#include <auparse.h>
#include <new>
extern "C" auparse_state_t* __real_auparse_init(ausource_t,const void*);
extern "C" auparse_state_t* __wrap_auparse_init(ausource_t source,const void* bytes) {
    static unsigned calls=0;
    if (++calls==2) {
#ifdef HIDS_M3_FAULT_ALLOCATE
        throw std::bad_alloc();
#else
        return nullptr;
#endif
    }
    return __real_auparse_init(source,bytes);
}
