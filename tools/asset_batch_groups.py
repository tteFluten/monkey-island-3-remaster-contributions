"""Combine frozen asset work units into larger scene-local execution batches."""
from collections import OrderedDict


def group_batches(batches, size=100):
    if not isinstance(size,int) or isinstance(size,bool) or size<1:
        raise ValueError('Batch size must be a positive integer')
    scenes=OrderedDict();seen=set()
    for batch in batches:
        if batch['phase']!='process':continue
        scene=scenes.setdefault(batch['scene'],dict(room=batch['room'],name=batch['name'],sources=[],owners={}))
        for source in batch['sources']:
            if source in seen:raise ValueError('Source occurs in multiple work units')
            seen.add(source);scene['sources'].append(source);scene['owners'][source]=batch['id']
    result=[]
    for scene_id,scene in scenes.items():
        for offset in range(0,len(scene['sources']),size):
            sources=scene['sources'][offset:offset+size]
            result.append(dict(id=f'{scene_id}-large-{offset//size+1:03}',scene=scene_id,
                room=scene['room'],name=scene['name'],sources=sources,
                work_units=list(dict.fromkeys(scene['owners'][s] for s in sources))))
    return result
