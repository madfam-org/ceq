"""
ComfyUI Executor

Headless ComfyUI execution engine for ceq-worker.
Wraps ComfyUI's API for workflow execution without the web UI.
"""

import asyncio
import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of a workflow execution."""
    
    output_paths: list[Path] = field(default_factory=list)
    node_timings: dict[str, float] = field(default_factory=dict)
    vram_peak_gb: float = 0.0
    model_hash: str = ""
    success: bool = True
    error: str | None = None


class ComfyUIExecutor:
    """
    Headless ComfyUI executor.
    
    Manages a ComfyUI server process and executes workflows via its API.
    """

    def __init__(
        self,
        comfyui_path: Path,
        models_path: Path,
        device: str = "cuda:0",
        port: int = 8188,
    ) -> None:
        self.comfyui_path = comfyui_path
        self.models_path = models_path
        self.device = device
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self._process: subprocess.Popen | None = None
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        """Start ComfyUI server if not running."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=300.0)

        # Check if already running
        if await self._is_healthy():
            print("   ComfyUI already running")
            return

        # Start ComfyUI server
        print("   Starting ComfyUI server...")
        await self._start_server()

        # Wait for server to be ready
        for i in range(30):
            if await self._is_healthy():
                print("   ComfyUI server ready")
                return
            await asyncio.sleep(1)

        raise RuntimeError("ComfyUI server failed to start")

    async def _is_healthy(self) -> bool:
        """Check if ComfyUI server is responding."""
        if self._client is None:
            return False
        try:
            response = await self._client.get(f"{self.base_url}/system_stats")
            return response.status_code == 200
        except Exception:
            return False

    async def _start_server(self) -> None:
        """Start ComfyUI server process."""
        cmd = [
            "python",
            str(self.comfyui_path / "main.py"),
            "--listen", "127.0.0.1",
            "--port", str(self.port),
            "--disable-auto-launch",
            "--extra-model-paths-config", str(self.models_path / "extra_model_paths.yaml"),
        ]

        self._process = subprocess.Popen(
            cmd,
            cwd=str(self.comfyui_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    async def execute(
        self,
        workflow: dict[str, Any],
        job_id: str,
        timeout: int = 300,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> ExecutionResult:
        """
        Execute a ComfyUI workflow.
        
        Args:
            workflow: ComfyUI workflow in API format
            job_id: Unique job identifier for output naming
            timeout: Maximum execution time in seconds
            on_progress: Optional callback for progress updates
            
        Returns:
            ExecutionResult with output paths and metadata
        """
        if self._client is None:
            raise RuntimeError("Executor not initialized")

        result = ExecutionResult()
        start_time = time.time()

        try:
            # Submit prompt to queue
            response = await self._client.post(
                f"{self.base_url}/prompt",
                json={
                    "prompt": workflow,
                    "client_id": f"ceq-{job_id}",
                },
            )
            response.raise_for_status()
            
            prompt_data = response.json()
            prompt_id = prompt_data.get("prompt_id")

            if not prompt_id:
                raise RuntimeError("Failed to queue workflow")

            # Poll for completion
            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    raise asyncio.TimeoutError()

                # Check history for completion
                history_response = await self._client.get(
                    f"{self.base_url}/history/{prompt_id}"
                )
                
                if history_response.status_code == 200:
                    history = history_response.json()
                    if prompt_id in history:
                        # Execution complete
                        outputs = history[prompt_id].get("outputs", {})
                        result.output_paths = self._collect_outputs(outputs, job_id)
                        result.node_timings = self._extract_timings(history[prompt_id])
                        break

                # Check queue status
                queue_response = await self._client.get(f"{self.base_url}/queue")
                if queue_response.status_code == 200:
                    queue = queue_response.json()
                    running = queue.get("queue_running", [])
                    
                    # Report progress if we have a callback
                    if on_progress and running:
                        for item in running:
                            if item[1] == prompt_id:
                                on_progress({
                                    "node": item[2] if len(item) > 2 else "unknown",
                                    "percent": 50,  # Approximate
                                })

                await asyncio.sleep(0.5)

            result.vram_peak_gb = await self._get_vram_usage()
            result.success = True

        except asyncio.TimeoutError:
            result.success = False
            result.error = "Execution timeout"
            # Cancel the running prompt
            await self._client.post(f"{self.base_url}/interrupt")
        except Exception as e:
            result.success = False
            result.error = str(e)

        return result

    def _collect_outputs(
        self, 
        outputs: dict[str, Any], 
        job_id: str
    ) -> list[Path]:
        """Collect output file paths from execution results."""
        output_paths: list[Path] = []
        output_dir = self.comfyui_path / "output"

        for node_id, node_outputs in outputs.items():
            images = node_outputs.get("images", [])
            for img in images:
                filename = img.get("filename")
                if filename:
                    path = output_dir / filename
                    if path.exists():
                        output_paths.append(path)

        return output_paths

    def _extract_timings(self, history: dict[str, Any]) -> dict[str, float]:
        """Extract node execution timings from history."""
        timings: dict[str, float] = {}
        # ComfyUI doesn't provide detailed node timings by default
        # This would require custom node instrumentation
        exec_time = history.get("execution_time", 0)
        timings["total"] = exec_time
        return timings

    async def _get_vram_usage(self) -> float:
        """Get current GPU VRAM usage in GB."""
        try:
            if self._client:
                response = await self._client.get(f"{self.base_url}/system_stats")
                if response.status_code == 200:
                    stats = response.json()
                    devices = stats.get("devices", [])
                    if devices:
                        vram_used = devices[0].get("vram_used", 0)
                        return vram_used / (1024 ** 3)  # Convert to GB
        except Exception as e:
            logger.debug(f"Failed to get VRAM usage: {e}")
        return 0.0

    async def shutdown(self) -> None:
        """Shutdown ComfyUI server."""
        if self._client:
            await self._client.aclose()
            self._client = None

        if self._process:
            self._process.terminate()
            self._process.wait(timeout=10)
            self._process = None
