import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_hits = defaultdict(deque)


def _prune(q, now, window):
    while q and now - q[0] > window:
        q.popleft()


def check(key, limit, window_seconds):
    """Count one hit. Returns False if the limit is already reached."""
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        _prune(q, now, window_seconds)
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def is_limited(key, limit, window_seconds):
    """Look only, don't count."""
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        _prune(q, now, window_seconds)
        return len(q) >= limit


def record(key):
    with _lock:
        _hits[key].append(time.monotonic())


def reset(key):
    with _lock:
        _hits.pop(key, None)