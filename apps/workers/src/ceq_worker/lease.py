"""Lease-mode consumer: pull jobs from ceq-api over authenticated HTTPS.

This is the external-GPU-worker path. Instead of connecting to
``ceq:jobs:pending`` — which would require Redis to be reachable from the public
internet, since Vast.ai instances cannot resolve cluster DNS — the worker:

1. mints a short-lived Janua ``client_credentials`` token carrying ``ceq:worker``
2. long-polls ``POST /v1/worker/lease`` for a job
3. heartbeats ``POST /v1/worker/jobs/{id}/heartbeat`` while the GPU runs
4. reports ``/complete`` or ``/fail``

Redis mode (``ceq_worker.queue``) is unchanged and remains the default for
in-cluster workers. ``ceq_worker.__main__``-equivalent entrypoints choose between
them on ``settings.lease_mode_enabled``.

The token is re-minted before expiry rather than on 401: a GPU job can outlive a
token, and discovering that at completion time would mean losing the result.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

import httpx

from ceq_worker.config import get_settings

settings = get_settings()

JobHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ArtifactTooLargeError(RuntimeError):
    """A file is over the size this worker moves. Trying again would not shrink it."""


def _require_https(url: str) -> None:
    """A presigned URL is a credential for one object. It is only ever used over https."""
    if not str(url).startswith("https://"):
        raise RuntimeError("the API returned a transfer URL that is not https")


def _comfy_handler() -> JobHandler:
    """The ComfyUI handler, imported only when a consumer actually needs it.

    Importing it builds the ComfyUI executor and a storage client, which a CPU
    worker has no use for and no dependencies to load.
    """
    from ceq_worker.handler import handler

    return handler


class TokenExpiredError(RuntimeError):
    """The service credentials were rejected by Janua."""


class ServiceTokenProvider:
    """Mints and caches a Janua ``client_credentials`` access token.

    Mirrors the fashion-cabinet -> yantra4d consumer pattern: one confidential
    client, ``grant_type=client_credentials``, scope requested explicitly, and a
    proactive re-mint ``token_refresh_leeway_seconds`` before ``exp`` so no
    request is ever issued with a token that expires in flight.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get_token(self, *, force_refresh: bool = False) -> str:
        """Return a valid access token, minting a new one when needed."""
        async with self._lock:
            now = time.time()
            if (
                not force_refresh
                and self._token is not None
                and now < self._expires_at - settings.token_refresh_leeway_seconds
            ):
                return self._token

            payload: dict[str, str] = {
                "grant_type": "client_credentials",
                "client_id": settings.janua_client_id,
                "client_secret": settings.janua_client_secret,
                "scope": settings.janua_scope,
            }
            if settings.janua_audience:
                payload["audience"] = settings.janua_audience

            response = await self._client.post(
                settings.janua_token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code >= 400:
                raise TokenExpiredError(
                    f"Janua token mint failed: HTTP {response.status_code} "
                    f"{response.text[:200]}"
                )

            body = response.json()
            token = body.get("access_token")
            if not token:
                raise TokenExpiredError("Janua token response carried no access_token")

            expires_in = float(body.get("expires_in") or 3600)
            self._token = str(token)
            self._expires_at = time.time() + expires_in
            print(f"🔑 Minted {settings.janua_scope} token (expires in {expires_in:.0f}s)")
            return self._token


class LeaseConsumer:
    """HTTPS job-lease consumer for external GPU workers."""

    def __init__(
        self,
        handler: JobHandler | None = None,
        capabilities: Sequence[str] | None = None,
    ) -> None:
        """``handler`` runs a leased job; the default is the ComfyUI handler.

        ``capabilities`` are the job kinds this worker asks for. None sends no
        list, which the API reads as ``["comfy"]``: the behaviour of every
        worker that predates job kinds.
        """
        if capabilities is not None and len(capabilities) == 0:
            # An empty list would be sent as no list, which the API reads as
            # ["comfy"]: a worker that asked for nothing would be handed GPU jobs.
            raise ValueError("capabilities may be omitted, but not empty")
        self._handler = handler
        self._capabilities = list(capabilities) if capabilities is not None else None
        self._client: httpx.AsyncClient | None = None
        self._tokens: ServiceTokenProvider | None = None
        self._running = False
        self._current_job_id: str | None = None
        self._cancel_requested = False

    # --- lifecycle -------------------------------------------------------

    async def initialize(self) -> None:
        """Open the HTTP client and mint the first token."""
        if not settings.lease_mode_enabled:
            raise RuntimeError(
                "Lease mode requires CEQ_LEASE_URL, CEQ_WORKER_CLIENT_ID and "
                "CEQ_WORKER_CLIENT_SECRET."
            )

        self._client = httpx.AsyncClient(
            timeout=settings.lease_request_timeout_seconds,
        )
        # Resolved before the first lease: a worker that cannot load its handler
        # must fail at startup, not after it has taken a job.
        if self._handler is None:
            self._handler = _comfy_handler()
        self._tokens = ServiceTokenProvider(self._client)
        await self._tokens.get_token()
        print(f"📡 Lease mode: {settings.lease_url}")
        print(f"   Worker: {settings.worker_id}")

    async def stop(self) -> None:
        """Stop the consumer gracefully."""
        print("\n⏹️ Stopping lease worker...")
        self._running = False
        if self._current_job_id:
            print(f"   Waiting for job {self._current_job_id} to finish...")

    async def close(self) -> None:
        """Release HTTP resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # --- HTTP plumbing ---------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{settings.lease_url.rstrip('/')}/{path.lstrip('/')}"

    async def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        retry_auth: bool = True,
    ) -> httpx.Response:
        """POST with a bearer token, re-minting once on a 401.

        The proactive refresh in ``ServiceTokenProvider`` is the primary
        mechanism; this 401 retry only covers the case where Janua revoked or
        rotated the credential mid-flight.
        """
        if self._client is None or self._tokens is None:
            raise RuntimeError("Consumer not initialized")

        token = await self._tokens.get_token()
        response = await self._client.post(
            self._url(path),
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        if response.status_code == 401 and retry_auth:
            print("   Token rejected (401); re-minting and retrying once")
            await self._tokens.get_token(force_refresh=True)
            return await self._post(path, payload, retry_auth=False)

        return response

    # --- artifacts without storage credentials ---------------------------

    async def upload_artifact(
        self, job_id: str, path: Path, *, content_type: str
    ) -> dict[str, Any]:
        """Upload one file of a leased job through a presigned URL.

        The API authorizes one key under the job's own prefix; the bytes go
        straight to storage. The worker holds no storage credentials.
        """
        if self._client is None:
            raise RuntimeError("Consumer not initialized")
        response = await self._post(
            f"/v1/worker/jobs/{job_id}/upload-url",
            {
                "worker_id": settings.worker_id,
                "filename": path.name,
                "content_type": content_type,
            },
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"upload-url refused for {path.name}: HTTP {response.status_code}"
            )
        grant = response.json()
        size = path.stat().st_size
        if size > settings.max_artifact_bytes:
            raise ArtifactTooLargeError(
                f"{path.name} is {size} bytes, over the {settings.max_artifact_bytes} byte limit"
            )
        _require_https(grant["upload_url"])

        async def chunks():
            with path.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    yield block

        # Streamed, with the length stated: a presigned PUT refuses chunked
        # encoding, and a large export must not be held in memory.
        put = await asyncio.wait_for(
            self._client.put(
                grant["upload_url"],
                content=chunks(),
                # The signature covers the content type; it must match.
                headers={"Content-Type": content_type, "Content-Length": str(size)},
                timeout=settings.artifact_transfer_timeout_seconds,
            ),
            timeout=settings.artifact_transfer_total_seconds,
        )
        if put.status_code >= 400:
            raise RuntimeError(f"upload of {path.name} failed: HTTP {put.status_code}")
        return {
            "filename": path.name,
            "storage_uri": grant["storage_uri"],
            "file_type": content_type,
            "file_size_bytes": size,
        }

    async def download_input(self, job_id: str, storage_uri: str, dest: Path) -> Path:
        """Fetch an output of a step this job depends on, through a presigned URL."""
        if self._client is None:
            raise RuntimeError("Consumer not initialized")
        response = await self._post(
            f"/v1/worker/jobs/{job_id}/download-url",
            {"worker_id": settings.worker_id, "storage_uri": storage_uri},
        )
        if response.status_code >= 400:
            raise RuntimeError(f"download-url refused: HTTP {response.status_code}")
        url = response.json()["download_url"]
        _require_https(url)

        async def fetch() -> None:
            received = 0
            async with self._client.stream(
                "GET", url, timeout=settings.artifact_transfer_timeout_seconds
            ) as stream:
                if stream.status_code >= 400:
                    raise RuntimeError(f"download failed: HTTP {stream.status_code}")
                with dest.open("wb") as out:
                    async for chunk in stream.aiter_bytes():
                        received += len(chunk)
                        if received > settings.max_artifact_bytes:
                            raise ArtifactTooLargeError(
                                f"the input is over the {settings.max_artifact_bytes} byte limit"
                            )
                        out.write(chunk)

        try:
            await asyncio.wait_for(fetch(), timeout=settings.artifact_transfer_total_seconds)
        except BaseException:
            dest.unlink(missing_ok=True)
            raise
        return dest

    # --- main loop -------------------------------------------------------

    async def run(self) -> None:
        """Poll for leases and execute jobs until stopped."""
        self._running = True
        print(f"🔥 Worker {settings.worker_id} leasing jobs over HTTPS...")

        while self._running:
            try:
                leased = await self._lease_one()
                if leased is None:
                    await asyncio.sleep(settings.lease_poll_interval_seconds)
                    continue

                await self._execute_leased(leased)

            except TokenExpiredError as exc:
                # Bad or revoked credentials: no amount of retrying fixes this
                # quickly, so back off hard rather than hammering Janua.
                print(f"❌ Credential error: {exc}")
                await asyncio.sleep(30)
            except httpx.HTTPError as exc:
                print(f"⚠️ Lease transport error: {exc}")
                await asyncio.sleep(settings.lease_poll_interval_seconds)
            except Exception as exc:  # noqa: BLE001 - loop must survive anything
                print(f"❌ Lease loop error: {exc}")
                await asyncio.sleep(settings.lease_poll_interval_seconds)

    async def _lease_one(self) -> dict[str, Any] | None:
        """Claim one job, or None when the queue is empty."""
        body: dict[str, Any] = {
            "worker_id": settings.worker_id,
            "ttl_seconds": settings.lease_ttl_seconds,
        }
        if self._capabilities:
            body["capabilities"] = self._capabilities
        response = await self._post("/v1/worker/lease", body)

        # 204 is the normal empty-queue answer, not an error.
        if response.status_code == 204:
            return None

        if response.status_code == 403:
            raise TokenExpiredError(
                "Worker token lacks the required scope "
                f"({settings.janua_scope}); check the Janua client grant."
            )

        if response.status_code >= 400:
            raise httpx.HTTPError(
                f"lease failed: HTTP {response.status_code} {response.text[:200]}"
            )

        body = response.json()
        return body if isinstance(body, dict) and body.get("job_id") else None

    async def _execute_leased(self, leased: dict[str, Any]) -> None:
        """Run one leased job to completion, heartbeating throughout."""
        job_id = str(leased["job_id"])
        payload = leased.get("payload") or {}
        attempt = leased.get("attempt", 1)

        self._current_job_id = job_id
        self._cancel_requested = False

        print(f"\n{'='*50}")
        print(f"📥 Leased job: {job_id} (attempt {attempt})")
        print(f"{'='*50}")

        interval = int(
            leased.get("heartbeat_interval_seconds")
            or settings.lease_heartbeat_interval_seconds
        )

        start = time.time()
        if self._handler is None:
            raise RuntimeError("Consumer not initialized")
        handler_task = asyncio.create_task(self._handler({"id": job_id, **payload}))
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(job_id, interval))

        try:
            done, _pending = await asyncio.wait(
                {handler_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            # The heartbeat loop finishing first means the lease was lost or the
            # job was cancelled — either way this worker must stop.
            if heartbeat_task in done and handler_task not in done:
                handler_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await handler_task

                if self._cancel_requested:
                    await self._report_fail(
                        job_id,
                        error="Job cancelled",
                        retryable=False,
                        cancelled=True,
                        gpu_seconds=time.time() - start,
                    )
                else:
                    # Lease lost: the API has already requeued the job, so do
                    # NOT report — another worker owns it now.
                    print(f"⚠️ Lease lost for {job_id}; abandoning without report")
                return

            result = await handler_task
            await self._report_result(job_id, result, time.time() - start)

        except Exception as exc:  # noqa: BLE001 - always report, never hang the lease
            print(f"❌ Job {job_id} raised: {exc}")
            await self._report_fail(
                job_id,
                error=str(exc),
                retryable=True,
                gpu_seconds=time.time() - start,
            )
        finally:
            if not heartbeat_task.done():
                heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat_task
            self._current_job_id = None

    async def _heartbeat_loop(self, job_id: str, interval: int) -> None:
        """Extend the lease until the job ends, the lease is lost, or cancel.

        Returning from this coroutine is the signal to abandon the job: either
        ``self._cancel_requested`` is set (user cancelled) or the lease is gone
        (409 — it expired and someone else re-claimed it).
        """
        while self._running:
            await asyncio.sleep(interval)

            try:
                response = await self._post(
                    f"/v1/worker/jobs/{job_id}/heartbeat",
                    {"worker_id": settings.worker_id},
                )
            except httpx.HTTPError as exc:
                # A transient network blip is survivable — the visibility
                # timeout has room for a missed beat by design.
                print(f"   ⚠️ Heartbeat transport error for {job_id}: {exc}")
                continue

            if response.status_code == 409:
                print(f"   ⚠️ Lease for {job_id} no longer held")
                return

            if response.status_code >= 400:
                print(f"   ⚠️ Heartbeat rejected: HTTP {response.status_code}")
                continue

            body = response.json()
            if body.get("cancel_requested"):
                print(f"   ⏹️ Cancel requested for {job_id}")
                self._cancel_requested = True
                return

    # --- reporting -------------------------------------------------------

    async def _report_result(
        self,
        job_id: str,
        result: dict[str, Any],
        elapsed: float,
    ) -> None:
        """Translate a handler result into /complete or /fail."""
        if result.get("cancelled"):
            await self._report_fail(
                job_id,
                error=result.get("error") or "Job cancelled",
                retryable=False,
                cancelled=True,
                gpu_seconds=result.get("execution_time", elapsed),
            )
            return

        if not result.get("success"):
            # Execution failures are retryable: a different GPU box may well
            # succeed. The API's attempt budget stops this cycling forever.
            await self._report_fail(
                job_id,
                error=result.get("error") or "Execution failed",
                # A handler may say a retry cannot help (bad parameters, a page
                # that may not be opened). Unsaid, it stays retryable.
                retryable=bool(result.get("retryable", True)),
                gpu_seconds=result.get("execution_time", elapsed),
                metadata=result.get("metadata") or {},
            )
            return

        outputs = [
            _completion_output_payload(output)
            for output in result.get("outputs", [])
        ]
        response = await self._post(
            f"/v1/worker/jobs/{job_id}/complete",
            {
                "worker_id": settings.worker_id,
                "outputs": outputs,
                "metadata": result.get("metadata") or {},
                "gpu_seconds": result.get("execution_time", elapsed),
            },
        )

        if response.status_code >= 400:
            print(
                f"⚠️ Completion rejected for {job_id}: "
                f"HTTP {response.status_code} {response.text[:200]}"
            )
        else:
            print(f"✅ Job {job_id} completed ({len(outputs)} outputs)")

    async def _report_fail(
        self,
        job_id: str,
        *,
        error: str,
        retryable: bool,
        cancelled: bool = False,
        gpu_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Report a failure so the API can requeue or retire the job."""
        try:
            response = await self._post(
                f"/v1/worker/jobs/{job_id}/fail",
                {
                    "worker_id": settings.worker_id,
                    "error": error[:4000],
                    "retryable": retryable,
                    "cancelled": cancelled,
                    "metadata": metadata or {},
                    "gpu_seconds": gpu_seconds,
                },
            )
            if response.status_code >= 400:
                print(
                    f"⚠️ Failure report rejected for {job_id}: "
                    f"HTTP {response.status_code}"
                )
            else:
                body = response.json()
                verb = "requeued" if body.get("requeued") else "retired"
                print(f"❌ Job {job_id} {verb}: {error}")
        except httpx.HTTPError as exc:
            # Nothing more to do — the lease will expire and the reaper will
            # recover the job. This is exactly what the visibility timeout is
            # for.
            print(f"⚠️ Could not report failure for {job_id}: {exc}")


def _completion_output_payload(output: dict[str, Any]) -> dict[str, Any]:
    """Normalize a worker output descriptor for the lease completion payload.

    Same normalization the Redis path applies in ``queue.QueueConsumer``: known
    columns map to fields, everything else folds into ``metadata`` so no worker
    detail is silently dropped.
    """
    known = {
        "filename",
        "storage_uri",
        "file_type",
        "file_size_bytes",
        "width",
        "height",
        "duration_seconds",
        "preview_url",
        "metadata",
    }
    metadata = output.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    for key, value in output.items():
        if key in known:
            continue
        if value is not None:
            metadata[key] = value

    return {
        "filename": output["filename"],
        "storage_uri": output["storage_uri"],
        "file_type": output["file_type"],
        "file_size_bytes": output["file_size_bytes"],
        "width": output.get("width"),
        "height": output.get("height"),
        "duration_seconds": output.get("duration_seconds"),
        "preview_url": output.get("preview_url"),
        "metadata": metadata,
    }


async def main() -> None:
    """Entry point for the lease-mode consumer."""
    consumer = LeaseConsumer()
    await consumer.initialize()

    loop = asyncio.get_event_loop()

    def signal_handler() -> None:
        asyncio.create_task(consumer.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, signal_handler)

    try:
        await consumer.run()
    finally:
        await consumer.close()


if __name__ == "__main__":
    asyncio.run(main())
