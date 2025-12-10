"""
ceq-worker: ComfyUI Workflow Handler

This module implements a Furnace-compatible handler for executing
ComfyUI workflows on GPU workers.

The handler pattern is designed to be compatible with RunPod's serverless
SDK for easy migration.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import redis.asyncio as redis

from ceq_worker.config import get_settings
from ceq_worker.comfyui import ComfyUIExecutor
from ceq_worker.storage import StorageClient

settings = get_settings()


class WorkflowHandler:
    """
    Handles ComfyUI workflow execution.

    This is the core handler that processes jobs from the queue.
    Compatible with Furnace serverless SDK pattern.
    """

    def __init__(self) -> None:
        self.executor = ComfyUIExecutor(
            comfyui_path=settings.comfyui_path,
            models_path=settings.models_path,
            device=settings.gpu_device,
        )
        self.storage = StorageClient()
        self._redis: redis.Redis | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the handler (called once on worker startup)."""
        if self._initialized:
            return

        print("⚡ Initializing ceq-worker...")
        print(f"   ComfyUI path: {settings.comfyui_path}")
        print(f"   Models path: {settings.models_path}")
        print(f"   GPU device: {settings.gpu_device}")

        # Initialize Redis for progress publishing
        self._redis = redis.from_url(
            str(settings.redis_url),
            decode_responses=True,
        )
        await self._redis.ping()
        print("   Redis connected for progress updates")

        # Initialize ComfyUI executor
        await self.executor.initialize()

        # Initialize storage client
        await self.storage.initialize()

        self._initialized = True
        print("✅ Worker initialized. Furnace ignited.")

    async def handler(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Main handler function for workflow execution.
        
        This follows the Furnace/RunPod serverless pattern:
        - event["input"] contains the job input
        - Returns a dict with output data
        
        Args:
            event: Job event containing:
                - input.workflow_json: ComfyUI workflow in API format
                - input.params: Input parameters (prompts, seeds, etc.)
                - input.job_id: Unique job identifier
                - input.webhook_url: Optional callback URL
                
        Returns:
            Dict containing:
                - output_urls: List of generated asset URLs
                - metadata: Execution metadata
                - execution_time: Time taken in seconds
        """
        start_time = time.time()
        job_id = event.get("id", "unknown")
        input_data = event.get("input", {})

        try:
            # Extract workflow and parameters
            workflow_json = input_data.get("workflow_json", {})
            params = input_data.get("params", {})
            
            if not workflow_json:
                return {
                    "error": "Chaos prevails: No workflow provided",
                    "success": False,
                }

            print(f"📥 Processing job {job_id}")
            print(f"   Params: {list(params.keys())}")

            # Apply parameters to workflow
            prepared_workflow = self._apply_params(workflow_json, params)

            # Execute workflow
            async def progress_callback(p: dict[str, Any]) -> None:
                await self._report_progress(job_id, p)

            result = await self.executor.execute(
                workflow=prepared_workflow,
                job_id=job_id,
                timeout=settings.default_timeout,
                on_progress=progress_callback,
            )

            # Upload outputs to R2
            output_urls = []
            for output_path in result.output_paths:
                url = await self.storage.upload_output(
                    local_path=output_path,
                    job_id=job_id,
                )
                output_urls.append(url)

            execution_time = time.time() - start_time

            print(f"✅ Job {job_id} completed in {execution_time:.2f}s")
            print(f"   Outputs: {len(output_urls)}")

            return {
                "success": True,
                "output_urls": output_urls,
                "metadata": {
                    "node_timings": result.node_timings,
                    "vram_peak_gb": result.vram_peak_gb,
                    "model_hash": result.model_hash,
                },
                "execution_time": execution_time,
            }

        except asyncio.TimeoutError:
            return {
                "error": "Chaos won: Execution timeout",
                "success": False,
                "execution_time": time.time() - start_time,
            }
        except Exception as e:
            print(f"❌ Job {job_id} failed: {e}")
            return {
                "error": f"Chaos won this round: {str(e)}",
                "success": False,
                "execution_time": time.time() - start_time,
            }

    def _apply_params(
        self, 
        workflow: dict[str, Any], 
        params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Apply input parameters to workflow nodes.
        
        Parameters are matched to nodes by:
        1. Direct node ID reference (e.g., "3.inputs.text")
        2. Node title/name matching
        3. Input type matching (e.g., all "prompt" inputs)
        """
        # Deep copy to avoid mutating original
        import copy
        prepared = copy.deepcopy(workflow)

        for param_key, param_value in params.items():
            # Handle direct node.input references
            if "." in param_key:
                parts = param_key.split(".")
                node_id = parts[0]
                input_path = parts[1:]
                
                if node_id in prepared:
                    target = prepared[node_id]
                    for key in input_path[:-1]:
                        target = target.get(key, {})
                    if input_path:
                        target[input_path[-1]] = param_value
            else:
                # Search for matching inputs across all nodes
                for node_id, node_data in prepared.items():
                    inputs = node_data.get("inputs", {})
                    if param_key in inputs:
                        inputs[param_key] = param_value

        return prepared

    async def _report_progress(self, job_id: str, progress: dict[str, Any]) -> None:
        """Report progress to Redis pub/sub for real-time updates."""
        print(f"   Progress: {progress.get('node', 'unknown')} - {progress.get('percent', 0)}%")

        if self._redis is None:
            return

        try:
            # Publish progress to Redis channel for WebSocket relay
            progress_data = {
                "job_id": job_id,
                "status": "running",
                "worker_id": settings.worker_id,
                "node": progress.get("node", "unknown"),
                "percent": progress.get("percent", 0),
            }
            await self._redis.publish(
                f"ceq:job:{job_id}:status",
                json.dumps(progress_data),
            )
        except Exception as e:
            print(f"   Warning: Failed to publish progress: {e}")


# Furnace-compatible handler export
handler_instance = WorkflowHandler()


async def handler(event: dict[str, Any]) -> dict[str, Any]:
    """
    Furnace serverless handler function.
    
    This is the entry point called by the Furnace worker runtime.
    Compatible with RunPod's handler pattern.
    """
    await handler_instance.initialize()
    return await handler_instance.handler(event)


# For direct execution / testing
if __name__ == "__main__":
    import furnace  # type: ignore
    
    furnace.serverless.start({
        "handler": handler,
    })
