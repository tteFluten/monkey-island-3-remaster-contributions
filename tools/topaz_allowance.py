"""Explicit continuation allowances, separate from historical frozen budgets.

Callers hold the scene workflow lock while creating an allowance or allocating
work. Parallel workers receive disjoint reservations before either can submit.
"""
import math
import re
import time

from quiver_cannon import atomic
from topaz_character_cutouts import digest
from topaz_scenes import read


def charge(job):
    values = [h['estimate']['credits'] for h in job.get('history', [])]
    if job.get('state') in ('unknown', 'submitting'):
        values.append(job['estimate']['credits'])
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
           not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('Invalid journal charge')
    return sum(values)


def regular_batches(plan, units):
    """Only submit ordinary source artwork owned by these scene journals."""
    from topaz_guybrush import costume, EFFECTS
    entries = {e['source']: e for scene in plan['scenes'] for e in scene['sources']}
    result = []
    for unit in units:
        if unit['phase'] != 'process':
            continue
        sources = [s for s in unit['sources']
                   if entries[s]['operation'] in ('upscale-only', 'upscale-matting')
                   and costume(s) not in EFFECTS]
        if sources:
            result.append(dict(unit, sources=sources))
    return result


def membership(output, start_room):
    # Imports are local to avoid a cycle with the coordinators.
    from topaz_guybrush import selection
    from topaz_continue_scenes import select_rooms
    plan = read(output/'plan.json')
    units = read(output/'batches/plan.json')
    fingerprint = digest(output/'plan.json')
    if units['scene_plan_sha256'] != fingerprint:
        raise ValueError('Scene plan changed')
    _, _, owners = selection(plan)
    rooms, sources = select_rooms(plan, regular_batches(plan, units['batches']), start_room)
    owners = dict(owners)
    for room in rooms:
        for source in sources[room]:
            base = f'room-{room:04}'
            if source in owners and owners[source] != base:
                raise ValueError('Conflicting paid source owners')
            owners[source] = base
    grouped = {}
    for source, base in sorted(owners.items()):
        grouped.setdefault(base, []).append(source)
    return dict(scene_plan_sha256=fingerprint,
                batch_plan_sha256=digest(output/'batches/plan.json'),
                start_room=start_room, rooms=rooms, sources=grouped)


class Allowance:
    def __init__(self, output, allowance_id):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', allowance_id):
            raise ValueError('Invalid allowance ID')
        self.output = output
        self.id = allowance_id
        self.folder = output/'batches/allowances'/allowance_id
        self.path = self.folder/'allowance.json'
        self.data = read(self.path)

    def create(self, ceiling, start_room=19):
        if isinstance(ceiling, bool) or not isinstance(ceiling, int) or ceiling <= 0:
            raise ValueError('Allowance must be a positive integer')
        scope = membership(self.output, start_room)
        if self.data:
            if self.data['ceiling'] != ceiling or self.data['membership'] != scope:
                raise ValueError('Existing allowance cannot be increased or repurposed')
            return self
        self.data = dict(version=1, allowance_id=self.id, ceiling=ceiling,
                         created_at=time.time(), membership=scope,
                         authorization='Explicit user continuation allowance')
        self.data['baseline'] = self.charges()
        atomic(self.path, self.data)
        return self

    def validate(self):
        if not self.data:
            raise ValueError('Allowance must be explicitly created before processing')
        if self.data['membership'] != membership(self.output, self.data['membership']['start_room']):
            raise ValueError('Allowance membership changed')
        return self

    def charges(self):
        result = {}
        for base, sources in self.data['membership']['sources'].items():
            jobs = read(self.output/base/'jobs.json', {})
            result[base] = {s: charge(jobs.get(s, {})) for s in sources}
        return result

    def spent(self):
        current = self.charges()
        # Per-source deltas prevent a refund/recovery elsewhere from disguising
        # new spending. Unknown requests remain conservatively charged.
        return sum(max(0, amount-self.data['baseline'][base][source])
                   for base, sources in current.items() for source, amount in sources.items())

    def remaining(self):
        return max(0, self.data['ceiling']-self.spent())

    def summary(self):
        spent = self.spent()
        return dict(allowance_id=self.id, ceiling=self.data['ceiling'],
                    credits=spent, remaining_credits=max(0, self.data['ceiling']-spent))
