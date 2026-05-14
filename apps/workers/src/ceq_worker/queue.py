"""
Redis Queue Consumer for ceq-worker.

Listens for jobs from Redis and dispatches to the handler.
"""

import asyncio
import contextlib
import json
import signal
from typing import Any

import httpx
import redis.asyncio as redis

from ceq_worker.config import get_settings
from ceq_worker.handler import handler

settings = get_settings()


class QueueConsumer:
    """
    Redis-based job queue consumer.

    Listens for jobs on the pending queue and processes them
    using the workflow handler.
    """

    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        self._running = False
        self._current_job_id: str | None = None

    async def initialize(self) -> None:
        """Initialize Redis connection."""
        self._redis = redis.from_url(
            str(settings.redis_url),
            decode_responses=True,
        )
        print(f"📡 Connected to Redis: {settings.redis_url}")

    async def run(self) -> None:
        """Main consumer loop - process jobs from queue."""
        if self._redis is None:
            raise RuntimeError("Consumer not initialized")

        self._running = True
        print(f"🔥 Worker {settings.worker_id} listening for jobs...")
        print(f"   Queue: {settings.job_queue_key}")

        while self._running:
            try:
                # Block waiting for a job (BRPOPLPUSH for reliability)
                job_data = await self._redis.brpoplpush(
                    settings.job_queue_key,
                    settings.job_processing_key,
                    timeout=5,  # Check for shutdown every 5s
                )

                if job_data is None:
                    continue

                await self._process_job(job_data)

            except redis.ConnectionError as e:
                print(f"⚠️ Redis connection error: {e}")
                await asyncio.sleep(5)
            except Exception as e:
                print(f"❌ Consumer error: {e}")
                await asyncio.sleep(1)

    async def _process_job(self, job_data: str) -> None:
        """Process a single job."""
        if self._redis is None:
            return

        try:
            job = json.loads(job_data)
            job_id = job.get("id", "unknown")
            self._current_job_id = job_id

            print(f"\n{'='*50}")
            print(f"📥 Processing job: {job_id}")
            print(f"{'='*50}")

            # Update job status to running
            await self._update_status(job_id, "running")

            if await self._is_cancel_requested(job_id):
                result = self._cancelled_result()
            else:
                result = await self._run_handler_with_cancel(job_id, job)

            # Store result
            await self._store_result(job_id, result)

            callback_sent = await self._report_completion(job_id, result)
            if not callback_sent:
                print(f"⚠️ Job {job_id} completion callback was not persisted")

            # Update status based on result
            final_status = self._status_from_result(result)
            if final_status == "completed":
                await self._update_status(job_id, final_status)
                print(f"✅ Job {job_id} completed successfully")
            elif final_status == "cancelled":
                await self._update_status(job_id, final_status, result.get("error"))
                print(f"⏹️ Job {job_id} cancelled")
            else:
                await self._update_status(job_id, final_status, result.get("error"))
                print(f"❌ Job {job_id} failed: {result.get('error')}")

            # Remove from processing queue
            await self._redis.lrem(settings.job_processing_key, 1, job_data)

        except json.JSONDecodeError as e:
            print(f"❌ Invalid job data: {e}")
            await self._redis.lrem(settings.job_processing_key, 1, job_data)
        except Exception as e:
            print(f"❌ Job processing error: {e}")
            # Move back to pending queue for retry
            await self._redis.lpush(settings.job_queue_key, job_data)
            await self._redis.lrem(settings.job_processing_key, 1, job_data)
        finally:
            self._current_job_id = None

    async def _update_status(
        self,
        job_id: str,
        status: str,
        error: str | None = None
    ) -> None:
        """Update job status in Redis."""
        if self._redis is None:
            return

        status_data = {
            "status": status,
            "worker_id": settings.worker_id,
        }
        if error:
            status_data["error"] = error

        await self._redis.hset(
            f"ceq:job:{job_id}",
            mapping=status_data,
        )

        # Publish status update for WebSocket relay
        await self._redis.publish(
            f"ceq:job:{job_id}:status",
            json.dumps(status_data),
        )

    async def _store_result(self, job_id: str, result: dict[str, Any]) -> None:
        """Store job result in Redis."""
        if self._redis is None:
            return

        await self._redis.hset(
            f"ceq:job:{job_id}",
            "result",
            json.dumps(result),
        )

        # Also store in results key for API to query
        await self._redis.lpush(
            settings.job_results_key,
            json.dumps({"job_id": job_id, **result}),
        )

    async def _run_handler_with_cancel(
        self,
        job_id: str,
        job: dict[str, Any],
    ) -> dict[str, Any]:
        """Run a job while listening for active cancellation."""
        handler_task = asyncio.create_task(handler(job))
        cancel_task = asyncio.create_task(self._watch_cancel(job_id))

        try:
            done, _pending = await asyncio.wait(
                {handler_task, cancel_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if cancel_task in done and cancel_task.result():
                handler_task.cancel()
                try:
                    return await handler_task
                except asyncio.CancelledError:
                    return self._cancelled_result()

            return await handler_task
        finally:
            if not cancel_task.done():
                cancel_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await cancel_task

    async def _watch_cancel(self, job_id: str) -> bool:
        """Watch the per-job control channel and Redis status for cancellation."""
        if self._redis is None:
            return False

        channel = f"ceq:job:{job_id}:control"
        pubsub = self._redis.pubsub()

        try:
            await pubsub.subscribe(channel)
            while self._running and self._current_job_id == job_id:
                if await self._is_cancel_requested(job_id):
                    return True

                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if self._is_cancel_message(message):
                    return True

            return False
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(channel)
            with contextlib.suppress(Exception):
                await pubsub.close()

    async def _is_cancel_requested(self, job_id: str) -> bool:
        """Return True when API-side Redis state has requested cancellation."""
        if self._redis is None:
            return False

        try:
            job_state = await self._redis.hgetall(f"ceq:job:{job_id}")
        except Exception as exc:  # noqa: BLE001 - cancellation polling is best effort
            print(f"   Warning: Failed to check cancellation state: {exc}")
            return False

        if not isinstance(job_state, dict):
            return False

        return (
            job_state.get("status") == "cancelled"
            or str(job_state.get("cancel_requested", "")).lower() == "true"
        )

    def _is_cancel_message(self, message: Any) -> bool:
        """Return True when a Redis pub/sub message is a cancel command."""
        if not isinstance(message, dict) or message.get("type") != "message":
            return False

        try:
            payload = json.loads(message.get("data") or "{}")
        except (TypeError, json.JSONDecodeError):
            return False

        return payload.get("action") == "cancel"

    def _cancelled_result(self) -> dict[str, Any]:
        """Build the standard cancelled handler result."""
        return {
            "success": False,
            "cancelled": True,
            "error": "Job cancelled",
            "outputs": [],
            "metadata": {"cancelled": True},
            "execution_time": 0.0,
        }

    def _status_from_result(self, result: dict[str, Any]) -> str:
        """Map handler result shape to the durable job status."""
        if result.get("cancelled"):
            return "cancelled"
        if result.get("success"):
            return "completed"
        return "failed"

    async def _report_completion(self, job_id: str, result: dict[str, Any]) -> bool:
        """Post final job status and output descriptors back to ceq-api."""
        token = settings.api_job_completion_token
        if not token:
            return False

        status = self._status_from_result(result)
        path = settings.api_job_completion_path.format(job_id=job_id)
        url = f"{settings.api_url.rstrip('/')}/{path.lstrip('/')}"
        payload = {
            "status": status,
            "progress": 1.0 if status == "completed" else 0.0,
            "error": result.get("error"),
            "outputs": [self._completion_output_payload(output) for output in result.get("outputs", [])],
            "metadata": {
                **(result.get("metadata", {}) if isinstance(result.get("metadata"), dict) else {}),
                "cancelled": bool(result.get("cancelled")),
            },
            "worker_id": settings.worker_id,
            "gpu_seconds": result.get("execution_time", 0.0),
        }

        max_attempts = max(1, settings.api_job_completion_max_attempts)
        retry_backoff = max(0.0, settings.api_job_completion_retry_backoff_seconds)
        last_error = ""
        last_status_code: int | None = None
        attempts_made = 0

        try:
            async with httpx.AsyncClient(
                timeout=settings.api_job_completion_timeout_seconds,
            ) as client:
                for attempt in range(1, max_attempts + 1):
                    attempts_made = attempt
                    try:
                        response = await client.post(
                            url,
                            headers={"X-CEQ-Worker-Token": token},
                            json=payload,
                        )
                        last_status_code = int(getattr(response, "status_code", 200))
                        if 200 <= last_status_code < 300:
                            return True

                        last_error = f"HTTP {last_status_code}"
                        if not self._should_retry_completion_status(last_status_code):
                            break
                    except httpx.HTTPError as exc:
                        last_error = str(exc)
                        last_status_code = None

                    if attempt < max_attempts and retry_backoff > 0:
                        await asyncio.sleep(retry_backoff * attempt)
        except httpx.HTTPError as exc:
            last_error = str(exc)

        await self._record_completion_dead_letter(
            job_id=job_id,
            url=url,
            payload=payload,
            error=last_error or "Completion callback failed",
            status_code=last_status_code,
            attempts=attempts_made or max_attempts,
        )
        print(f"⚠️ Completion callback failed for {job_id}: {last_error}")
        return False

    def _completion_output_payload(self, output: dict[str, Any]) -> dict[str, Any]:
        """Normalize one worker output descriptor for the API callback."""
        metadata = output.get("metadata") if isinstance(output.get("metadata"), dict) else {}
        metadata = dict(metadata)
        for key, value in output.items():
            if key in {
                "filename",
                "storage_uri",
                "file_type",
                "file_size_bytes",
                "width",
                "height",
                "duration_seconds",
                "preview_url",
                "metadata",
            }:
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

    def _should_retry_completion_status(self, status_code: int) -> bool:
        """Retry transient callback responses only."""
        return status_code >= 500 or status_code in {408, 409, 425, 429}

    async def _record_completion_dead_letter(
        self,
        *,
        job_id: str,
        url: str,
        payload: dict[str, Any],
        error: str,
        status_code: int | None,
        attempts: int,
    ) -> None:
        """Persist an exhausted completion callback for operator inspection."""
        if self._redis is None:
            return

        dead_letter = {
            "job_id": job_id,
            "worker_id": settings.worker_id,
            "url": url,
            "payload": payload,
            "error": error,
            "status_code": status_code,
            "attempts": attempts,
        }
        await self._redis.hset(
            f"ceq:job:{job_id}",
            mapping={
                "callback_error": error,
                "callback_attempts": str(attempts),
                "callback_dead_lettered": "true",
            },
        )
        await self._redis.lpush(
            settings.job_completion_dead_letter_key,
            json.dumps(dead_letter),
        )

    async def stop(self) -> None:
        """Stop the consumer gracefully."""
        print("\n⏹️ Stopping worker...")
        self._running = False

        if self._current_job_id:
            print(f"   Waiting for job {self._current_job_id} to complete...")

        if self._redis:
            await self._redis.close()


async def main() -> None:
    """Main entry point for queue consumer."""
    consumer = QueueConsumer()
    await consumer.initialize()

    # Handle shutdown signals
    loop = asyncio.get_event_loop()

    def signal_handler() -> None:
        asyncio.create_task(consumer.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    await consumer.run()


if __name__ == "__main__":
    asyncio.run(main())
