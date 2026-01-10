"""Tests for ComfyUI executor."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ceq_worker.comfyui import ComfyUIExecutor, ExecutionResult


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_default_values(self):
        """ExecutionResult should have sensible defaults."""
        result = ExecutionResult()
        assert result.output_paths == []
        assert result.node_timings == {}
        assert result.vram_peak_gb == 0.0
        assert result.model_hash == ""
        assert result.success is True
        assert result.error is None

    def test_with_values(self):
        """ExecutionResult should accept custom values."""
        result = ExecutionResult(
            output_paths=[Path("/tmp/output.png")],
            node_timings={"total": 5.2},
            vram_peak_gb=12.5,
            model_hash="abc123",
            success=True,
            error=None,
        )
        assert len(result.output_paths) == 1
        assert result.vram_peak_gb == 12.5

    def test_error_state(self):
        """ExecutionResult should handle error state."""
        result = ExecutionResult(
            success=False,
            error="Execution timeout",
        )
        assert result.success is False
        assert result.error == "Execution timeout"


class TestComfyUIExecutorInit:
    """Tests for ComfyUIExecutor initialization."""

    def test_init_with_defaults(self):
        """Executor should initialize with provided paths."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/opt/ComfyUI"),
            models_path=Path("/models"),
        )
        assert executor.comfyui_path == Path("/opt/ComfyUI")
        assert executor.models_path == Path("/models")
        assert executor.device == "cuda:0"
        assert executor.port == 8188
        assert executor.base_url == "http://127.0.0.1:8188"

    def test_init_with_custom_port(self):
        """Executor should accept custom port."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/opt/ComfyUI"),
            models_path=Path("/models"),
            port=9999,
        )
        assert executor.port == 9999
        assert executor.base_url == "http://127.0.0.1:9999"

    def test_init_with_custom_device(self):
        """Executor should accept custom device."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/opt/ComfyUI"),
            models_path=Path("/models"),
            device="cuda:1",
        )
        assert executor.device == "cuda:1"


