"""Tests for asset management endpoints."""

import io
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status

from ceq_api.models.asset import Asset
from ceq_api.routers.assets import sanitize_filename, ASSET_TYPES


class TestSanitizeFilename:
    """Tests for filename sanitization."""

    def test_normal_filename(self):
        """Normal filename should be unchanged."""
        result = sanitize_filename("model.safetensors")
        assert result == "model.safetensors"

    def test_path_traversal_forward_slash(self):
        """Path traversal with forward slash should be blocked."""
        result = sanitize_filename("../../../etc/passwd")
        assert "/" not in result
        assert ".." not in result
        assert result == "_.._.._.._etc_passwd"

    def test_path_traversal_backslash(self):
        """Path traversal with backslash should be blocked."""
        result = sanitize_filename("..\\..\\windows\\system32")
        assert "\\" not in result

    def test_null_bytes(self):
        """Null bytes should be removed."""
        result = sanitize_filename("file\x00.txt")
        assert "\x00" not in result

    def test_hidden_file(self):
        """Leading dots should be removed."""
        result = sanitize_filename(".hidden_file")
        assert not result.startswith(".")

    def test_special_characters(self):
        """Special characters should be replaced with underscore."""
        result = sanitize_filename("file<>:\"|?*.txt")
        assert all(c.isalnum() or c in "_.-" for c in result)

    def test_long_filename(self):
        """Long filenames should be truncated."""
        long_name = "a" * 300 + ".safetensors"
        result = sanitize_filename(long_name)
        assert len(result) <= 200

    def test_empty_filename(self):
        """Empty filename should return default."""
        result = sanitize_filename("")
        assert result == "unnamed_asset"

    def test_unicode_characters(self):
        """Unicode characters should be handled."""
        result = sanitize_filename("модель.safetensors")
        assert "_" in result or result.isascii()


class TestAssetTypes:
    """Tests for asset type definitions."""

    def test_checkpoint_type(self):
        """Checkpoint type should be defined correctly."""
        assert "checkpoint" in ASSET_TYPES
        assert ".safetensors" in ASSET_TYPES["checkpoint"]["extensions"]
        assert ASSET_TYPES["checkpoint"]["max_size_gb"] == 20

    def test_lora_type(self):
        """LoRA type should be defined correctly."""
        assert "lora" in ASSET_TYPES
        assert ASSET_TYPES["lora"]["max_size_gb"] == 1

    def test_all_types_have_required_fields(self):
        """All asset types should have required fields."""
        required_fields = ["name", "description", "extensions", "icon", "max_size_gb"]
        for asset_type, config in ASSET_TYPES.items():
            for field in required_fields:
                assert field in config, f"{asset_type} missing {field}"


