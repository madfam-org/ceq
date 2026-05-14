"""Application-level Prometheus metrics for CEQ runtime paths."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

worker_completion_reports_total = Counter(
    "ceq_worker_completion_reports_total",
    "Worker completion reports accepted by the API.",
    ["status"],
)

worker_completion_outputs_total = Counter(
    "ceq_worker_completion_outputs_total",
    "Output descriptors persisted from worker completion reports.",
)

job_cancellations_total = Counter(
    "ceq_job_cancellations_total",
    "Jobs cancelled through the API.",
)

completion_dead_letter_replays_total = Counter(
    "ceq_completion_dead_letter_replays_total",
    "Worker completion dead-letter replay attempts.",
    ["result"],
)

job_webhook_deliveries_total = Counter(
    "ceq_job_webhook_deliveries_total",
    "User job completion webhook delivery outcomes.",
    ["status"],
)

job_webhook_delivery_seconds = Histogram(
    "ceq_job_webhook_delivery_seconds",
    "Total time spent delivering user job completion webhooks.",
)


def record_worker_completion_report(status: str, outputs_persisted: int) -> None:
    """Record a durable worker completion callback."""
    worker_completion_reports_total.labels(status=status).inc()
    if outputs_persisted > 0:
        worker_completion_outputs_total.inc(outputs_persisted)


def record_job_cancellation() -> None:
    """Record a user/API initiated cancellation."""
    job_cancellations_total.inc()


def record_completion_dead_letter_replay(result: str) -> None:
    """Record a dead-letter replay attempt."""
    completion_dead_letter_replays_total.labels(result=result).inc()


def record_job_webhook_delivery(status: str, elapsed_seconds: float) -> None:
    """Record a user webhook delivery outcome."""
    job_webhook_deliveries_total.labels(status=status).inc()
    job_webhook_delivery_seconds.observe(max(0.0, elapsed_seconds))
