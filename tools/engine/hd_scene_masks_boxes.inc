// Included in boxes.cpp, where the packed v8 Box resource layout is known.
static Box hdMaskExtra[255];
static bool hdMaskExtraReady[255] = {};
static int hdMaskResourceRoom = -1;
static bool hdMaskSyncing = false, hdMaskNative = false;
void ScummEngine::hdMasksSync() {
    if (_game.id != GID_CMI || _game.version != 8 || hdMaskSyncing || !ConfMan.hasKey("hd_scene_masks_path")) return;
    auto &s=HdMasks::state();
    if(s.room==_currentRoom && s.draft())return;
    byte *resource=getResourceAddress(rtMatrix,2);if(!resource)return;
    const unsigned count=READ_LE_UINT32(resource);
    if(count>255 || getResourceSize(rtMatrix,2)<(int)(4+count*SIZEOF_BOX_V8))return;
    hdMaskSyncing=true;
    HdMasks::load(ConfMan.get("hd_scene_masks_path").c_str());
    bool ok;std::string source=HdMasks::readFile((ConfMan.get("hd_path")+Common::String::format("/backgrounds/bg_%04d.png.stamp",_currentRoom)).c_str(),ok);
    if(source.empty())source="original";else source=source.substr(0,source.find_first_of(":\r\n"));
    const std::string widePath=(ConfMan.get("hd_path")+Common::String::format("/widescreen/bg_%04d.png",_currentRoom)).c_str();
    FILE *wide=fopen(widePath.c_str(),"rb");s.widePainting=wide!=nullptr;if(wide)fclose(wide);
    if(s.writable)s.error.clear();
    s.room=_currentRoom;s.source=source;s.key=std::to_string(_currentRoom)+":"+source;
    s.animationMaskDrag=s.animationMaskEdit=s.animationMaskInsert=false;s.animationDrag=false;s.animationSelected.clear();s.animationVisuals.clear();HdSprites::cache().clear();s.animationFrame=-1;HdHead::state().frame=-1;
    s.clipView=HdMasks::EditView();s.clipPan=s.clipInsert=false;
    s.drag=s.pending=s.adding=s.bypassForeground=s.rectangleDrag=false;s.clipTool=0;s.creation.clear();s.selected=s.node=-1;
    memset(hdMaskExtraReady,0,sizeof(hdMaskExtraReady));hdMaskResourceRoom=_currentRoom;
    auto &d=s.drafts[s.key];
    if(!d.initialized) {
        d.initialized=true;
        for(unsigned id=0;id<count;++id) {
            const Box *b=(const Box *)(resource+4+id*SIZEOF_BOX_V8);
            HdMasks::Box box;box.id=box.parent=id;
            box.points={{(double)(int32)FROM_LE_32(b->v8.ulx),(double)(int32)FROM_LE_32(b->v8.uly)},
                        {(double)(int32)FROM_LE_32(b->v8.urx),(double)(int32)FROM_LE_32(b->v8.ury)},
                        {(double)(int32)FROM_LE_32(b->v8.lrx),(double)(int32)FROM_LE_32(b->v8.lry)},
                        {(double)(int32)FROM_LE_32(b->v8.llx),(double)(int32)FROM_LE_32(b->v8.lly)}};
            d.base.boxes.push_back(box);
        }
        d.base.water=HdMasks::defaults(_currentRoom,source);
        const bool registered=(_currentRoom==13&&source==HdPlunderMap::kSource)||(_currentRoom==29&&source==HdVoodooExterior::kSource);
        if(s.widePainting&&!registered)for(auto *rings:{&d.base.water.zones,&d.base.water.holes})for(auto &ring:*rings)for(auto &point:ring)point.x=(point.x*640/1000+107)*1000/854;
        d.live=d.saved=d.base;
        HdMasks::Document loaded;
        if(HdMasks::loadScene(loaded)) {
            bool valid=loaded.boxes.size()>=count;
            for(unsigned i=0;i<loaded.boxes.size();++i) {
                auto &b=loaded.boxes[i];valid=valid&&b.id==(int)i&&b.parent<(int)count;
                if(i>=count||b.points!=d.base.boxes[i].points)valid=valid&&HdMasks::validWalk(b.points,i<count?&d.base.boxes[i].points:nullptr);
            }
            if(valid)d.live=d.saved=loaded;else{s.error="Saved walkboxes do not match this room; using originals";s.writable=false;}
        }
    }
    HdMasks::changed(d);hdMaskSyncing=false;
}
int ScummEngine::hdMasksBoxCount(int count) {
    if(hdMaskNative)return count;
    hdMasksSync();auto &s=HdMasks::state();auto *d=s.draft();
    return s.room==_currentRoom&&d&&d->walkChanged?MAX(count,(int)d->live.boxes.size()):count;
}
Box *ScummEngine::hdMasksExtraBox(int id) {
    if(hdMaskNative)return nullptr;
    hdMasksSync();auto &s=HdMasks::state();auto *d=s.draft();
    byte *resource=getResourceAddress(rtMatrix,2);if(!resource||s.room!=_currentRoom||!d||!d->walkChanged)return nullptr;
    int count=READ_LE_UINT32(resource);if(id<count||id>=255)return nullptr;
    const auto *b=HdMasks::find(d->live,id);if(!b||b->parent>=count)return nullptr;
    if(hdMaskResourceRoom!=_currentRoom){memset(hdMaskExtraReady,0,sizeof(hdMaskExtraReady));hdMaskResourceRoom=_currentRoom;}
    if(!hdMaskExtraReady[id]){memcpy(&hdMaskExtra[id],resource+4+b->parent*SIZEOF_BOX_V8,SIZEOF_BOX_V8);hdMaskExtraReady[id]=true;}
    return &hdMaskExtra[id];
}
bool ScummEngine::hdMasksCoordinates(int id,BoxCoords &out) {
    if(hdMaskNative)return false;
    hdMasksSync();auto &s=HdMasks::state();auto *d=s.draft();if(s.room!=_currentRoom||!d||!d->walkChanged)return false;
    const auto *b=HdMasks::find(d->live,id);if(!b)return false;
    auto pt=[](HdMasks::Point p){return Common::Point((int)p.x,(int)p.y);};
    out.ul=pt(b->points[0]);out.ur=pt(b->points[1]);out.lr=pt(b->points[2]);out.ll=pt(b->points[3]);return true;
}
bool ScummEngine::hdMasksDisabled(int id) {
    if(hdMaskNative)return false;
    auto &s=HdMasks::state();auto *d=s.draft();const auto *b=s.room==_currentRoom&&d&&d->walkChanged?HdMasks::find(d->live,id):nullptr;return b&&b->disabled;
}
int ScummEngine::hdMasksNextBox(int from,int to) {
    if(hdMaskNative)return -2;
    // -2 delegates to the unmodified native routing resource.
    hdMasksSync();auto &s=HdMasks::state();auto *d=s.draft();if(s.room!=_currentRoom||!d||!d->walkChanged)return -2;
    int n=getNumBoxes();if(from==255)return to<n?to:-1;if(from<0||to<0||from>=n||to>=n)return -1;
    if(from==to)return to;
    std::vector<int> first(n,-1),queue;first[from]=from;queue.push_back(from);
    for(unsigned i=0;i<queue.size();++i)for(int j=1;j<n;++j)if(first[j]<0&&hdMasksConnected(queue[i],j)){
        first[j]=queue[i]==from?j:first[queue[i]];if(j==to)return first[j];queue.push_back(j);
    }
    return -1;
}

bool ScummEngine::hdMasksConnected(int from,int to) {
    auto &s=HdMasks::state();auto *d=s.draft();if(!d||s.room!=_currentRoom||from==to)return false;
    if((getBoxFlags(from)|getBoxFlags(to))&kBoxInvisible)return false;
    if(from<(int)d->base.boxes.size()&&to<(int)d->base.boxes.size()){
        hdMaskNative=true;int next=getNextBox(from,to);hdMaskNative=false;return next==to;
    }
    return areBoxesNeighbors(from,to);
}

void ScummEngine::hdMasksTrimExtras(unsigned count) {
    for(unsigned i=count;i<255;++i)hdMaskExtraReady[i]=false;
}
