"""Small replayable change feed shared by local editor windows."""
from collections import deque
import secrets
import threading


class ChangeFeed:
    def __init__(self, capacity=1024):
        self.condition = threading.Condition()
        self.epoch = secrets.token_hex(8)
        self.sequence = 0
        self.events = deque(maxlen=capacity)

    def cursor(self):
        with self.condition:return f'{self.epoch}:{self.sequence}'

    def publish(self, asset, kind='asset'):
        with self.condition:
            self.sequence += 1
            self.events.append((self.sequence, asset, kind))
            self.condition.notify_all()

    def read(self, cursor=None, timeout=15):
        with self.condition:
            try:
                epoch, number = cursor.split(':')
                number = int(number)
            except (AttributeError, ValueError):
                epoch, number = '', -1
            def expired():
                return epoch != self.epoch or number > self.sequence or number < (self.events[0][0]-1 if self.events else 0)
            if not expired() and number == self.sequence:
                self.condition.wait_for(lambda: number != self.sequence, timeout)
            current = f'{self.epoch}:{self.sequence}'
            if expired():
                return dict(cursor=current, reset=True, ids=[])
            if number == self.sequence:
                return None
            events = [event for event in self.events if event[0] > number]
            return dict(cursor=current, ids=list(dict.fromkeys(e[1] for e in events)),
                        kinds=list(dict.fromkeys(e[2] for e in events)))
