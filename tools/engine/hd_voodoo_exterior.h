#ifndef HD_VOODOO_EXTERIOR_H
#define HD_VOODOO_EXTERIOR_H
#include "common/hd_plunder_map.h"

// Room 29: native simulation -> landmarks on the supplied 2048x1152 preview.
// The painting is unchanged. The inverse maps input to the original walkboxes,
// keeping their connections, actor scaling, exits and puzzle scripts intact.
namespace HdVoodooExterior {
static const char kSource[] = "77d0b9f10c76ae10f230f9386c8d032669535b838be69971e66e00f4443f5cb6";
using HdPlunderMap::Point;
static const Point kX[] = {{0,250},{29,335},{94,500},{150,635},{202,746},
    {220,790},{265,900},{300,984},{346,1094},{376,1190},{385,1210},
    {437,1335},{475,1430},{513,1540},{640,1845}};
static const Point kY[] = {{0,0},{104,275},{130,348},{160,420},{230,580},
    {249,623},{261,664},{267,674},{301,753},{316,805},{334,846},
    {360,907},{363,915},{414,1030},{429,1072},{480,1198}};
// The original walk-in starts against the 640px left edge. In the new art
// that point is inside the painting, beside a path leaving through the bottom.
// Ease the actor's draw origin below that edge until it joins the bridge. The
// same position-only curve works in reverse, and across save/restore.
inline int entranceOffset(double x,double y) {
    auto smooth=[](double t){t=t<0?0:t>1?1:t;return t*t*(3-2*t);};
    return int(260*smooth((100-x)/100)*smooth((y-414)/15)+.5);
}
inline double paintX(double x) { return HdPlunderMap::interpolate(kX,x); }
inline double paintY(double y) { return HdPlunderMap::interpolate(kY,y); }
inline double nativeX(double x) { return HdPlunderMap::interpolate(kX,x,true); }
inline double nativeY(double y) { return HdPlunderMap::interpolate(kY,y,true); }
inline double sourceX(double x) { return nativeX(256 + x * 2.4); }
inline double sourceY(double y) { return nativeY(y * 2.4); }
inline int screenX(double x) { return int((paintX(x)-256)/2.4 + 0.5); }
inline int screenY(double y) { return int(paintY(y)/2.4 + 0.5); }
inline bool pointer(int px,int py,int left,int top,int width,int height,int &x,int &y) {
    if (height <= 0 || width <= 0) return false;
    const double wide = height * 16.0/9.0;
    const double paintx = (px-left-(width-wide)/2)*2048/wide;
    const double painty = (py-top)*1152.0/height;
    if (paintx<0 || paintx>=2048 || painty<0 || painty>=1152) return false;
    x = int(nativeX(paintx)+0.5); y = int(nativeY(painty)+0.5);
    x = x<0 ? 0 : x>639 ? 639 : x;
    y = y<0 ? 0 : y>479 ? 479 : y;
    return true;
}
inline bool water(double x,double y,unsigned r,unsigned g,unsigned b) {
    static const Point pools[] = {{0,570},{210,566},{350,611},{515,622},
        {605,626},{822,605},{1030,592},{1050,650},{1200,650},{1370,669},
        {1550,690},{1730,707},{1880,665},{2048,675},{2048,1152},{0,1152}};
    static const Point bridge[] = {{350,1010},{415,760},{905,715},
        {1140,880},{1130,977},{715,1110}};
    static const Point path[] = {{1040,724},{1190,647},{1290,648},{1375,695},
        {1545,742},{1670,822},{1608,889},{1490,924},{1300,1028},{980,1030},
        {924,941},{1060,827},{1240,794}};
    static const Point foreground[] = {{170,1152},{190,1070},{390,995},
        {595,1030},{725,1090},{625,1152}};
    return b>35 && b*100>r*115 && b*100>g*103 &&
        HdPlunderMap::polygon(pools,x,y) && !HdPlunderMap::polygon(bridge,x,y) &&
        !HdPlunderMap::polygon(path,x,y) && !HdPlunderMap::polygon(foreground,x,y);
}
}
#endif
