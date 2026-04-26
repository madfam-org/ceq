"""
CEQ Worker Orchestrator

Manages GPU worker instances across providers (Vast.ai, Furnace).
Handles auto-scaling, job routing, and cost optimization.

This is the main entry point for the worker management system.
"""

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import redis.asyncio as redis

from ceq_worker.config import get_settings
from ceq_worker.providers import GPUProvider, get_provider
from ceq_worker.providers.base import GPUTier, InstanceInfo, InstanceSpec, InstanceStatus

settings = get_settings()


@dataclass
class WorkerState:
    """State of a managed worker."""
    instance: InstanceInfo
    last_job_at: datetime | None = None
    jobs_completed: int = 0
    last_health_check: datetime | None = None
    healthy: bool = True
    consecutive_failures: int = 0


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""
    # Provider settings
    primary_provider: str = "vast"
    fallback_provider: str | None = None

    # Scaling
    min_workers: int = 0
    max_workers: int = 5
    target_queue_depth: int = 3
    scale_up_threshold: int = 5
    scale_down_threshold: int = 0

    # Timing
    idle_timeout_seconds: int = 300
    health_check_interval: int = 30
    scale_check_interval: int = 10

    # GPU requirements
    min_vram_gb: float = 16.0
    preferred_gpu_tier: GPUTier = GPUTier.PROSUMER

    # Cost control
    max_hourly_spend: float = 5.0
    prefer_spot: bool = True


