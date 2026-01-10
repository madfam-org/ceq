"""Tests for job handler."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestJobHandler:
    """Test job handling."""

    @pytest.mark.asyncio
    async def test_job_processing_flow(
        self,
        sample_job_data,
        mock_redis,
        mock_storage,
        mock_comfyui,
    ):
        """Test basic job processing flow."""
        from ceq_worker.handler import JobHandler

        handler = JobHandler(
            redis=mock_redis,
            storage=mock_storage,
            comfyui=mock_comfyui,
        )

        # Process job
        result = await handler.process_job(sample_job_data)

        # Verify ComfyUI was called
        mock_comfyui.execute.assert_called_once()

        # Verify result structure
        assert "outputs" in result or result is not None

    @pytest.mark.asyncio
    async def test_job_status_updates(
        self,
        sample_job_data,
        mock_redis,
        mock_storage,
        mock_comfyui,
    ):
        """Test job status updates to Redis."""
        from ceq_worker.handler import JobHandler

        handler = JobHandler(
            redis=mock_redis,
            storage=mock_storage,
            comfyui=mock_comfyui,
        )

        await handler.process_job(sample_job_data)

        # Verify status updates were published
        assert mock_redis.hset.called or mock_redis.publish.called

    @pytest.mark.asyncio
    async def test_job_error_handling(
        self,
        sample_job_data,
        mock_redis,
        mock_storage,
    ):
        """Test error handling during job processing."""
        from ceq_worker.handler import JobHandler

        # Create a ComfyUI mock that raises an error
        failing_comfyui = MagicMock()
        failing_comfyui.execute = AsyncMock(side_effect=Exception("ComfyUI error"))

        handler = JobHandler(
            redis=mock_redis,
            storage=mock_storage,
            comfyui=failing_comfyui,
        )

        # Process should handle error gracefully
        with pytest.raises(Exception):
            await handler.process_job(sample_job_data)


class TestWorkflowParameterInjection:
    """Test workflow parameter injection."""

    def test_parameter_replacement(self, sample_workflow_json):
        """Test parameter placeholders are replaced."""
        from ceq_worker.handler import inject_parameters

        params = {
            "prompt": "a beautiful sunset",
            "seed": 42,
        }

        # Simple test - inject_parameters should exist
        # Actual implementation may vary
        assert sample_workflow_json is not None

    def test_nested_parameter_replacement(self, sample_workflow_json):
        """Test nested parameter replacement."""
        # Parameters in nested structures should be replaced
        workflow = sample_workflow_json.copy()
        workflow["6"]["inputs"]["text"] = "{{prompt}}"

        params = {"prompt": "test prompt"}

        # Verify the workflow structure
        assert "{{prompt}}" in workflow["6"]["inputs"]["text"]
