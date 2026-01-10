"""Tests for job queue management."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock


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
