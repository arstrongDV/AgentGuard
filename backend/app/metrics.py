"""Aggregate audit events into the dashboard's Metrics payload (see api-contract.md)."""

import math
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from app.core.events import AuditEvent
from app.core.ids import iso

WINDOWS = {"15m": (timedelta(minutes=15), timedelta(minutes=1)),
           "1h": (timedelta(hours=1), timedelta(minutes=1)),
           "24h": (timedelta(hours=24), timedelta(minutes=15))}
MAX_EVENTS = 50_000


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, math.ceil(p / 100 * len(ordered)) - 1))
    return round(ordered[rank], 3)


def window_start(window: str, now: datetime) -> datetime:
    return now - WINDOWS[window][0]


def compute_metrics(events: list[AuditEvent], window: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    span, bucket = WINDOWS[window]

    totals = Counter({"requests": 0, "allow": 0, "redact": 0, "block": 0, "needs_approval": 0, "monitor_only": 0, "errors": 0})
    categories: Counter[str] = Counter()
    latencies: dict[str, list[float]] = defaultdict(list)
    tiers: dict[str, int] = {}
    reached_t2 = reached_t3 = 0
    overhead: list[float] = []

    start = now - span
    n_buckets = int(span / bucket)
    series = [{"ts": iso(start + i * bucket), "allow": 0, "redact": 0, "block": 0} for i in range(n_buckets)]

    for e in events:
        if e.direction == "request":
            totals["requests"] += 1
        totals[e.decision.value] += 1
        totals["monitor_only"] += e.monitor_only
        totals["errors"] += e.error is not None
        categories.update({f.category for f in e.findings if f.score > 0})
        ran = [t for t in e.timings if t.skipped_reason is None]
        for t in ran:
            latencies[t.check].append(t.ms)
            tiers[t.check] = t.tier
        reached_t2 += any(t.tier == 2 for t in ran)
        reached_t3 += any(t.tier == 3 for t in ran)
        overhead.append(e.total_ms)

        ts = datetime.fromisoformat(e.ts.replace("Z", "+00:00"))
        index = int((ts - start) / bucket)
        if 0 <= index < n_buckets and e.decision.value in ("allow", "redact", "block"):
            series[index][e.decision.value] += 1

    n = len(events) or 1
    return {
        "window": window,
        "totals": dict(totals),
        "top_categories": [{"category": c, "count": k} for c, k in categories.most_common(8)],
        "latency": sorted(
            ({"check": check, "tier": tiers[check], "p50": percentile(v, 50), "p95": percentile(v, 95), "runs": len(v)}
             for check, v in latencies.items()),
            key=lambda row: (row["tier"], row["check"]),
        ),
        "tier_reach": {"t2_pct": round(100 * reached_t2 / n, 1), "t3_pct": round(100 * reached_t3 / n, 1)},
        "overhead_ms": {"p50": percentile(overhead, 50), "p95": percentile(overhead, 95)},
        "timeseries": series,
    }
