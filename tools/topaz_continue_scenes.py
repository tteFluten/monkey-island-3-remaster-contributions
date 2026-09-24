#!/usr/bin/env python3
"""Continue frozen scene pairs until the starting credit allowance is exhausted."""
import argparse
from collections import defaultdict
import json
import os
import subprocess
import time

from quiver_cannon import atomic, locked
from topaz_batch import API
from topaz_parallel_scenes import cost, execute, TERMINAL
from topaz_scenes import ROOT, OUTPUT, read


def select_rooms(plan, units, start_room):
    """Keep the frozen scene order and process only regular source groups."""
    sources=defaultdict(set)
    for unit in units:
        if unit['phase']=='process':sources[unit['room']].update(unit['sources'])
    order=[s['room'] for s in plan['scenes']]
    return [r for r in order[order.index(start_room):] if sources[r]], sources


def continue_scenes(start_room, wait_pid=None):
    folder=OUTPUT/'batches'/f'continuation-from-{start_room:04}'
    with locked(folder):
        def progress(state, **details):
            atomic(folder/'progress.json',dict(state=state,pid=os.getpid(),updated_at=time.time(),**details))
        if wait_pid:
            progress('waiting_for_predecessor',predecessor_pid=wait_pid)
            while True:
                try:os.kill(wait_pid,0)
                except ProcessLookupError:break
                time.sleep(3)
        if (OUTPUT/'stop-after-current').exists():
            progress('stopped');return
        plan=read(OUTPUT/'plan.json');units=read(OUTPUT/'batches/plan.json')['batches']
        order,sources=select_rooms(plan,units,start_room)
        def total_cost():return sum(cost(OUTPUT/f'room-{r:04}',sources[r]) for r in order)
        def terminal(room):
            jobs=read(OUTPUT/f'room-{room:04}'/'jobs.json',{})
            return all(jobs.get(s,{}).get('state') in TERMINAL for s in sources[room])
        api=API(ROOT/'.context/secrets/topaz-api-key',4)
        budget=read(folder/'budget.json')
        if not budget:
            budget=dict(ceiling=api.balance(),initial_cost=total_cost(),rooms=order,
                        source_fingerprint=read(OUTPUT/'batches/plan.json')['scene_plan_sha256'])
            atomic(folder/'budget.json',budget)
        if budget['rooms']!=order or budget['source_fingerprint']!=read(OUTPUT/'batches/plan.json')['scene_plan_sha256']:
            raise ValueError('Frozen continuation membership changed')
        remaining=lambda:max(0,budget['ceiling']-(total_cost()-budget['initial_cost']))
        pending=[r for r in order if not terminal(r)]
        try:
            while pending:
                if (OUTPUT/'stop-after-current').exists():progress('stopped');return
                if remaining()<1 or api.balance()<1:
                    progress('credit_cap',remaining_credits=remaining(),pending_rooms=pending);return
                rooms=pending[:2]
                if len(rooms)==1:
                    # A completed room is an idle partner; never create new work.
                    partner=next((r for r in order if r!=rooms[0] and terminal(r)),None)
                    if partner is None:raise RuntimeError('No idle partner for final scene')
                    rooms.append(partner)
                progress('running',current_rooms=rooms,remaining_credits=remaining(),pending_rooms=pending)
                print('CONTINUE ROOMS',rooms,'continuation credits remaining',remaining(),flush=True)
                # One invocation owns both workers and all global workflow locks.
                # Any unexpected error stops this continuation; no paid retries.
                execute(rooms,max_credits=remaining())
                states={r:read(OUTPUT/'batches'/f'room-{r:04}-production/progress.json') for r in rooms}
                for r,state in states.items():
                    if state['state'] not in ('scene_production_checkpoint','awaiting_provider'):
                        progress(state['state'],current_rooms=rooms,pending_rooms=pending);return
                    jobs=read(OUTPUT/f'room-{r:04}'/'jobs.json',{})
                    # Only saved final-stage requests may be left behind.
                    if any(jobs.get(s,{}).get('state') not in TERMINAL and not
                           (jobs.get(s,{}).get('state')=='submitted' and jobs[s].get('stage')=='matting')
                           for s in sources[r]):
                        progress('recovery_pending',current_rooms=rooms,pending_rooms=pending);return
                pending=[r for r in pending if r not in rooms]
            progress('production_checkpoint',remaining_credits=remaining(),note='Saved provider jobs and manual cleanup remain separate.')
        except Exception as error:
            progress('interrupted',error=str(error),remaining_credits=remaining());raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--start-room',type=int,required=True)
    p.add_argument('--wait-pid',type=int)
    args=p.parse_args();continue_scenes(args.start_room,args.wait_pid)
