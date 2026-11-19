"""The closed set of job kinds and the pending list each kind is queued on.

RFC 0061 (the cinematic production pipeline) gives every job a **kind**. A kind
is also the *capability* a worker declares when it leases: a worker only ever
receives kinds it asked for.

Routing rule (the whole contract, in one place):

- ``comfy`` jobs stay on the original list ``ceq:jobs:pending``. Nothing about
  that list changes, so legacy Redis-mode workers (``BRPOPLPUSH`` on it) and
  HTTPS leasers that send no ``capabilities`` keep working untouched.
- Every other kind has its own list, ``ceq:jobs:pending:<kind>``. A legacy
  Redis worker never looks at those lists, so it can never pop a job it cannot
  run.

This module has no dependencies on purpose: the model, the enqueue helper, the
lease scripts and the worker router all import it.
"""

from __future__ import annotations

from enum import StrEnum

COMFY_PENDING_KEY = "ceq:jobs:pending"


class JobKind(StrEnum):
    """What a job is, and therefore which worker can run it."""

    COMFY = "comfy"
    CAPTURE_JOURNEY = "capture.journey"
    CAPTURE_STAGE = "capture.stage"
    CAPTURE_PAGE = "capture.page"
    EDIT = "edit"
    EXPORT = "export"


DEFAULT_JOB_KIND = JobKind.COMFY.value
JOB_KINDS: tuple[str, ...] = tuple(kind.value for kind in JobKind)


def validate_job_kind(kind: str) -> str:
    """Return ``kind`` if it is in the closed set, else raise ``ValueError``."""
    if kind not in JOB_KINDS:
        raise ValueError(
            f"Unknown job kind {kind!r}; allowed: {', '.join(JOB_KINDS)}"
        )
    return kind


def pending_key_for_kind(kind: str) -> str:
    """The Redis list a job of ``kind`` waits on."""
    validate_job_kind(kind)
    if kind == JobKind.COMFY.value:
        return COMFY_PENDING_KEY
    return f"{COMFY_PENDING_KEY}:{kind}"


ALL_PENDING_KEYS: tuple[str, ...] = tuple(pending_key_for_kind(k) for k in JOB_KINDS)