class TestComfyUIExecutorHealth:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_is_healthy_no_client(self):
        """Health check should return False when client not initialized."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/opt/ComfyUI"),
            models_path=Path("/models"),
        )
        result = await executor._is_healthy()
        assert result is False

    @pytest.mark.asyncio
    async def test_is_healthy_success(self):
        """Health check should return True when server responds."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/opt/ComfyUI"),
            models_path=Path("/models"),
        )

        mock_response = MagicMock()
        mock_response.status_code = 200

        executor._client = AsyncMock()
        executor._client.get = AsyncMock(return_value=mock_response)

        result = await executor._is_healthy()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_healthy_failure(self):
        """Health check should return False when server fails."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/opt/ComfyUI"),
            models_path=Path("/models"),
        )

        executor._client = AsyncMock()
        executor._client.get = AsyncMock(side_effect=Exception("Connection refused"))

        result = await executor._is_healthy()
        assert result is False


class TestComfyUIExecutorExecution:
    """Tests for workflow execution."""

    @pytest.mark.asyncio
    async def test_execute_not_initialized(self):
        """Execute should raise error when not initialized."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/opt/ComfyUI"),
            models_path=Path("/models"),
        )

        with pytest.raises(RuntimeError, match="not initialized"):
            await executor.execute({}, "test-job")

    @pytest.mark.asyncio
    async def test_execute_success(self, sample_workflow_json):
        """Execute should return result on success."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/tmp/ComfyUI"),
            models_path=Path("/models"),
        )

        # Mock client
        mock_client = AsyncMock()
        executor._client = mock_client

        # Mock prompt submission
        prompt_response = MagicMock()
        prompt_response.status_code = 200
        prompt_response.raise_for_status = MagicMock()
        prompt_response.json.return_value = {"prompt_id": "test-prompt-123"}

        # Mock history check (execution complete)
        history_response = MagicMock()
        history_response.status_code = 200
        history_response.json.return_value = {
            "test-prompt-123": {
                "outputs": {},
                "execution_time": 5.2,
            }
        }

        # Mock system stats for VRAM
        stats_response = MagicMock()
        stats_response.status_code = 200
        stats_response.json.return_value = {
            "devices": [{"vram_used": 12 * 1024 ** 3}]
        }

        mock_client.post = AsyncMock(return_value=prompt_response)
        mock_client.get = AsyncMock(side_effect=[history_response, stats_response])

        result = await executor.execute(sample_workflow_json, "test-job", timeout=10)

        assert result.success is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_timeout(self, sample_workflow_json):
        """Execute should handle timeout."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/tmp/ComfyUI"),
            models_path=Path("/models"),
        )

        mock_client = AsyncMock()
        executor._client = mock_client

        # Mock prompt submission
        prompt_response = MagicMock()
        prompt_response.status_code = 200
        prompt_response.raise_for_status = MagicMock()
        prompt_response.json.return_value = {"prompt_id": "test-prompt-123"}

        # Mock history check (never complete - will timeout)
        history_response = MagicMock()
        history_response.status_code = 200
        history_response.json.return_value = {}  # Empty - not complete

        # Mock queue check
        queue_response = MagicMock()
        queue_response.status_code = 200
        queue_response.json.return_value = {"queue_running": []}

        # Mock interrupt
        interrupt_response = MagicMock()
        interrupt_response.status_code = 200

        mock_client.post = AsyncMock(side_effect=[prompt_response, interrupt_response])
        mock_client.get = AsyncMock(return_value=history_response)

        result = await executor.execute(sample_workflow_json, "test-job", timeout=0.1)

        assert result.success is False
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_with_progress_callback(self, sample_workflow_json):
        """Execute should call progress callback during execution."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/tmp/ComfyUI"),
            models_path=Path("/models"),
        )

        mock_client = AsyncMock()
        executor._client = mock_client

        # Track progress calls
        progress_calls = []

        def on_progress(data):
            progress_calls.append(data)

        # Mock responses
        prompt_response = MagicMock()
        prompt_response.status_code = 200
        prompt_response.raise_for_status = MagicMock()
        prompt_response.json.return_value = {"prompt_id": "test-prompt-123"}

        # First call: show running, second call: complete
        history_empty = MagicMock()
        history_empty.status_code = 200
        history_empty.json.return_value = {}

        history_complete = MagicMock()
        history_complete.status_code = 200
        history_complete.json.return_value = {
            "test-prompt-123": {"outputs": {}, "execution_time": 1.0}
        }

        queue_response = MagicMock()
        queue_response.status_code = 200
        queue_response.json.return_value = {
            "queue_running": [[0, "test-prompt-123", "KSampler"]]
        }

        stats_response = MagicMock()
        stats_response.status_code = 200
        stats_response.json.return_value = {"devices": [{"vram_used": 0}]}

        mock_client.post = AsyncMock(return_value=prompt_response)
        mock_client.get = AsyncMock(
            side_effect=[history_empty, queue_response, history_complete, stats_response]
        )

        result = await executor.execute(
            sample_workflow_json,
            "test-job",
            timeout=10,
            on_progress=on_progress,
        )

        assert result.success is True
        assert len(progress_calls) > 0
        assert progress_calls[0]["node"] == "KSampler"


class TestComfyUIExecutorOutputCollection:
    """Tests for output collection."""

    def test_collect_outputs_empty(self):
        """Should return empty list when no outputs."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/tmp/ComfyUI"),
            models_path=Path("/models"),
        )

        outputs = executor._collect_outputs({}, "test-job")
        assert outputs == []

    def test_collect_outputs_with_images(self, tmp_path):
        """Should collect image outputs."""
        executor = ComfyUIExecutor(
            comfyui_path=tmp_path,
            models_path=Path("/models"),
        )

        # Create output directory and file
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        test_file = output_dir / "test_output.png"
        test_file.write_bytes(b"fake png data")

        outputs_data = {
            "9": {
                "images": [{"filename": "test_output.png"}]
            }
        }

        outputs = executor._collect_outputs(outputs_data, "test-job")

        assert len(outputs) == 1
        assert outputs[0] == test_file

    def test_extract_timings(self):
        """Should extract execution time from history."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/tmp/ComfyUI"),
            models_path=Path("/models"),
        )

        history = {"execution_time": 5.2}
        timings = executor._extract_timings(history)

        assert timings["total"] == 5.2


class TestComfyUIExecutorVRAM:
    """Tests for VRAM monitoring."""

    @pytest.mark.asyncio
    async def test_get_vram_usage_success(self):
        """Should return VRAM usage in GB."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/tmp/ComfyUI"),
            models_path=Path("/models"),
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "devices": [{"vram_used": 12 * 1024 ** 3}]  # 12 GB in bytes
        }

        executor._client = AsyncMock()
        executor._client.get = AsyncMock(return_value=mock_response)

        vram = await executor._get_vram_usage()

        assert vram == 12.0

    @pytest.mark.asyncio
    async def test_get_vram_usage_no_client(self):
        """Should return 0 when client not initialized."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/tmp/ComfyUI"),
            models_path=Path("/models"),
        )

        vram = await executor._get_vram_usage()

        assert vram == 0.0

    @pytest.mark.asyncio
    async def test_get_vram_usage_error(self):
        """Should return 0 on error."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/tmp/ComfyUI"),
            models_path=Path("/models"),
        )

        executor._client = AsyncMock()
        executor._client.get = AsyncMock(side_effect=Exception("Connection error"))

        vram = await executor._get_vram_usage()

        assert vram == 0.0


class TestComfyUIExecutorLifecycle:
    """Tests for executor lifecycle management."""

    @pytest.mark.asyncio
    async def test_shutdown_cleans_up(self):
        """Shutdown should clean up resources."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/tmp/ComfyUI"),
            models_path=Path("/models"),
        )

        # Mock client and process
        mock_client = AsyncMock()
        mock_process = MagicMock()
        mock_process.terminate = MagicMock()
        mock_process.wait = MagicMock()

        executor._client = mock_client
        executor._process = mock_process

        await executor.shutdown()

        # Verify cleanup was called (references saved before shutdown)
        mock_client.aclose.assert_called_once()
        mock_process.terminate.assert_called_once()
        # After shutdown, both should be None
        assert executor._client is None
        assert executor._process is None

    @pytest.mark.asyncio
    async def test_shutdown_no_resources(self):
        """Shutdown should handle no resources gracefully."""
        executor = ComfyUIExecutor(
            comfyui_path=Path("/tmp/ComfyUI"),
            models_path=Path("/models"),
        )

        # Should not raise
        await executor.shutdown()
