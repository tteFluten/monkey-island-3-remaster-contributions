#ifndef SCUMM_HD_AUTOSAVE_H
#define SCUMM_HD_AUTOSAVE_H
// Autosave: ScummVM's periodic autosave (slot 0) plus one at every chapter
// change, and a Load-page tile for it. On the book's Load page the first tile
// is the autosave and every other tile shows the slot before it; the Save page
// keeps its numbering, so the autosave slot is never offered for saving.

namespace HdAutosave {

// Chapter title cards: "Part I" to "Part VI".
inline bool chapterCard(int room) { return (room >= 4 && room <= 8) || room == 88; }

// Book tiles on the Load page, and the save slot each one shows.
inline int loadSlot(int tile) { return tile - 1; }

// Stamp slot for the autosave file: slot 0 means the temporary current game
// to the book scripts, so the autosave needs its own value.
static const int kStampSlot = 1000;

// Minutes since 1970 of a SCUMM save's date (day << 24 | month << 16 | year)
// and time (hour << 8 | minute).
inline long minutes(unsigned int date, unsigned int time) {
    long y = date & 0xFFFF;
    const long m = (date >> 16) & 0xFF, d = (date >> 24) & 0xFF;
    y -= m <= 2;
    const long era = (y >= 0 ? y : y - 399) / 400;
    const long yoe = y - era * 400;
    const long doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    const long doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    const long days = era * 146097 + doe - 719468;
    return days * 1440 + ((time >> 8) & 0xFF) * 60 + (time & 0xFF);
}

} // namespace HdAutosave

#endif
