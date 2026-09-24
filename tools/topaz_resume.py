#!/usr/bin/env python3
"""Resume Guybrush, then missing rooms, under one explicitly authorized allowance."""
import argparse
import os
import time

from quiver_cannon import atomic, locked
from topaz_allowance import Allowance
from topaz_guybrush import execute as guybrush
from topaz_continue_scenes import continue_scenes
from topaz_scenes import ROOT, OUTPUT, read
from install_asset_drafts import install
from package_topaz_drafts import package


def execute(allowance_id, max_credits, start_room=19):
    allowance=Allowance(OUTPUT,allowance_id)
    # Serializes the full handoff as well as duplicate launches of this command.
    with locked(allowance.folder/'runner'):
        with locked(OUTPUT), locked(OUTPUT/'batches'):
            allowance.create(max_credits,start_room).validate()
        def progress(state,phase,**details):
            value=dict(state=state,phase=phase,pid=os.getpid(),updated_at=time.time(),
                       **allowance.summary(),**details)
            atomic(allowance.folder/'progress.json',value)
            print('CONTINUATION',value,flush=True)
            return value
        phase='guybrush';state='interrupted';error=None
        progress('running',phase)
        try:
            state=guybrush(0,allowance_id=allowance_id)
            if state=='production_checkpoint':
                phase='rooms';progress('running',phase)
                state=continue_scenes(start_room,allowance_id=allowance_id)
        except Exception as failure:
            error=failure
        details={}
        # Retain deliverables even when a provider error stops new submissions.
        try:
            with locked(OUTPUT), locked(OUTPUT/'batches'):
                details['installation']=install(OUTPUT,ROOT/'.playtest')['new_or_changed']
                details['package']=package(ROOT)
                from asset_pack import verify
                details['verification']=verify(ROOT,media=True)
        except Exception as failure:
            details['delivery_pending']=str(failure)
        if error:details['error']=str(error)
        checkpoint=(OUTPUT/'batches/guybrush-all/progress.json' if phase=='guybrush' else
                    allowance.folder/f'continuation-from-{start_room:04}'/'progress.json')
        details['checkpoint']=read(checkpoint,{})
        result=progress('interrupted' if error else state,phase,**details)
        if error:raise error
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allowance-id',required=True)
    parser.add_argument('--max-credits',type=int,required=True)
    parser.add_argument('--start-room',type=int,default=19)
    args=parser.parse_args()
    execute(args.allowance_id,args.max_credits,args.start_room)
