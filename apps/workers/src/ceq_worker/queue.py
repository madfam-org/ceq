"""
Redis Queue Consumer for ceq-worker.

Listens for jobs from Redis and dispatches to the handler.
"""

import asyncio
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

            # Execute the handler
            result = await handler(job)

            # Store result
            await self._store_result(job_id, result)

            callback_sent = await self._report_completion(job_id, result)
            if not callback_sent:
                print(f"⚠️ Job {job_id} completion callback was not persisted")

            # Update status based on result
            if result.get("success"):
                await self._update_status(job_id, "completed")
                print(f"✅ Job {job_id} completed successfully")
            else:
                await self._update_status(job_id, "failed", result.get("error"))
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

    async def _report_completion(self, job_id: str, result: dict[str, Any]) -> bool:
        """Post final job status and output descriptors back to ceq-api."""
        token = settings.api_job_completion_token
        if not token:
            return False

        status = "completed" if result.get("success") else "failed"
        path = settings.api_job_completion_path.format(job_id=job_id)
        url = f"{settings.api_url.rstrip('/')}/{path.lstrip('/')}"
        payload = {
            "status": status,
            "progress": 1.0 if result.get("success") else 0.0,
            "error": result.get("error"),
            "outputs": [
                {
                    "filename": output["filename"],
                    "storage_uri": output["storage_uri"],
                    "file_type": output["file_type"],
                    "file_size_bytes": output["file_size_bytes"],
                    "width": output.get("width"),
                    "height": output.get("height"),
                    "duration_seconds": output.get("duration_seconds"),
                    "preview_url": output.get("preview_url"),
                    "metadata": {
                        key: value
                        for key, value in output.items()
                        if key not in {
                            "filename",
                            "storage_uri",
                            "file_type",
                            "file_size_bytes",
                            "width",
                            "height",
                            "duration_seconds",
                            "preview_url",
                        }
                    },
                }
                for output in result.get("outputs", [])
            ],
            "metadata": result.get("metadata", {}),
            "worker_id": settings.worker_id,
            "gpu_seconds": result.get("execution_time", 0.0),
        }

        try:
            async with httpx.AsyncClient(
                timeout=settings.api_job_completion_timeout_seconds,
            ) as client:
                response = await client.post(
                    url,
                    headers={"X-CEQ-Worker-Token": token},
                    json=payload,
                )
                response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            if self._redis is not None:
                await self._redis.hset(
                    f"ceq:job:{job_id}",
                    mapping={"callback_error": str(exc)},
                )
            print(f"⚠️ Completion callback failed for {job_id}: {exc}")
            return False

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
