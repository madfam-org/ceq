"""Redis-backed job leases for the HTTPS worker surface (``/v1/worker/*``).

Why this exists
---------------
GPU workers run on Vast.ai, **outside** the k3s cluster. Today they consume jobs
by speaking Redis directly, which forces `ceq:jobs:pending` to be published on
the public internet (see ``docs/GPU_COMPUTE_STRATEGY.md``). This module is the
replacement: workers lease jobs over authenticated HTTPS, and Redis stays
cluster-internal.

Interop contract (the important part)
-------------------------------------
Lease-mode workers and legacy in-cluster Redis workers MUST be able to run at the
same time against the same queue without ever double-processing a job. That is
achieved by claiming through the *same* structures ``ceq_worker.queue`` uses:

    ceq:jobs:pending      LIST   job payloads awaiting execution (LPUSH by API)
    ceq:jobs:processing   LIST   payloads currently claimed (in-flight)

A Redis worker claims with ``BRPOPLPUSH pending processing``. This module claims
with ``RPOPLPUSH pending processing`` inside a Lua script. Both are single
atomic Redis operations popping the same tail of the same list, so Redis itself
arbitrates: exactly one claimant wins any given payload. There is no second,
parallel queue for HTTPS workers to race against — that is the whole design.

The lease adds ONE structure the Redis path does not have:

    ceq:jobs:lease:<job_id>   HASH   {payload, worker_id, client_id, expires_at,
                                      attempts, leased_at}
    ceq:jobs:leased           ZSET   job_id -> expires_at (reaper index)

Crash recovery
--------------
A lease is a *visibility timeout*, not a lock held by a live connection. If a
worker dies mid-job — instance preempted, network partitioned, process OOM-killed
— it simply stops heartbeating. Once ``expires_at`` passes, ``reap_expired``
moves the payload from ``processing`` back to ``pending`` atomically and deletes
the lease, making the job claimable again by any worker of either mode. Nothing
needs to detect the crash; the absence of a heartbeat *is* the detection.

Consequences worth stating plainly:

- **At-least-once, not exactly-once.** A worker that finishes the GPU work but
  dies before calling ``/complete`` will have its job re-leased and re-run. Job
  handlers are idempotent at the storage layer (outputs are content-addressed by
  ``storage_uri``, and ``report_job_outputs`` upserts on ``(job_id,
  storage_uri)``), so a re-run overwrites rather than duplicates.
- **A slow worker can lose its lease.** If GPU work outruns the visibility
  timeout without heartbeats, the job is re-queued while the original worker is
  still running it. ``complete``/``fail`` therefore verify lease ownership by
  ``worker_id`` and reject a stale worker's late write (409), so the re-run's
  result is the one that lands.
- **Attempts are capped.** Each requeue increments ``attempts``; past
  ``worker_lease_max_attempts`` the payload is dead-lettered to
  ``ceq:jobs:lease:dead`` instead of cycling forever.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# --- Key space (shares pending/processing with ceq_worker.queue) -------------

PENDING_KEY = "ceq:jobs:pending"
PROCESSING_KEY = "ceq:jobs:processing"
LEASE_INDEX_KEY = "ceq:jobs:leased"
LEASE_DEAD_LETTER_KEY = "ceq:jobs:lease:dead"


def lease_key(job_id: str) -> str:
    """Redis hash key holding the lease record for ``job_id``."""
    return f"ceq:jobs:lease:{job_id}"


# --- Lua scripts -------------------------------------------------------------
#
# Every multi-key mutation below runs as one Lua script so it is atomic against
# concurrent leasers, concurrent reapers, and legacy Redis workers. Scripts are
# invoked with `EVAL` (not `EVALSHA` + cache) because these are low-frequency
# control-plane calls, and EVAL keeps behavior identical under the AsyncMock /
# fakeredis test doubles the repo uses.

# Claim the next pending job.
#
# RPOPLPUSH is the same tail-pop a Redis worker's BRPOPLPUSH performs, so the two
# modes contend on one queue and Redis picks a single winner. We then extract the
# job id from the payload and write the lease. If the payload is unparseable or
# carries no id we still leave it on `processing` and return nil rather than
# silently dropping it — an operator can inspect the list.
#
# KEYS: pending, processing, lease_index
# ARGV: worker_id, client_id, now, expires_at, lease_key_prefix
_CLAIM_LUA = """
local payload = redis.call('RPOPLPUSH', KEYS[1], KEYS[2])
if not payload then
    return nil
end

local ok, job = pcall(cjson.decode, payload)
if not ok or type(job) ~= 'table' then
    return {'', payload, '0'}
end

