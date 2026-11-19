"""Productions: a small directed graph of jobs (RFC 0061).

A production job waits in the database, not on a queue, until every step it
depends on has completed. ``released_at`` is the line between the two: null
means "waiting on a step", set means "put on the queue of its kind".

Three things happen here and nowhere else:

- ``validate_graph``: the submitted steps form a graph that can run.
- ``release_ready_jobs``: queue every waiting job whose dependencies are done.
  Called on submit (for the roots) and whenever a production job completes.
- ``cancel_dependents``: when a job fails or is cancelled, the steps that
  needed it will never run, so they are cancelled rather than left waiting.

Delivery is at least once. A job is queued after its row is updated but before
the transaction commits; if the commit then fails, a retry queues it again.
A step that runs twice is safe: outputs upsert on ``(job_id, storage_uri)``.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.config import get_settings
from ceq_api.db.redis import enqueue_job
from ceq_api.job_kinds import JobKind
from ceq_api.models.job import Job, JobStatus
from ceq_api.models.output import Output
from ceq_api.models.production import Production

logger = logging.getLogger(__name__)

# Kinds a production may contain. `comfy` is excluded: a ComfyUI job needs a
# workflow and a credit debit, and has its own submit routes.
PRODUCTION_KINDS: frozenset[str] = frozenset(
    kind.value for kind in JobKind if kind is not JobKind.COMFY
)
# Kinds that make a worker open a web page.
CAPTURE_KINDS: frozenset[str] = frozenset(
    {JobKind.CAPTURE_JOURNEY.value, JobKind.CAPTURE_STAGE.value, JobKind.CAPTURE_PAGE.value}
)

TERMINAL = frozenset({JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value})


class GraphError(ValueError):
    """The submitted steps do not form a production that can run."""


def host_allowed(host: str, allowed: list[str]) -> bool:
    """Whether ``host`` is one a capture job may open.

    An entry matches itself. An entry starting with a dot matches any
    subdomain, and not the bare domain: ``.madfam.io`` allows ``cv.madfam.io``.
    """
    host = host.lower().rstrip(".")
    for entry in allowed:
        entry = entry.lower().strip()
        if not entry:
            continue
        if entry.startswith("."):
            if host.endswith(entry) and len(host) > len(entry):
                return True
        elif host == entry:
            return True
    return False


# One DNS label, and a whole host name of at least two labels. Letters, digits
# and hyphens only: no IP literal, no underscore, nothing a browser and Python
# could read differently.
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOSTNAME = re.compile(rf"^(?:{_LABEL}\.)+{_LABEL}$")
# Everything a URL here may be made of. Notably absent: backslash (a browser
# ends the host at one, Python does not), whitespace, control characters and
# anything outside ASCII.
_URL_CHARS = re.compile(r"^[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+$")
# A string that names a resource by scheme ("file:", "concat:", "http://").
# The colon must be followed by something, so prose such as "Intro: hello" is
# not mistaken for one.
_SCHEME_LIKE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:(?=\S)")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def check_capture_url(url: Any, allowed: list[str]) -> str:
    """Return the canonical form of a page a worker may open, or raise ``GraphError``.

    Refused: anything not https, a non-default port, credentials, a host not
    named by the deployment, an IP address, and any character outside the
    plain URL set. The canonical form is rebuilt from the parsed parts, so the
    worker is handed what was checked rather than the string as received.

    This is a check at submit time only. It does not constrain where the page
    redirects or what it loads; a worker that opens pages from inside the
    cluster must enforce the same list on every request it makes.
    """
    if not isinstance(url, str) or not url:
        raise GraphError("a capture step needs params.url")
    if len(url) > 2048 or not _URL_CHARS.match(url):
        raise GraphError("capture url has characters a URL here may not contain")
    try:
        parts = urlsplit(url)
        port = parts.port
        host = (parts.hostname or "").lower().rstrip(".")
    except ValueError:
        raise GraphError("capture url cannot be parsed") from None
    if parts.scheme.lower() != "https":
        raise GraphError("capture url must be https")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise GraphError("capture url must not carry credentials")
    if port not in (None, 443):
        raise GraphError("capture url must use the default https port")
    labels = host.split(".")
    if not _HOSTNAME.match(host) or len(host) > 253 or not re.search("[a-z]", labels[-1]):
        raise GraphError("capture url needs a plain host name")
    if not host_allowed(host, allowed):
        raise GraphError(f"host {host!r} is not one this deployment may capture")
    return urlunsplit(("https", host, parts.path or "/", parts.query, ""))


def check_no_other_locations(value: Any, where: str) -> None:
    """Refuse any string in ``params`` that names a resource by scheme.

    Only ``params.url`` of a capture step is checked against the host list.
    Until each kind has a declared parameter contract, nothing else in
    ``params`` may carry a location a worker might open or read: no
    ``file:``, ``concat:``, ``http://`` or similar, no absolute, home-relative
    or parent-relative path, and no control character, at any depth.
    """
    if isinstance(value, str):
        # Judge the string as a tool would after trimming it.
        text = _CONTROL.sub("", value).strip()
        if (
            text != value.strip()  # carried a control character
            or _SCHEME_LIKE.match(text)
            or "://" in text
            or text.startswith(("/", "\\", "~", ".."))
        ):
            raise GraphError(f"{where} may not carry a location or scheme")
    elif isinstance(value, dict):
        for key, item in value.items():
            check_no_other_locations(key, where)
            check_no_other_locations(item, f"{where}.{key}")
    elif isinstance(value, list):
        for item in value:
            check_no_other_locations(item, where)


def validate_graph(
    steps: list[dict[str, Any]], *, allowed_hosts: list[str], max_jobs: int
) -> list[str]:
    """Check the steps and return their names in an order that respects dependencies.

    A capture step's ``params.url`` is replaced in place by its canonical form.

    Raises ``GraphError`` on: no steps or too many, a repeated name, a kind a
    production may not contain, a dependency on an unknown step or on itself,
    a cycle, or a capture step whose page may not be opened.
    """
    if not steps:
        raise GraphError("a production needs at least one step")
    if len(steps) > max_jobs:
        raise GraphError(f"a production may have at most {max_jobs} steps")

    names = [step["step"] for step in steps]
    if len(set(names)) != len(names):
        raise GraphError("step names must be unique")
    known = set(names)

    for step in steps:
        if step["kind"] not in PRODUCTION_KINDS:
            raise GraphError(
                f"step {step['step']!r}: kind {step['kind']!r} cannot be part of a production"
            )
        deps = step.get("depends_on") or []
        if len(set(deps)) != len(deps):
            raise GraphError(f"step {step['step']!r} lists a dependency twice")
        for dep in deps:
            if dep == step["step"]:
                raise GraphError(f"step {dep!r} depends on itself")
            if dep not in known:
                raise GraphError(f"step {step['step']!r} depends on unknown step {dep!r}")
        params = dict(step.get("params") or {})
        try:
            if step["kind"] in CAPTURE_KINDS:
                canonical = check_capture_url(params.pop("url", None), allowed_hosts)
                check_no_other_locations(params, "params")
                step["params"] = {**params, "url": canonical}
            else:
                check_no_other_locations(params, "params")
        except GraphError as exc:
            raise GraphError(f"step {step['step']!r}: {exc}") from None

    # Kahn's algorithm, keeping submission order among steps that are ready.
    remaining = {step["step"]: set(step.get("depends_on") or []) for step in steps}
    order: list[str] = []
    while remaining:
        ready = [name for name in names if name in remaining and not remaining[name]]
        if not ready:
            raise GraphError(
                "the steps depend on each other in a cycle: " + ", ".join(sorted(remaining))
            )
        for name in ready:
            order.append(name)
            del remaining[name]
        for deps in remaining.values():
            deps.difference_update(ready)
    return order


def production_status(jobs: list[Job]) -> str:
    """The state of a production, read from its jobs."""
    statuses = [job.status for job in jobs]
    if not statuses:
        return JobStatus.QUEUED.value
    if JobStatus.FAILED.value in statuses:
        return JobStatus.FAILED.value
    if JobStatus.CANCELLED.value in statuses:
        return JobStatus.CANCELLED.value
    if all(s == JobStatus.COMPLETED.value for s in statuses):
        return JobStatus.COMPLETED.value
    if any(s in (JobStatus.RUNNING.value, JobStatus.COMPLETED.value) for s in statuses):
        return JobStatus.RUNNING.value
    return JobStatus.QUEUED.value


def in_submitted_order(jobs: list[Job], spec: dict[str, Any] | None) -> list[Job]:
    """The jobs in the order their steps were submitted.

    Jobs of one production are inserted in one transaction and share a
    timestamp, so the submitted graph is the only record of their order.
    """
    names = [step.get("step") for step in (spec or {}).get("steps", [])]
    rank = {name: index for index, name in enumerate(names)}
    return sorted(jobs, key=lambda job: (rank.get(job.step, len(rank)), str(job.id)))


async def lock_production(db: AsyncSession, production_id: UUID) -> dict[str, Any] | None:
    """Take the production's row lock and return its submitted graph.

    Everything that changes a production job's state takes this lock FIRST,
    before it writes any job row, and holds it to the end of the transaction.
    One lock, always taken first, is what keeps two steps finishing at once
    (or a completion racing a cancel) from waiting on each other.
    """
    return (
        await db.execute(
            select(Production.spec).where(Production.id == production_id).with_for_update()
        )
    ).scalar_one_or_none()


async def _production_jobs(db: AsyncSession, production_id: UUID) -> list[Job]:
    """The production's jobs as they are in the database now, under its lock.

    Relies on READ COMMITTED (the PostgreSQL default, and what this API runs
    at): a read made after waiting for the lock sees what the other
    transaction committed.
    """
    spec = await lock_production(db, production_id)
    result = await db.execute(
        select(Job)
        .where(Job.production_id == production_id)
        .execution_options(populate_existing=True)
    )
    return in_submitted_order(list(result.scalars().all()), spec)


async def release_ready_jobs(db: AsyncSession, production_id: UUID) -> list[Job]:
    """Queue every waiting job of the production whose dependencies have completed.

    Each released job's payload carries the outputs of the steps it depends
    on, under ``input.inputs[<step>]``, so a worker needs nothing but its lease.
    """
    jobs = await _production_jobs(db, production_id)
    by_step = {job.step: job for job in jobs}
    ready = [
        job
        for job in jobs
        if job.status == JobStatus.QUEUED.value
        and job.released_at is None
        and all(
            dep in by_step and by_step[dep].status == JobStatus.COMPLETED.value
            for dep in (job.depends_on or [])
        )
    ]
    if not ready:
        return []

    dep_ids = {by_step[dep].id for job in ready for dep in (job.depends_on or [])}
    outputs_by_job: dict[UUID, list[dict[str, Any]]] = {}
    if dep_ids:
        result = await db.execute(
            select(Output).where(Output.job_id.in_(dep_ids)).order_by(Output.filename)
        )
        for output in result.scalars().all():
            # A worker reports its own storage_uri. Only an artifact under the
            # reporting job's own prefix (where the upload route puts it) is
            # handed on, so one worker cannot point the next at something else.
            expected = f"r2://{get_settings().r2_bucket}/outputs/{output.job_id}/"
            if not output.storage_uri.startswith(expected) or ".." in output.storage_uri:
                logger.warning(
                    "Production %s: output %s of job %s is outside the job prefix; not passed on",
                    production_id,
                    output.id,
                    output.job_id,
                )
                continue
            outputs_by_job.setdefault(output.job_id, []).append(
                {
                    "filename": output.filename,
                    "storage_uri": output.storage_uri,
                    "file_type": output.file_type,
                }
            )

    now = datetime.now(UTC)
    payloads: list[dict[str, Any]] = []
    for job in ready:
        job.released_at = now
        payloads.append(
            {
                "id": str(job.id),
                "kind": job.kind,
                "production_id": str(production_id),
                "step": job.step,
                "input": {
                    "job_id": str(job.id),
                    "params": job.input_params or {},
                    "inputs": {
                        dep: outputs_by_job.get(by_step[dep].id, [])
                        for dep in (job.depends_on or [])
                    },
                },
            }
        )
    await db.flush()
    # Queue last, after every row change is written, so a failure here rolls
    # the whole release back instead of leaving half of it applied.
    for payload in payloads:
        await enqueue_job(payload)
    logger.info("Production %s: released %s", production_id, ", ".join(str(j.step) for j in ready))
    return ready


async def cancel_dependents(db: AsyncSession, job: Job) -> list[Job]:
    """Cancel every waiting step that needed ``job``, directly or through another step.

    Only waiting jobs (never released) are touched: a job already on a queue
    or running did not depend on the failed step, or it would not have been
    released.
    """
    if job.production_id is None or job.step is None:
        return []
    jobs = await _production_jobs(db, job.production_id)
    dead = {job.step}
    cancelled: list[Job] = []
    changed = True
    now = datetime.now(UTC)
    while changed:
        changed = False
        for other in jobs:
            if (
                other.step not in dead
                and other.status == JobStatus.QUEUED.value
                and other.released_at is None
                and dead.intersection(other.depends_on or [])
            ):
                needed = sorted(dead.intersection(other.depends_on or []))[0]
                other.status = JobStatus.CANCELLED.value
                other.error = f"Not run: step {needed!r} did not complete."
                other.completed_at = now
                dead.add(other.step)
                cancelled.append(other)
                changed = True
    if cancelled:
        await db.flush()
        logger.info(
            "Production %s: cancelled %s after step %r ended %s",
            job.production_id,
            ", ".join(str(j.step) for j in cancelled),
            job.step,
            job.status,
        )
    return cancelled


async def on_job_finished(db: AsyncSession, job: Job) -> None:
    """Move a production on after one of its jobs reached a terminal state."""
    if job.production_id is None:
        return
    # The jobs are re-read from the database below; write this one's new state
    # first so the re-read does not put the old one back.
    await db.flush()
    if job.status == JobStatus.COMPLETED.value:
        await release_ready_jobs(db, job.production_id)
    elif job.status in (JobStatus.FAILED.value, JobStatus.CANCELLED.value):
        await cancel_dependents(db, job)


async def cancel_production(db: AsyncSession, production_id: UUID) -> list[Job]:
    """Cancel every job of the production that has not finished.

    Returns the jobs that were cancelled. Waiting jobs simply end; a job that
    was already queued or is running is returned so the caller can also pull
    it from its queue and signal its worker.
    """
    jobs = await _production_jobs(db, production_id)
    now = datetime.now(UTC)
    cancelled: list[Job] = []
    for job in jobs:
        if job.status in TERMINAL:
            continue
        job.output_metadata = {
            **(job.output_metadata or {}),
            "cancel_requested_at": now.isoformat(),
            "cancel_requested_from_status": job.status,
        }
        if job.status == JobStatus.QUEUED.value:
            job.completed_at = now
        job.status = JobStatus.CANCELLED.value
        job.error = job.error or "Production cancelled."
        cancelled.append(job)
    if cancelled:
        await db.flush()
    return cancelled
