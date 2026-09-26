// Small, engine-independent model for the in-game scene picker.
#ifndef HD_SCENE_JUMP_H
#define HD_SCENE_JUMP_H
namespace HdSceneJump {
struct Room { int number; const char *name; };
const int kRows = 12, kWidth = 320, kRowHeight = 16, kHeaderLines = 3;
const int kLines = kHeaderLines + kRows + 4;
const int kHeight = kLines * kRowHeight + 8;

struct State {
    bool open = false;
    int selected = 0, first = 0, sourceRoom = 0, pending = 0;

    void close() { open = false; pending = 0; }
    void reveal(int count) {
        if (count <= 0) { selected = first = 0; return; }
        if (selected < 0) selected = 0;
        if (selected >= count) selected = count - 1;
        if (first > selected) first = selected;
        if (selected >= first + kRows) first = selected - kRows + 1;
        const int last = count > kRows ? count - kRows : 0;
        if (first > last) first = last;
        if (first < 0) first = 0;
    }
    void show(int current, const Room *rooms, int count) {
        close();
        if (!count) return;
        sourceRoom = current;
        selected = first = 0;
        for (int i = 0; i < count; ++i)
            if (rooms[i].number == current) selected = i;
        reveal(count);
        open = true;
    }
    void move(int delta, int count) { selected += delta; reveal(count); }
    void choose(int index, const Room *rooms, int count) {
        if (!open || index < 0 || index >= count) return;
        selected = index;
        reveal(count);
        if (rooms[index].number == sourceRoom) close();
        else pending = rooms[index].number;
    }
    // Called on the engine thread, never from the event handler. A changed
    // room or a busy engine cancels the request instead of deferring it.
    int takePending(bool ready, int current) {
        if (!ready || current != sourceRoom) { close(); return 0; }
        const int room = pending;
        if (room) close();
        return room;
    }
};
}
#endif