local job_id = job['id'] or job['job_id']
if job_id == nil then
    local input = job['input']
    if type(input) == 'table' then
        job_id = input['job_id']
    end
end
if job_id == nil then
    return {'', payload, '0'}
end
job_id = tostring(job_id)

local lkey = ARGV[5] .. job_id
-- Carry the attempt counter forward across requeues. A requeued payload keeps
-- its count in the dedicated attempts hash so the retry budget survives the
-- lease record being deleted.
local attempts = tonumber(redis.call('HGET', lkey, 'attempts') or '0') or 0
attempts = attempts + 1

redis.call('HSET', lkey,
    'payload', payload,
    'job_id', job_id,
    'worker_id', ARGV[1],
    'client_id', ARGV[2],
    'leased_at', ARGV[3],
    'expires_at', ARGV[4],
    'attempts', tostring(attempts))
-- Clear any TTL inherited from an attempts-only stub: this is now a LIVE lease,
-- and it must not vanish out from under a running worker. Lease lifetime is
-- governed by `expires_at` + the reaper, never by key expiry.
redis.call('PERSIST', lkey)
redis.call('ZADD', KEYS[3], tonumber(ARGV[4]), job_id)

return {job_id, payload, tostring(attempts)}
"""

# Extend an existing lease. Only the CURRENT lease holder may extend: a worker
# whose lease was already reaped and re-claimed by someone else must be told to
# stop (0), not silently allowed to keep working on a job another worker owns.
#
# KEYS: lease_key, lease_index
# ARGV: worker_id, new_expires_at, job_id
_HEARTBEAT_LUA = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return 0
end
if redis.call('HGET', KEYS[1], 'worker_id') ~= ARGV[1] then
    return -1
end
redis.call('HSET', KEYS[1], 'expires_at', ARGV[2])
redis.call('ZADD', KEYS[2], tonumber(ARGV[2]), ARGV[3])
return 1
"""

# Release a lease terminally (complete, or fail-with-no-retry). Removes the
# payload from `processing` exactly as the Redis worker's LREM does, so the
# in-flight list does not leak entries.
#
# KEYS: lease_key, lease_index, processing
# ARGV: worker_id, job_id
_RELEASE_LUA = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return 0
end
if redis.call('HGET', KEYS[1], 'worker_id') ~= ARGV[1] then
    return -1
end
local payload = redis.call('HGET', KEYS[1], 'payload')
if payload then
    redis.call('LREM', KEYS[3], 1, payload)
end
redis.call('DEL', KEYS[1])
redis.call('ZREM', KEYS[2], ARGV[2])
return 1
"""

# Requeue a leased job: processing -> pending, lease dropped, attempts kept.
# Used both by an explicit /fail with retries remaining and by the reaper.
#
# The attempts counter is preserved by re-writing a stub lease hash holding only
# `attempts`; the next claim reads it, increments, and overwrites the whole hash.
# Without this a job could bounce between workers forever.
#
# The stub is given a TTL because it is not guaranteed to be consumed: if a
# legacy Redis-mode worker drains the requeued payload, the lease API never sees
# that job again and the stub would otherwise sit in the SHARED DB14 keyspace
# forever. The TTL is generously longer than any plausible requeue-to-reclaim
# gap, so it never truncates a live retry budget — it only collects orphans.
#
# KEYS: lease_key, lease_index, processing, pending
# ARGV: worker_id ('' = force, used by the reaper), job_id, attempts, stub_ttl
_REQUEUE_LUA = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return 0
end
if ARGV[1] ~= '' and redis.call('HGET', KEYS[1], 'worker_id') ~= ARGV[1] then
    return -1
end
local payload = redis.call('HGET', KEYS[1], 'payload')
redis.call('DEL', KEYS[1])
redis.call('ZREM', KEYS[2], ARGV[2])
if payload then
    redis.call('LREM', KEYS[3], 1, payload)
    redis.call('LPUSH', KEYS[4], payload)
end
redis.call('HSET', KEYS[1], 'attempts', ARGV[3])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[4]))
return 1
"""

# How long an attempts-only stub survives when nothing re-claims the job.
ATTEMPTS_STUB_TTL_SECONDS = 86_400

# Dead-letter a leased job: drop it from processing WITHOUT returning it to
# pending, and archive the payload for operator inspection.
#
# KEYS: lease_key, lease_index, processing, dead_letter
# ARGV: worker_id ('' = force), job_id, reason, now
_DEAD_LETTER_LUA = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return 0
end
if ARGV[1] ~= '' and redis.call('HGET', KEYS[1], 'worker_id') ~= ARGV[1] then
    return -1
