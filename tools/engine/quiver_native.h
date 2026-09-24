#ifndef SCUMM_QUIVER_NATIVE_H
#define SCUMM_QUIVER_NATIVE_H
#include <cstddef>
namespace QuiverNative {
// Must be called front-to-back with only fully validated replacement poses.
inline void removeActor(unsigned char *display, const unsigned char *under,
                        const unsigned char *after, size_t count) {
    for (size_t i = 0; i < count; ++i)
        if (display[i] == after[i] && under[i] != after[i]) display[i] = under[i];
}
}
#endif
