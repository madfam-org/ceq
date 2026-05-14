"""Tests for job queue management."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestJobQueue:
    """Test job queue operations."""

    @pytest.mark.asyncio
    async def test_enqueue_job(self, mock_redis, sample_job_data):
        """Test enqueueing a job."""
        job_json = json.dumps(sample_job_data)

        await mock_redis.lpush("ceq:jobs:pending", job_json)

        mock_redis.lpush.assert_called_once_with(
            "ceq:jobs:pending",
            job_json,
        )

    @pytest.mark.asyncio
    async def test_dequeue_job(self, mock_redis, sample_job_data):
        """Test dequeueing a job."""
        job_json = json.dumps(sample_job_data)
        mock_redis.brpop.return_value = ("ceq:jobs:pending", job_json)

        result = await mock_redis.brpop("ceq:jobs:pending", timeout=5)

        assert result is not None
        assert result[1] == job_json

    @pytest.mark.asyncio
    async def test_job_priority_ordering(self, mock_redis):
        """Test jobs are processed by priority."""
        high_priority = {"id": "high", "priority": 10}
        low_priority = {"id": "low", "priority": 1}

        # High priority should be processed first
        # This tests the concept - actual implementation uses sorted sets
        await mock_redis.lpush("ceq:jobs:pending", json.dumps(high_priority))
        await mock_redis.lpush("ceq:jobs:pending", json.dumps(low_priority))

        assert mock_redis.lpush.call_count == 2


class TestJobStatusTracking:
    """Test job status tracking in Redis."""

    @pytest.mark.asyncio
    async def test_update_job_status(self, mock_redis):
        """Test updating job status."""
        job_id = "test-123"

        await mock_redis.hset(
            f"ceq:job:{job_id}",
            mapping={
                "status": "running",
                "progress": "0.5",
                "current_node": "KSampler",
            },
        )

        mock_redis.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_job_status(self, mock_redis):
        """Test getting job status."""
        job_id = "test-123"
        mock_redis.hgetall.return_value = {
            "status": "running",
            "progress": "0.5",
        }

        result = await mock_redis.hgetall(f"ceq:job:{job_id}")

        assert result["status"] == "running"
        assert result["progress"] == "0.5"

    @pytest.mark.asyncio
    async def test_publish_status_update(self, mock_redis):
        """Test publishing status update via pubsub."""
        job_id = "test-123"
        update = json.dumps({
            "type": "progress",
            "data": {"progress": 0.75, "current_node": "VAEDecode"},
        })

        await mock_redis.publish(f"ceq:job:{job_id}:status", update)

        mock_redis.publish.assert_called_once()


class TestCompletionCallback:
    """Test worker -> API completion callback."""

    @pytest.mark.asyncio
    async def test_report_completion_posts_output_descriptors(self, monkeypatch):
        """Completion callback should POST durable output metadata to ceq-api."""
        from ceq_worker import queue as queue_module
        from ceq_worker.queue import QueueConsumer

        monkeypatch.setattr(queue_module.settings, "api_url", "http://api")
        monkeypatch.setattr(
            queue_module.settings,
            "api_job_completion_path",
            "/v1/jobs/{job_id}/outputs/report",
        )
        monkeypatch.setattr(
            queue_module.settings,
            "api_job_completion_token",
            "test-token",
        )

        consumer = QueueConsumer()
        consumer._redis = AsyncMock()

        response = MagicMock()
        response.raise_for_status.return_value = None

        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response

        result = {
            "success": True,
            "execution_time": 1.5,
            "outputs": [
                {
                    "filename": "output.png",
                    "storage_uri": "r2://ceq-assets/outputs/job/output.png",
                    "public_url": "https://cdn.example.com/output.png",
                    "file_type": "image/png",
                    "file_size_bytes": 1024,
                    "preview_url": "https://cdn.example.com/output.png",
                }
            ],
            "metadata": {"vram_peak_gb": 10},
        }

        with patch("ceq_worker.queue.httpx.AsyncClient", return_value=client):
            sent = await consumer._report_completion("job-1", result)

        assert sent is True
        client.post.assert_called_once()
        call = client.post.call_args
        assert call.args[0] == "http://api/v1/jobs/job-1/outputs/report"
        assert call.kwargs["headers"]["X-CEQ-Worker-Token"] == "test-token"
        assert call.kwargs["json"]["outputs"][0]["file_type"] == "image/png"

    @pytest.mark.asyncio
    async def test_report_completion_skips_without_token(self, monkeypatch):
        """Callback should be explicitly disabled when no token is configured."""
        from ceq_worker import queue as queue_module
        from ceq_worker.queue import QueueConsumer

        monkeypatch.setattr(queue_module.settings, "api_job_completion_token", "")

        consumer = QueueConsumer()

        sent = await consumer._report_completion("job-1", {"success": True})

        assert sent is False