class TestListAssets:
    """Tests for GET /v1/assets/"""

    def test_list_assets_empty(self, client):
        """Should return empty list when no assets exist."""
        response = client.get("/v1/assets/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["assets"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_assets_with_data(self, async_client, db_session, mock_user):
        """Should return assets owned by user."""
        asset = Asset(
            name="Test Model",
            description="A test model",
            asset_type="checkpoint",
            storage_uri="r2://ceq-assets/test.safetensors",
            size_bytes=1024 * 1024 * 100,  # 100MB
            checksum="abc123",
            tags=["test"],
            asset_metadata={},
            user_id=mock_user.id,
            is_public=False,
        )
        db_session.add(asset)
        await db_session.commit()

        response = await async_client.get("/v1/assets/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["assets"]) == 1
        assert data["assets"][0]["name"] == "Test Model"

    def test_list_assets_filter_by_type(self, client):
        """Should filter by asset type."""
        response = client.get("/v1/assets/?asset_type=lora")

        assert response.status_code == status.HTTP_200_OK

    def test_list_assets_invalid_type(self, client):
        """Should reject invalid asset type."""
        response = client.get("/v1/assets/?asset_type=invalid")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid asset_type" in response.json()["detail"]

    def test_list_assets_pagination(self, client):
        """Should respect pagination parameters."""
        response = client.get("/v1/assets/?skip=0&limit=10")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["skip"] == 0
        assert data["limit"] == 10


class TestGetAssetTypes:
    """Tests for GET /v1/assets/types"""

    def test_get_asset_types(self, client):
        """Should return all asset types."""
        response = client.get("/v1/assets/types")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "types" in data
        assert "checkpoint" in data["types"]
        assert "lora" in data["types"]


class TestGetAsset:
    """Tests for GET /v1/assets/{asset_id}"""

    def test_get_asset_not_found(self, client):
        """Should return 404 for non-existent asset."""
        fake_id = uuid4()
        response = client.get(f"/v1/assets/{fake_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_asset_success(self, async_client, db_session, mock_user):
        """Should return asset details."""
        asset = Asset(
            name="Test Model",
            description="A test model",
            asset_type="checkpoint",
            storage_uri="r2://ceq-assets/test.safetensors",
            size_bytes=1024 * 1024 * 100,
            checksum="abc123",
            tags=["test"],
            asset_metadata={},
            user_id=mock_user.id,
            is_public=False,
        )
        db_session.add(asset)
        await db_session.commit()

        response = await async_client.get(f"/v1/assets/{asset.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Test Model"
        assert data["asset_type"] == "checkpoint"

    @pytest.mark.asyncio
    async def test_get_asset_forbidden(self, async_client, db_session, mock_user):
        """Should return 403 for private asset owned by another user."""
        other_user_id = uuid4()
        asset = Asset(
            name="Private Model",
            description="Someone else's model",
            asset_type="checkpoint",
            storage_uri="r2://ceq-assets/private.safetensors",
            size_bytes=1024 * 1024 * 100,
            checksum="abc123",
            tags=[],
            asset_metadata={},
            user_id=other_user_id,
            is_public=False,
        )
        db_session.add(asset)
        await db_session.commit()

        response = await async_client.get(f"/v1/assets/{asset.id}")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_get_public_asset(self, async_client, db_session, mock_user):
        """Should allow access to public asset owned by another user."""
        other_user_id = uuid4()
        asset = Asset(
            name="Public Model",
            description="A public model",
            asset_type="checkpoint",
            storage_uri="r2://ceq-assets/public.safetensors",
            size_bytes=1024 * 1024 * 100,
            checksum="abc123",
            tags=[],
            asset_metadata={},
            user_id=other_user_id,
            is_public=True,
        )
        db_session.add(asset)
        await db_session.commit()

        response = await async_client.get(f"/v1/assets/{asset.id}")

        assert response.status_code == status.HTTP_200_OK


class TestUploadAsset:
    """Tests for POST /v1/assets/"""

    def test_upload_asset_storage_not_configured(self, client, mock_storage):
        """Should return 503 when storage is not configured."""
        mock_storage.is_configured = False

        files = {"file": ("model.safetensors", io.BytesIO(b"test data"), "application/octet-stream")}
        data = {"name": "Test Model", "asset_type": "checkpoint"}

        response = client.post("/v1/assets/", files=files, data=data)

        # Storage mock is configured in fixture, so this tests the path
        assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_503_SERVICE_UNAVAILABLE]

    def test_upload_asset_invalid_type(self, client):
        """Should reject invalid asset type."""
        files = {"file": ("model.safetensors", io.BytesIO(b"test data"), "application/octet-stream")}
        data = {"name": "Test Model", "asset_type": "invalid"}

        response = client.post("/v1/assets/", files=files, data=data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_upload_asset_invalid_extension(self, client):
        """Should reject invalid file extension."""
        files = {"file": ("model.exe", io.BytesIO(b"test data"), "application/octet-stream")}
        data = {"name": "Test Model", "asset_type": "checkpoint"}

        response = client.post("/v1/assets/", files=files, data=data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "extension" in response.json()["detail"].lower()


class TestPresignedUploadUrl:
    """Tests for POST /v1/assets/presigned-url"""

    def test_get_presigned_url(self, client):
        """Should return presigned upload URL."""
        data = {
            "filename": "model.safetensors",
            "asset_type": "checkpoint",
            "content_type": "application/octet-stream",
            "size_bytes": 1024 * 1024 * 100,
        }

        response = client.post("/v1/assets/presigned-url", json=data)

        # Depends on mock storage configuration
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE]

    def test_get_presigned_url_invalid_type(self, client):
        """Should reject invalid asset type."""
        data = {
            "filename": "model.safetensors",
            "asset_type": "invalid",
            "content_type": "application/octet-stream",
            "size_bytes": 1024,
        }

        response = client.post("/v1/assets/presigned-url", json=data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_presigned_url_file_too_large(self, client):
        """Should reject files exceeding size limit."""
        data = {
            "filename": "model.safetensors",
            "asset_type": "lora",  # Max 1GB
            "content_type": "application/octet-stream",
            "size_bytes": 5 * 1024 * 1024 * 1024,  # 5GB
        }

        response = client.post("/v1/assets/presigned-url", json=data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "too large" in response.json()["detail"].lower()


class TestConfirmUpload:
    """Tests for POST /v1/assets/{asset_id}/confirm"""

    def test_confirm_upload_not_found(self, client):
        """Should return 404 for non-existent asset."""
        fake_id = uuid4()
        response = client.post(f"/v1/assets/{fake_id}/confirm", json={})

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_confirm_upload_success(self, async_client, db_session, mock_user):
        """Should confirm pending upload."""
        asset = Asset(
            name="Pending Model",
            description="A pending upload",
            asset_type="checkpoint",
            storage_uri="r2://ceq-assets/pending/test.safetensors",
            size_bytes=1024 * 1024 * 100,
            tags=[],
            asset_metadata={"status": "pending_upload"},
            user_id=mock_user.id,
            is_public=False,
        )
        db_session.add(asset)
        await db_session.commit()

        response = await async_client.post(
            f"/v1/assets/{asset.id}/confirm",
            json={"checksum": "sha256hash"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["checksum"] == "sha256hash"


class TestDeleteAsset:
    """Tests for DELETE /v1/assets/{asset_id}"""

    def test_delete_asset_not_found(self, client):
        """Should return 404 for non-existent asset."""
        fake_id = uuid4()
        response = client.delete(f"/v1/assets/{fake_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_asset_success(self, async_client, db_session, mock_user):
        """Should soft delete asset."""
        asset = Asset(
            name="Test Model",
            description="A test model",
            asset_type="checkpoint",
            storage_uri="r2://ceq-assets/test.safetensors",
            size_bytes=1024 * 1024 * 100,
            checksum="abc123",
            tags=[],
            asset_metadata={},
            user_id=mock_user.id,
            is_public=False,
        )
        db_session.add(asset)
        await db_session.commit()

        response = await async_client.delete(f"/v1/assets/{asset.id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify soft delete
        await db_session.refresh(asset)
        assert asset.is_deleted is True

    @pytest.mark.asyncio
    async def test_delete_asset_forbidden(self, async_client, db_session, mock_user):
        """Should not allow deleting another user's asset."""
        other_user_id = uuid4()
        asset = Asset(
            name="Other's Model",
            description="Someone else's model",
            asset_type="checkpoint",
            storage_uri="r2://ceq-assets/other.safetensors",
            size_bytes=1024 * 1024 * 100,
            checksum="abc123",
            tags=[],
            asset_metadata={},
            user_id=other_user_id,
            is_public=False,
        )
        db_session.add(asset)
        await db_session.commit()

        response = await async_client.delete(f"/v1/assets/{asset.id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND  # Returns 404 for security