end
local payload = redis.call('HGET', KEYS[1], 'payload')
local attempts = redis.call('HGET', KEYS[1], 'attempts') or '0'
redis.call('DEL', KEYS[1])
redis.call('ZREM', KEYS[2], ARGV[2])
if payload then
    redis.call('LREM', KEYS[3], 1, payload)
    redis.call('LPUSH', KEYS[4], cjson.encode({
        job_id = ARGV[2],
        payload = payload,
        reason = ARGV[3],
        attempts = attempts,
        dead_lettered_at = ARGV[4]
    }))
end
return 1
"""


# --- Result types ------------------------------------------------------------


@dataclass(frozen=True)
class LeasedJob:
    """A job successfully claimed by a worker."""

    job_id: str
    payload: dict[str, Any]
    attempts: int
    expires_at: float


class LeaseOutcome:
    """Return codes shared by the lease mutation helpers.

    ``OK`` the operation applied. ``MISSING`` there is no lease for this job
    (already completed, already reaped, or never leased). ``NOT_OWNER`` a lease
    exists but belongs to a different worker — the caller's lease was reaped and
    the job re-claimed, so the caller must abandon its work.
    """

    OK = "ok"
    MISSING = "missing"
    NOT_OWNER = "not_owner"


def _outcome(raw: Any) -> str:
    """Map a Lua integer return into a :class:`LeaseOutcome` constant."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return LeaseOutcome.MISSING
    if value == 1:
        return LeaseOutcome.OK
    if value == -1:
        return LeaseOutcome.NOT_OWNER
    return LeaseOutcome.MISSING