class Orchestrator:
    """
    Manages CEQ GPU workers across providers.

    Responsibilities:
    - Auto-scaling based on queue depth
    - Health monitoring and replacement
    - Cost optimization (cheapest available GPU)
    - Graceful shutdown and cleanup
    """

    def __init__(
        self,
        config: OrchestratorConfig | None = None,
        provider: GPUProvider | None = None,
    ) -> None:
        self.config = config or self._load_config()
        self.provider = provider or get_provider(self.config.primary_provider)
        self._fallback_provider: GPUProvider | None = None

        self._redis: redis.Redis | None = None
        self._workers: dict[str, WorkerState] = {}
        self._running = False
        self._lock = asyncio.Lock()

    def _load_config(self) -> OrchestratorConfig:
        """Load orchestrator config from environment."""
        return OrchestratorConfig(
            primary_provider=os.getenv("CEQ_GPU_PROVIDER", "vast"),
            fallback_provider=os.getenv("CEQ_FALLBACK_PROVIDER"),
            min_workers=int(os.getenv("CEQ_MIN_WORKERS", "0")),
            max_workers=int(os.getenv("CEQ_MAX_WORKERS", "5")),
            target_queue_depth=int(os.getenv("CEQ_TARGET_QUEUE", "3")),
            scale_up_threshold=int(os.getenv("CEQ_SCALE_UP_THRESHOLD", "5")),
            scale_down_threshold=int(os.getenv("CEQ_SCALE_DOWN_THRESHOLD", "0")),
            idle_timeout_seconds=int(os.getenv("CEQ_IDLE_TIMEOUT", "300")),
            health_check_interval=int(os.getenv("CEQ_HEALTH_INTERVAL", "30")),
            scale_check_interval=int(os.getenv("CEQ_SCALE_INTERVAL", "10")),
            min_vram_gb=float(os.getenv("CEQ_MIN_VRAM_GB", "16.0")),
            max_hourly_spend=float(os.getenv("CEQ_MAX_HOURLY_SPEND", "5.0")),
        )

    async def initialize(self) -> None:
        """Initialize orchestrator components."""
        print("🎛️ Initializing CEQ Orchestrator...")

        # Connect to Redis
        self._redis = redis.from_url(
            str(settings.redis_url),
            decode_responses=True,
        )
        print(f"   Redis: {settings.redis_url}")

        # Initialize primary provider
        await self.provider.initialize()
        print(f"   Primary provider: {self.config.primary_provider}")

        # Initialize fallback if configured
        if self.config.fallback_provider:
            self._fallback_provider = get_provider(self.config.fallback_provider)
            await self._fallback_provider.initialize()
            print(f"   Fallback provider: {self.config.fallback_provider}")

        # Discover existing workers
        await self._discover_workers()

        print(f"   Discovered workers: {len(self._workers)}")
        print("✅ Orchestrator initialized. Ready to quantize entropy.")

    async def _discover_workers(self) -> None:
        """Discover existing CEQ workers from provider."""
        instances = await self.provider.list_instances(
            labels={"app": "ceq-worker"}
        )

        for instance in instances:
            if instance.status in (InstanceStatus.RUNNING, InstanceStatus.STARTING):
                self._workers[instance.id] = WorkerState(instance=instance)

    async def run(self) -> None:
        """Main orchestrator loop."""
        self._running = True
        print("🔥 Orchestrator running...")

        # Start background tasks
        tasks = [
            asyncio.create_task(self._scale_loop()),
            asyncio.create_task(self._health_loop()),
            asyncio.create_task(self._metrics_loop()),
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            print("⏹️ Orchestrator stopping...")
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop orchestrator and cleanup."""
        self._running = False

        # Graceful shutdown - don't destroy running workers
        print(f"   Active workers: {len(self._workers)}")

        if self._redis:
            await self._redis.close()

    # === Scaling ===

    async def _scale_loop(self) -> None:
        """Periodic scaling check loop."""
        while self._running:
            try:
                await self._check_scale()
            except Exception as e:
                print(f"⚠️ Scale check error: {e}")

            await asyncio.sleep(self.config.scale_check_interval)

    async def _check_scale(self) -> None:
        """Check if scaling is needed based on queue depth."""
        if not self._redis:
            return

        # Get queue depth
        queue_depth = await self._redis.llen(settings.job_queue_key)
        active_workers = len([w for w in self._workers.values() if w.healthy])

        print(f"📊 Queue: {queue_depth} jobs, Workers: {active_workers}")

        # Scale up if needed
        if queue_depth > self.config.scale_up_threshold:
            needed = min(
                (queue_depth // self.config.target_queue_depth) - active_workers,
                self.config.max_workers - len(self._workers),
            )
            if needed > 0:
                await self._scale_up(needed)

        # Scale down if idle
        elif queue_depth <= self.config.scale_down_threshold:
            await self._check_idle_workers()

    async def _scale_up(self, count: int = 1) -> None:
        """Scale up by creating new workers."""
        async with self._lock:
            # Check spending limit
            current_spend = await self._estimate_hourly_spend()
            if current_spend >= self.config.max_hourly_spend:
                print(f"⚠️ Spending limit reached: ${current_spend:.2f}/hr")
                return

            for _ in range(count):
                try:
                    # Find cheapest GPU meeting requirements
                    gpu = await self.provider.find_cheapest_gpu(
                        min_vram_gb=self.config.min_vram_gb,
                        gpu_tier=self.config.preferred_gpu_tier,
                    )

                    if not gpu:
                        print("⚠️ No GPUs available meeting requirements")
                        break

                    print(f"🚀 Scaling up: {gpu['gpu_type']} @ ${gpu['min_price']:.2f}/hr")

                    spec = InstanceSpec(
                        gpu_type=gpu["gpu_type"],
                        gpu_count=1,
                        image=os.getenv("CEQ_WORKER_IMAGE", "ceq/worker:latest"),
                        env_vars={
                            "REDIS_URL": str(settings.redis_url),
                            "R2_ENDPOINT": settings.r2_endpoint,
                            "R2_ACCESS_KEY": settings.r2_access_key,
                            "R2_SECRET_KEY": settings.r2_secret_key,
                            "R2_BUCKET": settings.r2_bucket,
                        },
                        labels={
                            "app": "ceq-worker",
                            "managed-by": "orchestrator",
                            "created-at": datetime.utcnow().isoformat(),
                        },
                    )

                    instance = await self.provider.create_instance(spec)
                    self._workers[instance.id] = WorkerState(instance=instance)

                    print(f"✅ Worker created: {instance.id}")

                except Exception as e:
                    print(f"❌ Failed to scale up: {e}")
                    break

    async def _check_idle_workers(self) -> None:
        """Check for and remove idle workers."""
        now = datetime.utcnow()
        idle_threshold = timedelta(seconds=self.config.idle_timeout_seconds)

        workers_to_remove: list[str] = []

        for worker_id, state in self._workers.items():
            # Keep minimum workers
            if len(self._workers) - len(workers_to_remove) <= self.config.min_workers:
                break

            # Check if idle
            last_activity = state.last_job_at or datetime.utcnow()
            if now - last_activity > idle_threshold:
                workers_to_remove.append(worker_id)

        for worker_id in workers_to_remove:
            await self._remove_worker(worker_id)

    async def _remove_worker(self, worker_id: str) -> None:
        """Remove and destroy a worker."""
        async with self._lock:
            if worker_id not in self._workers:
                return

            print(f"📤 Removing idle worker: {worker_id}")

            try:
                await self.provider.destroy_instance(worker_id)
            except Exception as e:
                print(f"⚠️ Failed to destroy worker: {e}")

            del self._workers[worker_id]

    # === Health Monitoring ===

    async def _health_loop(self) -> None:
        """Periodic health check loop."""
        while self._running:
            try:
                await self._check_health()
            except Exception as e:
                print(f"⚠️ Health check error: {e}")

            await asyncio.sleep(self.config.health_check_interval)

    async def _check_health(self) -> None:
        """Check health of all workers."""
        for worker_id, state in list(self._workers.items()):
            try:
                healthy = await self.provider.is_instance_healthy(worker_id)
                state.healthy = healthy
                state.last_health_check = datetime.utcnow()

                if not healthy:
                    state.consecutive_failures += 1
                    if state.consecutive_failures >= 3:
                        print(f"🔄 Replacing unhealthy worker: {worker_id}")
                        await self._replace_worker(worker_id)
                else:
                    state.consecutive_failures = 0

            except Exception as e:
                print(f"⚠️ Health check failed for {worker_id}: {e}")
                state.consecutive_failures += 1

    async def _replace_worker(self, worker_id: str) -> None:
        """Replace an unhealthy worker."""
        old_state = self._workers.get(worker_id)
        if not old_state:
            return

        # Destroy old worker
        await self._remove_worker(worker_id)

        # Create replacement
        await self._scale_up(1)

    # === Metrics ===

    async def _metrics_loop(self) -> None:
        """Publish metrics to Redis."""
        while self._running:
            try:
                await self._publish_metrics()
            except Exception as e:
                print(f"⚠️ Metrics error: {e}")

            await asyncio.sleep(60)  # Every minute

    async def _publish_metrics(self) -> None:
        """Publish orchestrator metrics."""
        if not self._redis:
            return

        metrics = {
            "timestamp": datetime.utcnow().isoformat(),
            "workers": {
                "total": len(self._workers),
                "healthy": len([w for w in self._workers.values() if w.healthy]),
                "unhealthy": len([w for w in self._workers.values() if not w.healthy]),
            },
            "provider": self.config.primary_provider,
            "spending": await self._estimate_hourly_spend(),
        }

        await self._redis.hset(
            "ceq:orchestrator:metrics",
            mapping={k: json.dumps(v) if isinstance(v, dict) else str(v) for k, v in metrics.items()},
        )

    async def _estimate_hourly_spend(self) -> float:
        """Estimate current hourly spending."""
        total = 0.0
        for state in self._workers.values():
            if state.instance.status == InstanceStatus.RUNNING:
                total += state.instance.price_per_hour
        return total

    # === Public API ===

    async def get_status(self) -> dict[str, Any]:
        """Get orchestrator status."""
        queue_depth = 0
        if self._redis:
            queue_depth = await self._redis.llen(settings.job_queue_key)

        return {
            "running": self._running,
            "provider": self.config.primary_provider,
            "workers": {
                "total": len(self._workers),
                "healthy": len([w for w in self._workers.values() if w.healthy]),
                "ids": list(self._workers.keys()),
            },
            "queue_depth": queue_depth,
            "hourly_spend": await self._estimate_hourly_spend(),
            "config": {
                "min_workers": self.config.min_workers,
                "max_workers": self.config.max_workers,
                "max_hourly_spend": self.config.max_hourly_spend,
            },
        }

    async def force_scale_up(self, count: int = 1) -> list[str]:
        """Force scale up by specified count."""
        initial_count = len(self._workers)
        await self._scale_up(count)
        new_workers = [
            w_id for w_id in self._workers
            if w_id not in list(self._workers.keys())[:initial_count]
        ]
        return new_workers

    async def force_scale_down(self, count: int = 1) -> list[str]:
        """Force scale down by specified count."""
        workers_to_remove = list(self._workers.keys())[:count]
        for worker_id in workers_to_remove:
            await self._remove_worker(worker_id)
        return workers_to_remove


async def main() -> None:
    """Main entry point for orchestrator."""
    import signal

    orchestrator = Orchestrator()
    await orchestrator.initialize()

    loop = asyncio.get_event_loop()

    def signal_handler() -> None:
        asyncio.create_task(orchestrator.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main())
