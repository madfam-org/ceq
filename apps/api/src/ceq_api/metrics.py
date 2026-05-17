"""Application-level Prometheus metrics for CEQ runtime paths."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

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

queue_depth = Gauge(
    "ceq_queue_depth",
    "Pending and running job counts in Redis queues.",
    ["queue"],
)

completion_dead_letters = Gauge(
    "ceq_completion_dead_letters",
    "Number of completion callback dead letters buffered in Redis.",
)

running_jobs_stale_1h = Gauge(
    "ceq_running_jobs_stale_1h",
    "Number of running jobs still marked running longer than 1 hour.",
)

alembic_revision_health = Gauge(
    "ceq_alembic_revision_health",
    "Current Alembic revision currently persisted in the DB.",
    ["revision"],
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


def set_queue_depth(*, pending: int, processing: int) -> None:
    """Set Redis queue depth gauges from runtime sampler."""
    queue_depth.labels("pending").set(max(0, int(pending)))
    queue_depth.labels("processing").set(max(0, int(processing)))


def set_completion_dead_letters(count: int) -> None:
    """Set completion dead-letter queue depth."""
    completion_dead_letters.set(max(0, int(count)))


def set_running_jobs_stale_1h(count: int) -> None:
    """Set count of running jobs that have crossed 1h age threshold."""
    running_jobs_stale_1h.set(max(0, int(count)))


def set_alembic_revision_health(revision: str | None) -> None:
    """Record current Alembic revision in Prometheus labels."""
    alembic_revision_health.clear()
    alembic_revision_health.labels(revision=revision or "unknown").set(1)
