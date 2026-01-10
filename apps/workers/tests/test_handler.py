"""Tests for workflow handler."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestWorkflowHandler:
    """Test workflow handling."""

    def test_workflow_handler_import(self):
        """WorkflowHandler should be importable."""
        from ceq_worker.handler import WorkflowHandler

        assert WorkflowHandler is not None

    @pytest.mark.asyncio
    async def test_handler_initialization(self):
        """Test handler initializes with executor and storage."""
        with patch("ceq_worker.handler.ComfyUIExecutor") as mock_executor, \
             patch("ceq_worker.handler.StorageClient") as mock_storage:
            from ceq_worker.handler import WorkflowHandler

            handler = WorkflowHandler()

            assert handler.executor is not None
            assert handler.storage is not None
            assert handler._initialized is False

    @pytest.mark.asyncio
    async def test_handler_function_export(self):
        """Test handler function is exported."""
        from ceq_worker.handler import handler

        assert handler is not None
        assert callable(handler)


class TestApplyParams:
    """Test workflow parameter application."""

    def test_apply_params_direct_reference(self):
        """Test direct node.input parameter replacement."""
        with patch("ceq_worker.handler.ComfyUIExecutor"), \
             patch("ceq_worker.handler.StorageClient"):
            from ceq_worker.handler import WorkflowHandler

            handler = WorkflowHandler()

            workflow = {
                "3": {
                    "inputs": {
                        "text": "original prompt"
                    }
                }
            }

            params = {"3.inputs.text": "new prompt"}

            result = handler._apply_params(workflow, params)

            assert result["3"]["inputs"]["text"] == "new prompt"

    def test_apply_params_by_key_name(self):
        """Test parameter replacement by input key name."""
        with patch("ceq_worker.handler.ComfyUIExecutor"), \
             patch("ceq_worker.handler.StorageClient"):
            from ceq_worker.handler import WorkflowHandler

            handler = WorkflowHandler()

            workflow = {
                "6": {
                    "inputs": {
                        "seed": 12345
                    }
                },
                "9": {
                    "inputs": {
                        "seed": 67890
                    }
                }
            }

            params = {"seed": 42}

            result = handler._apply_params(workflow, params)

            # Should replace seed in all nodes
            assert result["6"]["inputs"]["seed"] == 42
            assert result["9"]["inputs"]["seed"] == 42

    def test_apply_params_does_not_mutate_original(self):
        """Test that original workflow is not mutated."""
        with patch("ceq_worker.handler.ComfyUIExecutor"), \
             patch("ceq_worker.handler.StorageClient"):
            from ceq_worker.handler import WorkflowHandler

            handler = WorkflowHandler()

            workflow = {
                "3": {
                    "inputs": {
                        "text": "original"
                    }
                }
            }

            params = {"text": "new"}

            result = handler._apply_params(workflow, params)

            # Original should be unchanged
            assert workflow["3"]["inputs"]["text"] == "original"
            # Result should have new value
            assert result["3"]["inputs"]["text"] == "new"


class TestHandlerEvent:
    """Test handler event processing."""

    @pytest.mark.asyncio
    async def test_handler_no_workflow_returns_error(self):
        """Test handler returns error when no workflow provided."""
        with patch("ceq_worker.handler.ComfyUIExecutor"), \
             patch("ceq_worker.handler.StorageClient"), \
             patch("ceq_worker.handler.redis"):
            from ceq_worker.handler import WorkflowHandler

            handler = WorkflowHandler()
            handler._initialized = True  # Skip initialization

            event = {
                "id": "test-job-123",
                "input": {}  # No workflow_json
            }

            result = await handler.handler(event)

            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_handler_extracts_params(self):
        """Test handler correctly extracts params from event."""
        with patch("ceq_worker.handler.ComfyUIExecutor") as mock_executor_class, \
             patch("ceq_worker.handler.StorageClient"), \
             patch("ceq_worker.handler.redis"):
            from ceq_worker.handler import WorkflowHandler
            from ceq_worker.comfyui import ExecutionResult

            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=ExecutionResult(
                success=True,
                output_paths=[],
            ))
            mock_executor_class.return_value = mock_executor

            handler = WorkflowHandler()
            handler._initialized = True
            handler._redis = AsyncMock()

            event = {
                "id": "test-job-123",
                "input": {
                    "workflow_json": {"3": {"inputs": {"text": "hello"}}},
                    "params": {"text": "world"}
                }
            }

            result = await handler.handler(event)

            # Executor should have been called
            mock_executor.execute.assert_called_once()

            # Verify params were applied (first arg is workflow)
            call_args = mock_executor.execute.call_args
            prepared_workflow = call_args[1]["workflow"] if "workflow" in call_args[1] else call_args[0][0]
            assert prepared_workflow["3"]["inputs"]["text"] == "world"


class TestProgressReporting:
    """Test progress reporting."""

    @pytest.mark.asyncio
    async def test_report_progress_publishes_to_redis(self):
        """Test progress is published to Redis."""
        with patch("ceq_worker.handler.ComfyUIExecutor"), \
             patch("ceq_worker.handler.StorageClient"):
            from ceq_worker.handler import WorkflowHandler

            handler = WorkflowHandler()
            handler._redis = AsyncMock()

            await handler._report_progress("job-123", {"node": "KSampler", "percent": 50})

            handler._redis.publish.assert_called_once()
            call_args = handler._redis.publish.call_args
            assert "ceq:job:job-123:status" in call_args[0]

    @pytest.mark.asyncio
    async def test_report_progress_no_redis(self):
        """Test progress reporting handles no Redis gracefully."""
        with patch("ceq_worker.handler.ComfyUIExecutor"), \
             patch("ceq_worker.handler.StorageClient"):
            from ceq_worker.handler import WorkflowHandler

            handler = WorkflowHandler()
            handler._redis = None

            # Should not raise
            await handler._report_progress("job-123", {"node": "KSampler", "percent": 50})
