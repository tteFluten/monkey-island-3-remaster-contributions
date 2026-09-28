#ifndef HD_SCENE_MASKS_IO_H
#define HD_SCENE_MASKS_IO_H
#include "common/formats/json.h"
#include "common/hd_scene_masks.h"
#include <cstdio>
#include <unistd.h>
#include <sys/file.h>
#include <fcntl.h>
#include <cerrno>
namespace HdMasks {
inline std::string readFile(const std::string &path,bool &ok) {
    ok=true;FILE *f=fopen(path.c_str(),"rb");if(!f){ok=errno==ENOENT;return "";}
    std::string s;char buffer[4096];size_t n;
    while((n=fread(buffer,1,sizeof(buffer),f))) {s.append(buffer,n);if(s.size()>16*1024*1024){ok=false;break;}}
    if(ferror(f))ok=false;fclose(f);return s;
}
inline Common::JSONValue *number(double n){return new Common::JSONValue(n);}
inline Common::JSONValue *ringsJSON(const std::vector<Ring> &rings) {
    Common::JSONArray result;
    for(const auto &r:rings){Common::JSONArray ring;for(auto p:r){Common::JSONArray xy;xy.push_back(number(p.x));xy.push_back(number(p.y));ring.push_back(new Common::JSONValue(xy));}result.push_back(new Common::JSONValue(ring));}
    return new Common::JSONValue(result);
}
inline Common::JSONValue *encode(const Document &d) {
    Common::JSONObject out;Common::JSONArray boxes;
    for(const auto &b:d.boxes){Common::JSONObject v;v["id"]=number(b.id);v["parent"]=number(b.parent);v["disabled"]=new Common::JSONValue(b.disabled);auto *r=ringsJSON({b.points});v["points"]=new Common::JSONValue(*r->asArray()[0]);delete r;boxes.push_back(new Common::JSONValue(v));}
    out["walkboxes"]=new Common::JSONValue(boxes);
    Common::JSONObject water;water["authored"]=new Common::JSONValue(d.water.authored);water["palette"]=new Common::JSONValue(Common::String(d.water.palette.c_str()));
    water["zones"]=ringsJSON(d.water.zones);water["holes"]=ringsJSON(d.water.holes);out["water"]=new Common::JSONValue(water);
    Common::JSONArray planes;
    for(auto &f:d.foreground){Common::JSONObject v;v["plane"]=number(f.plane);v["zones"]=ringsJSON(f.zones);v["holes"]=ringsJSON(f.holes);v["replace"]=ringsJSON(f.replace);
        if(!f.order.empty()){Common::JSONArray order;for(int index:f.order)order.push_back(number(index));v["order"]=new Common::JSONValue(order);}
        planes.push_back(new Common::JSONValue(v));}
    out["foreground"]=new Common::JSONValue(planes);
    Common::JSONObject animations;for(auto &entry:d.animations){Common::JSONArray xy;xy.push_back(number(entry.second.x));xy.push_back(number(entry.second.y));animations[entry.first.c_str()]=new Common::JSONValue(xy);}out["animations"]=new Common::JSONValue(animations);
    if(!d.animationMasks.empty()){Common::JSONObject masks;for(auto &entry:d.animationMasks){const auto &m=entry.second;Common::JSONObject value;
        value["zones"]=ringsJSON(m.zones);value["holes"]=ringsJSON(m.holes);value["edge"]=number(m.edge);value["feather"]=number(m.feather);masks[entry.first.c_str()]=new Common::JSONValue(value);}out["animationMasks"]=new Common::JSONValue(masks);}
    return new Common::JSONValue(out);
}
inline bool readRing(const Common::JSONValue *v,Ring &r) {
    if(!v||!v->isArray()||v->asArray().size()>4096)return false;
    for(auto *xy:v->asArray()){if(!xy->isArray()||xy->asArray().size()!=2)return false;auto &a=xy->asArray();if(!a[0]->isNumber()||!a[1]->isNumber())return false;r.push_back({a[0]->asNumber(),a[1]->asNumber()});}return true;
}
inline bool decode(Common::JSONValue *v,Document &d,std::string &error) {
    if(!v||!v->isObject()||!v->hasChild("walkboxes")||!v->child("walkboxes")->isArray()||!v->hasChild("water"))return false;
    if(v->child("walkboxes")->asArray().size()>255)return false;
    for(auto *entry:v->child("walkboxes")->asArray()){
        if(!entry->isObject()||!entry->hasChild("id")||!entry->child("id")->isIntegerNumber()||!entry->hasChild("parent")||!entry->child("parent")->isIntegerNumber()||!entry->hasChild("disabled")||!entry->child("disabled")->isBool()||!entry->hasChild("points"))return false;
        if(entry->child("id")->asIntegerNumber()<0||entry->child("id")->asIntegerNumber()>=255||entry->child("parent")->asIntegerNumber()<0||entry->child("parent")->asIntegerNumber()>=255)return false;
        Box b;b.id=entry->child("id")->asIntegerNumber();b.parent=entry->child("parent")->asIntegerNumber();b.disabled=entry->child("disabled")->asBool();if(!readRing(entry->child("points"),b.points))return false;d.boxes.push_back(b);
    }
    auto *w=v->child("water");if(!w->isObject()||!w->hasChild("authored")||!w->child("authored")->isBool()||!w->hasChild("palette")||!w->child("palette")->isString())return false;
    d.water.authored=w->child("authored")->asBool();d.water.palette=w->child("palette")->asString().c_str();
    for(const char *key:{"zones","holes"}){if(!w->hasChild(key)||!w->child(key)->isArray()||w->child(key)->asArray().size()>1024)return false;for(auto *contour:w->child(key)->asArray()){Ring ring;if(!readRing(contour,ring))return false;(key[0]=='z'?d.water.zones:d.water.holes).push_back(ring);}}
    // Optional in schema 1 so existing walk/water files remain valid.
    if(v->hasChild("foreground")){
        auto *planes=v->child("foreground");if(!planes->isArray()||planes->asArray().size()>7)return false;
        for(auto *entry:planes->asArray()){
            if(!entry->isObject()||!entry->hasChild("plane")||!entry->child("plane")->isIntegerNumber())return false;
            int id=entry->child("plane")->asIntegerNumber();if(id<1||id>7)return false;
            Foreground f;f.plane=id;
            for(const char *key:{"zones","holes","replace"}){
                if(!entry->hasChild(key)||!entry->child(key)->isArray()||entry->child(key)->asArray().size()>1024)return false;
                auto &rings=key[0]=='z'?f.zones:key[0]=='h'?f.holes:f.replace;
                for(auto *contour:entry->child(key)->asArray()){Ring ring;if(!readRing(contour,ring))return false;rings.push_back(ring);}
            }
            if(entry->hasChild("order")){
                auto *order=entry->child("order");if(!order->isArray()||order->asArray().size()>2048)return false;
                for(auto *item:order->asArray()){if(!item->isIntegerNumber()||item->asIntegerNumber()<-1024||item->asIntegerNumber()>1024)return false;f.order.push_back(item->asIntegerNumber());}
            }
            d.foreground.push_back(f);
        }
    }
    if(v->hasChild("animations")){
        auto *values=v->child("animations");if(!values->isObject()||values->asObject().size()>256)return false;
        for(auto &entry:values->asObject()){auto *xy=entry._value;if(!xy->isArray()||xy->asArray().size()!=2||!xy->asArray()[0]->isNumber()||!xy->asArray()[1]->isNumber())return false;d.animations[entry._key.c_str()]={xy->asArray()[0]->asNumber(),xy->asArray()[1]->asNumber()};}
    }
    if(v->hasChild("animationMasks")){
        auto *values=v->child("animationMasks");if(!values->isObject()||values->asObject().size()>256)return false;
        for(auto &entry:values->asObject()){auto *value=entry._value;SpriteMask m;
            if(!value->isObject()||!value->hasChild("edge")||!value->child("edge")->isIntegerNumber()||!value->hasChild("feather")||!value->child("feather")->isNumber())return false;
            auto edge=value->child("edge")->asIntegerNumber();if(edge< -1||edge>2)return false;m.edge=edge;m.feather=value->child("feather")->asNumber();
            for(const char *key:{"zones","holes"}){if(!value->hasChild(key)||!value->child(key)->isArray()||value->child(key)->asArray().size()>64)return false;
                for(auto *contour:value->child(key)->asArray()){Ring ring;if(!readRing(contour,ring))return false;(key[0]=='z'?m.zones:m.holes).push_back(ring);}}
            d.animationMasks[entry._key.c_str()]=m;
        }
    }
    return validate(d,error);
}
inline Common::JSONValue *catalog(const std::string &text) {
    auto *root=Common::JSON::parse(text.empty()?"{\"schemaVersion\":1,\"scenes\":{}}":text.c_str());
    if(!root||!root->isObject()||!root->hasChild("schemaVersion")||!root->child("schemaVersion")->isIntegerNumber()||root->child("schemaVersion")->asIntegerNumber()!=1||!root->hasChild("scenes")||!root->child("scenes")->isObject()){delete root;return nullptr;}return root;
}
inline void load(const std::string &path) {
    auto &s=state();if(s.loaded)return;s.loaded=true;s.path=path;bool ok;
    s.fileText=readFile(path,ok);auto *root=catalog(s.fileText);s.writable=ok&&root&&!path.empty();
    if(!s.writable)s.error="Cannot read mask file or unsupported schema; file preserved";
    auto &heads=HdHead::state();heads.live.clear();heads.drag=heads.original=false;
    if(root&&root->hasChild("characterHeads")){
        auto *values=root->child("characterHeads");bool valid=values->isObject()&&values->asObject().size()<=4096;
        if(valid)for(auto &entry:values->asObject()){
            auto *v=entry._value;
            if(entry._key.empty()||entry._key.size()>128||!v->isArray()||v->asArray().size()!=2||!v->asArray()[0]->isNumber()||!v->asArray()[1]->isNumber()){valid=false;break;}
            HdHead::Offset p(v->asArray()[0]->asNumber(),v->asArray()[1]->asNumber());if(!HdHead::valid(p)){valid=false;break;}
            heads.live[entry._key.c_str()]=p;
        }
        if(!valid){heads.live.clear();s.writable=false;s.error="Invalid head offsets; original positions retained and file preserved";}
    }
    heads.saved=heads.live;
    delete root;
}
inline bool loadScene(Document &d) {
    auto &s=state();auto *root=catalog(s.fileText);if(!root)return false;
    auto *scenes=root->child("scenes");bool present=scenes->hasChild(s.key.c_str());
    if(present&&!decode(scenes->child(s.key.c_str()),d,s.error)){s.error="Invalid scene mask; original geometry retained";s.writable=false;present=false;}
    delete root;return present;
}
inline bool save(bool headsOnly=false) {
    auto &s=state();auto *draft=s.draft();auto &heads=HdHead::state();if((!draft&&!headsOnly)||!s.writable){s.error="Mask file is not writable";return false;}
    if(!headsOnly&&!validate(draft->live,s.error))return false;
    if(headsOnly){
        if(heads.live.size()>4096){s.error="Too many head offsets";return false;}
        for(auto &entry:heads.live)if(entry.first.empty()||entry.first.size()>128||!HdHead::valid(entry.second)){s.error="Invalid head offset; draft kept";return false;}
    }
    int lock=open((s.path+".lock").c_str(),O_CREAT|O_RDWR,0600);
    if(lock<0){s.error="Cannot create save lock; check folder permissions";return false;}
    if(flock(lock,LOCK_EX|LOCK_NB)!=0){close(lock);s.error="Another editor is saving; retry";return false;}
    bool ok;std::string current=readFile(s.path,ok);
    if(!ok||current!=s.fileText){close(lock);s.error="Mask file changed externally; draft kept. Restart to reload.";return false;}
    auto *root=catalog(current);if(!root){close(lock);s.error="Invalid mask file; draft kept";return false;}
    // Explicit value copies: Common JSON containers otherwise share owning pointers.
    Common::JSONObject object,scenes;
    for(auto &entry:root->asObject())if(entry._key!=(headsOnly?"characterHeads":"scenes"))object[entry._key]=new Common::JSONValue(*entry._value);
    if(headsOnly){Common::JSONObject offsets;for(auto &entry:heads.live){Common::JSONArray xy;xy.push_back(number(entry.second.x));xy.push_back(number(entry.second.y));offsets[entry.first.c_str()]=new Common::JSONValue(xy);}object["characterHeads"]=new Common::JSONValue(offsets);}
    else{
        for(auto &entry:root->child("scenes")->asObject())scenes[entry._key]=new Common::JSONValue(*entry._value);
        if(scenes.contains(s.key.c_str()))delete scenes[s.key.c_str()];scenes[s.key.c_str()]=encode(draft->live);
        object["scenes"]=new Common::JSONValue(scenes);
    }
    Common::JSONValue output(object);std::string text=output.stringify(true).c_str();text+='\n';
    delete root;
    std::string temporary=s.path+".tmp.XXXXXX";std::vector<char> name(temporary.begin(),temporary.end());name.push_back(0);
    int fd=mkstemp(name.data());ok=fd>=0;
    if(ok){size_t at=0;while(at<text.size()){ssize_t n=write(fd,text.data()+at,text.size()-at);if(n<=0){ok=false;break;}at+=n;}if(fsync(fd)!=0)ok=false;if(close(fd)!=0)ok=false;}
    if(ok){bool readable;ok=readFile(s.path,readable)==current&&readable;}
    if(ok)ok=rename(name.data(),s.path.c_str())==0;
    if(!ok){unlink(name.data());s.error="Could not save masks; draft kept";}else{s.fileText=text;
        if(headsOnly){heads.saved=heads.live;s.error="Saved head offsets";}
        else{draft->saved=draft->live;draft->dirty=false;s.error="Saved scene masks";}
    }
    close(lock);return ok;
}
}
#endif
