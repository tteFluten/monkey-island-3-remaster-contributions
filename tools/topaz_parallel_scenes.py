#!/usr/bin/env python3
"""Two scene workers with disjoint, frozen credit reservations and journals."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import time

from asset_batch_groups import group_batches
from asset_batches import report
from install_asset_drafts import install
from quiver_cannon import atomic, locked
from topaz_batch import API
from topaz_character_cutouts import run, digest, load_jobs
from topaz_scenes import ROOT, OUTPUT, read, prepare_scene, materialize
from topaz_allowance import Allowance, regular_batches

# Recovery cases are held without repurchase while other source groups continue.
RECOVERY = {'failed', 'unknown', 'submitting'}
TERMINAL = {'validated', 'accepted', 'rejected'} | RECOVERY


def allocate(balance, requests):
    """Reserve a non-overlapping slice of available credits for each room."""
    if not math.isfinite(balance) or balance < 0:
        raise ValueError('Invalid balance')
    result = {}
    for room, amount in requests:
        if room in result or not math.isfinite(amount) or amount < 0:
            raise ValueError('Invalid or duplicate room reservation')
        result[room] = min(balance, amount)
        balance -= result[room]
    return result


def validate_membership(groups_by_room):
    seen = set()
    for groups in groups_by_room.values():
        for group in groups:
            for source in group['sources']:
                if source in seen:
                    raise ValueError('A source belongs to more than one worker/group')
                seen.add(source)


def cost(base, sources):
    # A timed-out submission may have been billed without returning a job ID.
    # Keep its estimate reserved as well as all confirmed journal charges.
    jobs = read(base/'jobs.json', {})
    return sum(sum(h['estimate']['credits'] for h in j.get('history', [])) +
               (j['estimate']['credits'] if j.get('state') in ('unknown', 'submitting') else 0)
               for s, j in jobs.items() if s in sources)


def execute(rooms, output=OUTPUT, local=ROOT/'.playtest', max_credits=None, allowance_id=None):
    if len(rooms) != 2 or len(set(rooms)) != 2:
        raise ValueError('Select exactly two distinct rooms')
    if max_credits is not None and (not math.isfinite(max_credits) or max_credits < 0):
        raise ValueError('Invalid continuation credit ceiling')
    folder = output/'batches'/('parallel-' + '-'.join(f'{r:04}' for r in rooms))
    allowance = Allowance(output, allowance_id) if allowance_id else None
    if allowance:
        folder = allowance.folder/folder.name
    marker = output/'stop-after-current'
    with ExitStack() as locks:
        # Excludes legacy scene runners for the entire paired invocation.
        for path in (output, output/'batches', folder):
            locks.enter_context(locked(path))
        if allowance:
            allowance.validate()
            if any(r not in allowance.data['membership']['rooms'] for r in rooms):
                raise ValueError('Room outside allowance membership')
        if marker.exists():
            raise RuntimeError('Stop marker present')
        plan = read(output/'plan.json'); units = read(output/'batches/plan.json')
        if units['scene_plan_sha256'] != digest(output/'plan.json'):
            raise ValueError('Scene plan changed')
        if plan['source_manifest_sha256'] != digest(Path(plan['source_batch'])/'manifest.json'):
            raise ValueError('Source manifest changed')
        api = API(ROOT/'.context/secrets/topaz-api-key', 4)
        specs = {}; groups_by_room = {}; requests = []
        for room in rooms:
            base = output/f'room-{room:04}'
            production = output/'batches'/f'room-{room:04}-production'
            for path in (base, production, production/'large-worker'):
                locks.enter_context(locked(path))
            if (base/'stop-after-current').exists():
                raise RuntimeError(f'Room {room} stop marker present')
            selected = [b for b in units['batches'] if b['room'] == room and b['phase'] == 'process']
            if allowance:selected=regular_batches(plan,selected)
            if not selected:
                raise ValueError(f'No regular work for room {room}')
            groups = group_batches(selected, 100); groups_by_room[room] = groups
            sources = {s for g in groups for s in g['sources']}
            membership = dict(room=room, batch_size=100, total_sources=len(sources), groups=groups)
            budget_folder = allowance.folder/production.name if allowance else production
            previous = read(budget_folder/'large-plan.json')
            if previous and previous != membership:
                raise ValueError('Frozen source membership changed')
            atomic(budget_folder/'large-plan.json', membership)
            scene = next(s for s in plan['scenes'] if s['room'] == room)
            prepare_scene(output, scene, Path(plan['source_batch']))
            paid = cost(base, sources)
            budget_path = budget_folder/'budget.json'
            budget = read(budget_path)
            if budget and set(budget['sources']) != sources:
                raise ValueError('Frozen budget membership changed')
            if not budget:
                budget = dict(ceiling=sum(b['planning_minimum_credits'] for b in selected),
                              initial_cost=paid, sources=sorted(sources))
                atomic(budget_path, budget)
            requests.append((room, max(0, budget['ceiling'] - (paid-budget['initial_cost']))))
            specs[room] = dict(base=base, production=production, sources=sources, budget=budget, groups=groups)
        validate_membership(groups_by_room)
        reservation = read(folder/'budget.json')
        if not reservation:
            balance = api.balance()
            if allowance:
                balance = min(balance, allowance.remaining())
            if max_credits is not None:
                balance = min(balance, max_credits)
            allowances = allocate(balance, requests)
            reservation = dict(starting_balance=balance, created_at=time.time(), rooms={str(r):
                dict(ceiling=allowances[r], initial_cost=cost(specs[r]['base'], specs[r]['sources'])) for r in rooms})
            atomic(folder/'budget.json', reservation)
        if set(reservation['rooms']) != {str(r) for r in rooms}:
            raise ValueError('Reservation membership changed')
        # Re-entering after another phase spent credits must not resurrect old
        # reservations. These invocation slices are disjoint and never expand.
        invocation_costs = {r: cost(specs[r]['base'], specs[r]['sources']) for r in rooms}
        invocation_limits = None
        if allowance:
            available = min(allowance.remaining(), api.balance())
            if max_credits is not None:
                available = min(available, max_credits)
            invocation_limits = allocate(available, [(r, max(0,
                reservation['rooms'][str(r)]['ceiling'] -
                (invocation_costs[r]-reservation['rooms'][str(r)]['initial_cost']))) for r in rooms])
        checkpoint = threading.Lock(); states = {}
        def publish(room, state, **details):
            with checkpoint:
                spec = specs[room]
                value = dict(state=state, pid=os.getpid(), room=room, concurrency=16,
                             source_count=len(spec['sources']), credits=cost(spec['base'],spec['sources'])-spec['budget']['initial_cost'],
                             ceiling=spec['budget']['ceiling'], updated_at=time.time(), **details)
                if allowance:value['allowance_id']=allowance.id
                states[str(room)] = value
                atomic(spec['production']/'progress.json', value)
                atomic(folder/'progress.json', dict(pid=os.getpid(), rooms=states, updated_at=time.time()))
        def worker(room):
            spec = specs[room]; base=spec['base']; budget=spec['budget']; sources=spec['sources']
            reserved=reservation['rooms'][str(room)]
            client=API(ROOT/'.context/secrets/topaz-api-key',4)
            try:
                for group in spec['groups']:
                    if marker.exists() or (base/'stop-after-current').exists():
                        publish(room,'stopped');return
                    jobs=read(base/'jobs.json', {})
                    if all(jobs.get(s,{}).get('state') in TERMINAL for s in group['sources']):
                        continue
                    paid=cost(base,sources)
                    remaining=max(0,min(budget['ceiling']-(paid-budget['initial_cost']),
                                        reserved['ceiling']-(paid-reserved['initial_cost'])))
                    if invocation_limits is not None:
                        remaining=max(0,min(remaining,invocation_limits[room]-(paid-invocation_costs[room])))
                    publish(room,'running',current_batch=group['id'])
                    print(f"START {group['id']}: 16 slots, {remaining} reserved credits remaining",flush=True)
                    selected_sources=[]
                    for source in group['sources']:
                        job=jobs.get(source,{})
                        # A final-stage job that already exceeded the polling
                        # timeout gets one status check, rather than blocking
                        # every subsequent group for another five minutes.
                        if job.get('state')=='submitted' and job.get('stage')=='matting' and job.get('last_poll_timeout'):
                            status=client.call('/image/v1/status/'+job['process_id'])['status']
                            if status not in ('Completed','Failed','Cancelled'):
                                continue
                        selected_sources.append(source)
                    if selected_sources:
                        run(base,client,remaining,sources=selected_sources,concurrency=16,require_pilots=False,
                            stop_files=(marker,),poll_timeout=300)
                    jobs=load_jobs(base)
                    result=dict(id=group['id'],total=len(group['sources']),
                        counts=dict(Counter(jobs.get(s,{}).get('state','pending') for s in group['sources'])),
                        deferred_failures=[s for s in group['sources'] if jobs.get(s,{}).get('state')=='failed'],
                        deferred_requests=[s for s in group['sources'] if jobs.get(s,{}).get('state') in ('unknown','submitting')],
                        awaiting_provider=[s for s in group['sources'] if jobs.get(s,{}).get('state')=='submitted'],
                        updated_at=time.time())
                    with checkpoint:
                        materialize(output,plan)
                        try:result['installed_new_or_changed']=install(output,local)['new_or_changed']
                        except Exception as error:result['installation_pending']=str(error)
                        report(output,local)
                        atomic(spec['production']/'groups'/group['id']/'handoff.json',result)
                    print('CHECKPOINT',json.dumps(result),flush=True)
                    message=f"{group['id']}: {sum(result['counts'].get(s,0) for s in ('validated','accepted','rejected'))}/{len(group['sources'])} outputs finished."
                    subprocess.run(['osascript','-e','display notification '+json.dumps(message)+' with title "Topaz batch finished"'],capture_output=True,timeout=10)
                    unresolved=[jobs.get(s,{}) for s in group['sources'] if jobs.get(s,{}).get('state') not in TERMINAL]
                    # Only final-stage requests have no future charge to reserve.
                    # Keep their IDs, and let subsequent groups make progress.
                    if unresolved and not all(j.get('state')=='submitted' and j.get('stage')=='matting'
                                              and j.get('last_poll_timeout') for j in unresolved):
                        publish(room,read(base/'progress.json')['state'],current_batch=group['id']);return
                jobs=read(base/'jobs.json', {})
                awaiting=[s for s in sorted(sources) if jobs.get(s,{}).get('state')=='submitted']
                publish(room,'awaiting_provider' if awaiting else 'scene_production_checkpoint',awaiting_provider=awaiting,
                        recovery_sources=[s for s in sorted(sources) if jobs.get(s,{}).get('state') in RECOVERY],
                        note='Provider failures, uncertain requests, and manual cleanup remain separate.')
                print(f'ROOM {room} PRODUCTION CHECKPOINT',flush=True)
            except Exception as error:
                publish(room,'interrupted',error=str(error));raise
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(worker,r) for r in rooms]
            # Wait for both; one failed worker must not kill the other's paid jobs.
            failures=[]
            for future in futures:
                try:future.result()
                except Exception as error:failures.append(str(error))
            if failures:raise RuntimeError('; '.join(failures))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rooms',type=int,nargs=2,required=True)
    args=parser.parse_args();execute(args.rooms)
