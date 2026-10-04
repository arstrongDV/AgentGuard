import os
import threading
import time
from datetime import UTC, datetime

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


_last = (0, 0)  # (ms, random) of the previous id
_lock = threading.Lock()


def ulid() -> str:
    """26-char, lexicographically sortable id (ULID: 48-bit ms + 80-bit random).

    Monotonic: ids created in the same millisecond increment the random part, so sorting by id
    always matches creation order (a request event sorts before its response event)."""
    global _last
    with _lock:
        ms = time.time_ns() // 1_000_000
        rand = _last[1] + 1 if ms <= _last[0] else int.from_bytes(os.urandom(10))
        ms = max(ms, _last[0])
        _last = (ms, rand)
    value = ms << 80 | (rand & ((1 << 80) - 1))
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
