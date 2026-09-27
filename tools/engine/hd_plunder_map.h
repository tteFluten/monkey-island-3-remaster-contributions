#ifndef HD_PLUNDER_MAP_H
#define HD_PLUNDER_MAP_H

// Presentation coordinates are thousandths of the supplied 16:9 painting.
// Resource geometry, object IDs, walking and story scripts stay native.
namespace HdPlunderMap {
static const char kSource[] = "e5369aec8e127c954aa7b3dba42df3c9ac58de0bec25fdc06a173769f5e5c194";
struct Point { double x, y; };
struct Destination {
    const char *name;
    int x, y; // An unambiguous point inside the original object's hit box.
    Point outline[8];
    unsigned count;
};
static const Destination kDestinations[] = {
    {"Danjer Cove", 156, 168, {{178,302},{220,296},{310,325},{310,382},{237,410},{178,410}}, 6},
    {"Voodoo swamp", 236, 276, {{300,503},{403,496},{491,592},{421,671},{270,655},{246,592}}, 6},
    {"Brimstone Beach", 564, 252, {{830,500},{838,511},{820,534},{785,584},{750,594},{751,567}}, 6},
    {"Beach club", 616, 204, {{853,437},{893,426},{912,461},{873,507},{838,489}}, 5},
    {"Puerto Pollo west", 392, 216, {{548,382},{583,366},{602,405},{609,493},{588,520},{559,472}}, 6},
    {"Puerto Pollo upper", 450, 138, {{600,299},{627,268},{654,283},{684,334},{673,381},{602,380},{585,350}}, 7},
    {"Puerto Pollo east", 516, 168, {{685,334},{706,362},{762,393},{766,422},{691,448},{619,428},{619,382},{673,382}}, 8},
    {"Fort", 456, 328, {{636,607},{686,622},{726,661},{733,683},{685,790},{599,752},{565,713},{581,660}}, 8}
};
static const unsigned kCount = sizeof(kDestinations) / sizeof(kDestinations[0]);
inline bool polygon(const Point *p, unsigned count, double x, double y) {
    bool inside = false;
    for (unsigned i = 0, j = count - 1; i < count; j = i++)
        if ((p[i].y > y) != (p[j].y > y) &&
            x < (p[j].x - p[i].x) * (y - p[i].y) / (p[j].y - p[i].y) + p[i].x)
            inside = !inside;
    return inside;
}
template<unsigned N> inline bool polygon(const Point (&p)[N], double x, double y) {
    return polygon(p, N, x, y);
}
inline int target(double x, double y) {
    for (unsigned i = 0; i < kCount; ++i)
        if (polygon(kDestinations[i].outline, kDestinations[i].count, x, y)) return i;
    return -1;
}
inline void script(double x, double y, int &sx, int &sy) {
    const int i = target(x, y);
    sx = i < 0 ? 320 : kDestinations[i].x;
    sy = i < 0 ? 476 : kDestinations[i].y;
}
// Invert the exact full-width frame surrounding the backend's 4:3 rectangle.
inline bool pointer(int px, int py, int left, int top, int width, int height, int &sx, int &sy) {
    if (height <= 0) return false;
    const double wide = height * 16.0 / 9.0;
    const double x = (px - left - (width - wide) / 2) * 1000 / wide;
    const double y = (py - top) * 1000.0 / height;
    if (x < 0 || x >= 1000 || y < 0 || y >= 1000) return false;
    script(x, y, sx, sy);
    return true;
}
// Landmark registration, native room pixels -> 2048x1152 preview pixels. Separate
// monotone axes preserve walking continuity and align the boat's cove anchor.
static const Point kX[] = {{0,112},{108,405},{236,727},{400,1190},{450,1365},{564,1620},{620,1760},{640,1820}};
static const Point kY[] = {{0,0},{136,348},{165,420},{200,482},{276,674},{328,806},{400,995},{480,1152}};
template<unsigned N> inline double interpolate(const Point (&knots)[N], double value, bool inverse = false) {
    unsigned i = 1;
    while (i < N - 1 && value > (inverse ? knots[i].y : knots[i].x)) ++i;
    const double a = inverse ? knots[i-1].y : knots[i-1].x;
    const double b = inverse ? knots[i].y : knots[i].x;
    const double c = inverse ? knots[i-1].x : knots[i-1].y;
    const double d = inverse ? knots[i].x : knots[i].y;
    return c + (value - a) * (d - c) / (b - a);
}
inline double sourceX(double x) { return interpolate(kX, 256 + x * 2.4, true); }
inline double sourceY(double y) { return interpolate(kY, y * 2.4, true); }

// Full-frame sea and harbor; traced against the new painting. Deliberately
// conservative around the shore and separate from the legacy room-13 mask.
inline bool water(double x, double y, unsigned r, unsigned g, unsigned b) {
    static const Point sea[] = {{0,275},{210,214},{214,303},{185,319},{117,360},{93,434},
        {63,490},{111,537},{181,580},{245,619},{226,696},{191,761},{200,846},
        {221,925},{277,961},{350,982},{476,960},{581,907},{594,860},{631,831},
        {689,788},{735,690},{753,651},{753,602},{831,576},{911,497},{962,402},
        {976,274},{1000,281},{1000,1000},{0,1000}};
    static const Point bay[] = {{620,437},{665,452},{724,422},{758,422},{792,438},
        {831,451},{829,477},{791,523},{748,562},{738,587},{767,611},{743,637},
        {711,625},{677,605},{633,600},{609,568},{594,525},{603,490}};
    static const Point cove[] = {{199,358},{215,321},{242,329},{250,368},{226,394},{211,398}};
    static const Point ship[] = {{822,593},{850,591},{859,670},{832,680},{822,649}};
    static const Point wrecks[] = {{752,681},{800,677},{819,723},{838,788},{825,832},{792,824},{764,758}};
    return b > 6 && b * 100 > r * 112 && b * 100 > g * 70 &&
        (polygon(sea,x,y) || polygon(bay,x,y) || polygon(cove,x,y)) &&
        !polygon(ship,x,y) && !polygon(wrecks,x,y);
}
}
#endif
