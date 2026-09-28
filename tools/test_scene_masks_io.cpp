#define FORBIDDEN_SYMBOL_ALLOW_ALL
#include "common/hd_scene_masks_io.h"
#include <cassert>
#include <cstdarg>
#include <fstream>
#include "common/mutex.h"
#include "common/ustr.h"
#include <cctype>
// The engine JSON/string objects are real. No backend is used by this single-threaded test.
// Abort in backend/encoding stubs if a future implementation starts requiring them.
class OSystem; OSystem *g_system=nullptr;
namespace Common {
Mutex::Mutex(){abort();} Mutex::~Mutex(){} bool Mutex::lock(){abort();} bool Mutex::unlock(){abort();}
bool isDigit(int c){return std::isdigit(c);} bool isSpace(int c){return std::isspace(c);} bool isPrint(int c){return std::isprint(c);}
String U32String::encode(CodePage) const {abort();}
}

void warning(const char *, ...) {}
void error(const char *format, ...) { va_list args;va_start(args,format);vfprintf(stderr,format,args);va_end(args);abort(); }
int main(int argc,char **argv){
    assert(argc==2);using namespace HdMasks;auto &s=state();s.path=argv[1];
    load(s.path);assert(s.writable);s.room=9;s.key="9:test";Draft &d=s.drafts[s.key];d.initialized=true;
    Box b;b.id=1;b.parent=1;b.points={{1,1},{100,1},{100,100},{1,100}};d.live.boxes.push_back(b);
    d.live.water.authored=true;d.live.water.palette="any";d.live.water.zones={{{0,0},{1000,0},{1000,1000},{0,1000}}};
    Foreground f;f.plane=2;f.zones={{{0,0},{100,0},{100,100},{0,100}}};f.holes={{{20,20},{40,20},{40,40},{20,40}}};f.replace={{{0,0},{640,0},{640,480},{0,480}}};d.live.foreground={f};
    d.saved=d.live;d.live.animations[animationKey(31,7)]={1.25,-2.5};d.live.animations[animationFrameKey(animationKey(31,7),4)]={-.25,3};changed(d);assert(d.dirty);
    SpriteMask sprite;sprite.zones={rectangle({0,0},{850,1000})};sprite.holes={rectangle({100,100},{200,200})};sprite.edge=2;sprite.feather=.5;
    d.live.animationMasks["topaz:33:8"]=sprite;sprite.edge=1;d.live.animationMasks["topaz:33:8:10"]=sprite;changed(d);assert(d.dirty);
    assert(save());Document copy;assert(loadScene(copy));assert(sameWalk(copy,d.live)&&sameWater(copy.water,d.live.water)&&sameForeground(copy,d.live));
    addForegroundRing(d.live.foreground[0],rectangle({25,25},{35,35}),false);
    addForegroundRing(d.live.foreground[0],rectangle({28,28},{32,32}),true);
    assert(save());Document ordered;assert(loadScene(ordered));assert(sameForeground(ordered,d.live));assert(ordered.animations==d.live.animations);assert(ordered.animationMasks==d.live.animationMasks);
    assert(foregroundAt(&ordered.foreground[0],{26,26},false));assert(!foregroundAt(&ordered.foreground[0],{30,30},true));
    // Head saves share the catalog and atomic conflict checks, but never save
    // another editor's unsaved scene draft (or vice versa).
    auto &heads=HdHead::state();std::string pose=HdHead::key("topaz",2,-1);
    auto scene=d.live;d.live.water.palette="teal";
    heads.commit(pose,{1.25,-2.5});assert(save(true));
    Document unchanged;assert(loadScene(unchanged));assert(sameWater(unchanged.water,scene.water));
    s.loaded=false;load(s.path);assert(HdHead::get(heads.live,pose)==HdHead::Offset(1.25,-2.5));
    heads.commit(pose,{3,4});d.live=scene;assert(save());
    s.loaded=false;load(s.path);assert(HdHead::get(heads.live,pose)==HdHead::Offset(1.25,-2.5));
    bool ok;std::string contents=readFile(s.path,ok);assert(ok);
    {std::ofstream f(s.path);f<<"{\"schemaVersion\":1,\"scenes\":{},\"external\":true}";}
    assert(!save());assert(s.error.find("externally")!=std::string::npos);
    assert(readFile(s.path,ok).find("external")!=std::string::npos);
    heads.commit(pose,{7,8});assert(!save(true));assert(HdHead::get(heads.live,pose)==HdHead::Offset(7,8));
    assert(!catalog("{\"schemaVersion\":99,\"scenes\":{}}"));
    assert(!catalog("bad json"));
    // Simulate reopening after an external change: preserve unrelated metadata and scenes.
    s.loaded=false;load(s.path);assert(s.writable);assert(save());
    auto *saved=catalog(readFile(s.path,ok));assert(saved&&saved->hasChild("external"));delete saved;
    s.key="14:other";s.drafts[s.key].live=d.live;assert(save());
    saved=catalog(readFile(s.path,ok));assert(saved->child("scenes")->hasChild("9:test")&&saved->child("scenes")->hasChild("14:other"));delete saved;
    const std::string path=s.path;s.path+="/missing/file.json";assert(!save());s.path=path;
    // Malformed/unsupported documents are never overwritten.
    {std::ofstream f(path);f<<"{broken";}
    s.loaded=false;load(path);assert(!s.writable);assert(!save());assert(readFile(path,ok)=="{broken");
    auto *legacy=Common::JSON::parse("{\"walkboxes\":[],\"water\":{\"authored\":false,\"palette\":\"any\",\"zones\":[],\"holes\":[]}}");
    Document old;std::string legacyError;assert(decode(legacy,old,legacyError)&&old.foreground.empty()&&old.animations.empty());delete legacy;
    Document invalidAnimation=old;invalidAnimation.animations["31:7"]={0,INFINITY};assert(!validate(invalidAnimation,legacyError));
    invalidAnimation.animations.clear();invalidAnimation.animations["31:7:4:1"]={0,0};assert(!validate(invalidAnimation,legacyError));
    invalidAnimation.animations.clear();setAnimationOffset(invalidAnimation,"31:7",{.25,-2});assert(animationOffset(invalidAnimation,"31:7")==Point(.25,-2));
    setAnimationOffset(invalidAnimation,"31:7",{});assert(invalidAnimation.animations.empty());
    auto *bad=Common::JSON::parse("{\"walkboxes\":[],\"water\":{\"authored\":true,\"palette\":\"any\",\"zones\":[[[0,0],[100,100],[0,100],[100,0]]],\"holes\":[]}}");
    Document invalid;std::string error;assert(!decode(bad,invalid,error));delete bad;
    {std::ofstream f(path);f<<"{\"schemaVersion\":1,\"scenes\":{},\"characterHeads\":{\"topaz:2:-1\":[999,0]}}";}
    s.loaded=false;load(path);assert(!s.writable&&heads.live.empty()&&!save(true));
}
