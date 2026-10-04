"""Prometheus text exposition at GET /metrics (no client library needed).

Counters are per process; for several replicas, scrape each one and sum in Prometheus."""

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.api.common import get_services
from app.services import Services

router = APIRouter(tags=["dashboard"])


def _labels(**labels: str) -> str:
    return "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"


@router.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics(svc: Services = Depends(get_services)) -> str:
    lines = [
        "# HELP agentguard_events_total Audit events by channel, direction and decision.",
        "# TYPE agentguard_events_total counter",
    ]
    for key, value in sorted(svc.counters.items()):
        if key[0] == "events":
            _, channel, direction, decision, monitor_only = key
            lines.append(f"agentguard_events_total{_labels(channel=channel, direction=direction, decision=decision, monitor_only=monitor_only)} {value}")
    lines += ["# HELP agentguard_findings_total Events with at least one finding in this category.", "# TYPE agentguard_findings_total counter"]
    lines += [f"agentguard_findings_total{_labels(category=k[1])} {v}" for k, v in sorted(svc.counters.items()) if k[0] == "findings"]
    lines += ["# HELP agentguard_check_skipped_total Checks skipped by their gate or by a short-circuit.", "# TYPE agentguard_check_skipped_total counter"]
    lines += [f"agentguard_check_skipped_total{_labels(check=k[1])} {v}" for k, v in sorted(svc.counters.items()) if k[0] == "skipped"]
    lines += ["# HELP agentguard_check_latency_ms Latency of checks that ran.", "# TYPE agentguard_check_latency_ms summary"]
    for check in sorted(svc.latency_count):
        lines.append(f"agentguard_check_latency_ms_sum{_labels(check=check)} {svc.latency_sum[check]:.3f}")
        lines.append(f"agentguard_check_latency_ms_count{_labels(check=check)} {svc.latency_count[check]}")
    ml_up = int(bool(svc.ml.classifier and svc.ml.classifier.ready))
    lines += [
        "# HELP agentguard_approvals_pending Tool calls waiting for a human.",
        "# TYPE agentguard_approvals_pending gauge",
        f"agentguard_approvals_pending {len(svc.approvals.list('pending'))}",
        "# HELP agentguard_signatures Signatures in the active feed.",
        "# TYPE agentguard_signatures gauge",
        f"agentguard_signatures{_labels(feed_version=svc.feed.version)} {svc.feed.count}",
        "# HELP agentguard_ml_loaded 1 when the injection classifier is loaded.",
        "# TYPE agentguard_ml_loaded gauge",
        f"agentguard_ml_loaded {ml_up}",
        "# HELP agentguard_policy_info Active policy version.",
        "# TYPE agentguard_policy_info gauge",
        f"agentguard_policy_info{_labels(version=svc.policy.current().version)} 1",
    ]
    return "\n".join(lines) + "\n"