def _decode(value: Any) -> str:
    """Normalize a Redis reply that may be bytes or str."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return "" if value is None else str(value)


# --- Public operations -------------------------------------------------------


async def claim_next_job(
    redis: Any,
    *,
    worker_id: str,
    client_id: str,
    ttl_seconds: int,
    now: float | None = None,
) -> LeasedJob | None:
    """Atomically claim the next pending job and open a lease on it.

    Returns None when the queue is empty, or when the tail payload was
    unparseable (it is left on ``processing`` for operator inspection rather
    than being handed to a worker that cannot run it).
    """
    now = time.time() if now is None else now
    expires_at = now + ttl_seconds

    result = await redis.eval(
        _CLAIM_LUA,
        3,
        PENDING_KEY,
        PROCESSING_KEY,
        LEASE_INDEX_KEY,
        worker_id,
        client_id,
        f"{now:.3f}",
        f"{expires_at:.3f}",
        "ceq:jobs:lease:",
    )

    if not result:
        return None

    job_id = _decode(result[0])
    raw_payload = _decode(result[1])
    if not job_id:
        logger.warning(
            "Claimed an unidentifiable job payload; left on %s for inspection",
            PROCESSING_KEY,
        )
        return None

    try:
        payload = json.loads(raw_payload)
    except (TypeError, json.JSONDecodeError):
        logger.warning("Leased job %s carried non-JSON payload", job_id)
        return None

    try:
        attempts = int(_decode(result[2]) or "1")
    except ValueError:
        attempts = 1

    return LeasedJob(
        job_id=job_id,
        payload=payload if isinstance(payload, dict) else {},
        attempts=attempts,
        expires_at=expires_at,
    )


async def heartbeat_lease(
    redis: Any,
    *,
    job_id: str,
    worker_id: str,
    ttl_seconds: int,
    max_seconds: int,
    now: float | None = None,
) -> tuple[str, float | None]:
    """Extend a lease by ``ttl_seconds``, bounded by ``max_seconds`` total.

    The ceiling is measured from ``leased_at`` so a wedged-but-heartbeating
    worker cannot hold a job indefinitely: once the cap is hit the heartbeat
    stops extending and the lease is allowed to expire into the reaper.
    """
    now = time.time() if now is None else now
    lkey = lease_key(job_id)

    leased_at_raw = await redis.hget(lkey, "leased_at")
    try:
        leased_at = float(_decode(leased_at_raw))
    except (TypeError, ValueError):
        leased_at = now

    deadline = leased_at + max_seconds
    expires_at = min(now + ttl_seconds, deadline)
    if expires_at <= now:
        # Cap reached — refuse to extend. The reaper will take it.
        logger.warning(
            "Lease for job %s hit the %ss ceiling; refusing further extension",
            job_id,
            max_seconds,
        )
        return LeaseOutcome.MISSING, None

    outcome = _outcome(
        await redis.eval(
            _HEARTBEAT_LUA,
            2,
            lkey,
            LEASE_INDEX_KEY,
            worker_id,
            f"{expires_at:.3f}",
            job_id,
        )
    )
    return outcome, expires_at if outcome == LeaseOutcome.OK else None


async def release_lease(redis: Any, *, job_id: str, worker_id: str) -> str:
    """Terminally close a lease (job finished, no requeue)."""
    return _outcome(
        await redis.eval(
            _RELEASE_LUA,
            3,
            lease_key(job_id),
            LEASE_INDEX_KEY,
            PROCESSING_KEY,
            worker_id,
            job_id,
        )
    )


async def requeue_lease(
    redis: Any,
    *,
    job_id: str,
    worker_id: str,
    attempts: int,
) -> str:
    """Return a leased job to ``pending`` so another worker can retry it.

    Pass ``worker_id=""`` to force (the reaper does this — the owning worker is
    by definition not around to identify itself).
    """
    return _outcome(
        await redis.eval(
            _REQUEUE_LUA,
            4,
            lease_key(job_id),
            LEASE_INDEX_KEY,
            PROCESSING_KEY,
            PENDING_KEY,
            worker_id,
            job_id,
            str(attempts),
            str(ATTEMPTS_STUB_TTL_SECONDS),
        )
    )


async def dead_letter_lease(
    redis: Any,
    *,
    job_id: str,
    worker_id: str,
    reason: str,
    now: float | None = None,
) -> str:
    """Retire a leased job permanently, archiving it for operators."""
    now = time.time() if now is None else now
    return _outcome(
        await redis.eval(
            _DEAD_LETTER_LUA,
            4,
            lease_key(job_id),
            LEASE_INDEX_KEY,
            PROCESSING_KEY,
            LEASE_DEAD_LETTER_KEY,
            worker_id,
            job_id,
            reason,
            f"{now:.3f}",
        )
    )


async def get_lease(redis: Any, job_id: str) -> dict[str, str] | None:
    """Read an OPEN lease record, or None when no worker currently holds one.

    A requeued job leaves behind an attempts-only stub hash (see
    ``_REQUEUE_LUA``) so the retry budget survives the lease being dropped.
    That stub is bookkeeping, not a lease: it has no ``worker_id``, and treating
    it as one would let a worker whose lease was already reaped pass the
    ownership check and land a result for a job someone else now owns.
    """
    raw = await redis.hgetall(lease_key(job_id))
    if not raw:
        return None
    lease = {_decode(k): _decode(v) for k, v in dict(raw).items()}
    if not lease.get("worker_id"):
        return None
    return lease


async def reap_expired(
    redis: Any,
    *,
    max_attempts: int,
    now: float | None = None,
    limit: int = 50,
) -> list[tuple[str, str]]:
    """Return unheartbeated leases to the queue (or dead-letter them).

    This is the crash-recovery mechanism. It is called opportunistically at the
    head of every ``/v1/worker/lease`` request rather than from a background
    timer: a worker asking for work is exactly the moment a recovered job should
    become claimable, and it keeps the API stateless (any replica reaps, no
    leader election, nothing to schedule).

    Returns ``[(job_id, action)]`` where action is ``"requeued"`` or
    ``"dead_lettered"``.
    """
    now = time.time() if now is None else now

    try:
        expired = await redis.zrangebyscore(
            LEASE_INDEX_KEY, "-inf", now, start=0, num=limit
        )
    except Exception as exc:  # noqa: BLE001 - reaping is best-effort
        logger.debug("Unable to scan lease index: %s", exc)
        return []

    if not expired:
        return []

    actions: list[tuple[str, str]] = []
    for raw_job_id in expired:
        job_id = _decode(raw_job_id)
        if not job_id:
            continue

        lease = await get_lease(redis, job_id)
        if lease is None:
            # Lease vanished between the index scan and now (completed in the
            # gap). Drop the stale index entry and move on.
            await redis.zrem(LEASE_INDEX_KEY, job_id)
            continue

        try:
            attempts = int(lease.get("attempts", "0"))
        except ValueError:
            attempts = 0

        if attempts >= max_attempts:
            outcome = await dead_letter_lease(
                redis,
                job_id=job_id,
                worker_id="",
                reason=f"lease expired after {attempts} attempts",
                now=now,
            )
            if outcome == LeaseOutcome.OK:
                actions.append((job_id, "dead_lettered"))
                logger.warning(
                    "Job %s dead-lettered: lease expired on attempt %s of %s",
                    job_id,
                    attempts,
                    max_attempts,
                )
        else:
            outcome = await requeue_lease(
                redis, job_id=job_id, worker_id="", attempts=attempts
            )
            if outcome == LeaseOutcome.OK:
                actions.append((job_id, "requeued"))
                logger.info(
                    "Job %s requeued: lease expired (attempt %s of %s)",
                    job_id,
                    attempts,
                    max_attempts,
                )

    return actions
