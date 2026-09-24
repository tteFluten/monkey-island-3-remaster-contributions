#ifndef SCUMM_EXACT_COSTUME_ROOMS_H
#define SCUMM_EXACT_COSTUME_ROOMS_H
#include "common/config-manager.h"
namespace Scumm {
inline bool exactCostumeRoom(int room, bool topaz) {
    return room > 0 && (topaz || room == 9 || room == 87);
}
inline bool playtestExactRoom(int room) {
    const bool topaz = ConfMan.hasKey("playtest_character_pack") &&
        (ConfMan.get("playtest_character_pack") == "topaz" ||
         ConfMan.get("playtest_character_pack") == "topaz-crisp");
    return exactCostumeRoom(room, topaz);
}
}
#endif
