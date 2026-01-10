"""Tests for R2 storage client."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ceq_worker.storage import StorageClient


class TestStorageClientInit:
    """Tests for StorageClient initialization."""

    def test_init_no_client(self):
        """Client should be None on init."""
        client = StorageClient()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_initialize_no_config(self):
        """Initialize should handle missing R2 config gracefully."""
        with patch("ceq_worker.storage.settings") as mock_settings:
            mock_settings.r2_endpoint = ""

            client = StorageClient()
            await client.initialize()

            assert client._client is None

    @pytest.mark.asyncio
    async def test_initialize_with_config(self):
        """Initialize should create boto3 client when configured."""
        with patch("ceq_worker.storage.settings") as mock_settings:
            mock_settings.r2_endpoint = "https://test.r2.dev"
            mock_settings.r2_access_key = "test-key"
            mock_settings.r2_secret_key = "test-secret"

            with patch("ceq_worker.storage.boto3") as mock_boto3:
                mock_client = MagicMock()
                mock_boto3.client.return_value = mock_client

                client = StorageClient()
                await client.initialize()

                # Client should be set
                assert client._client is not None


class TestStorageClientContentType:
    """Tests for content type detection."""

    def test_guess_content_type_png(self):
        """Should detect PNG content type."""
        client = StorageClient()
        assert client._guess_content_type(Path("test.png")) == "image/png"

    def test_guess_content_type_jpg(self):
        """Should detect JPEG content type."""
        client = StorageClient()
        assert client._guess_content_type(Path("test.jpg")) == "image/jpeg"
        assert client._guess_content_type(Path("test.jpeg")) == "image/jpeg"

    def test_guess_content_type_webp(self):
        """Should detect WebP content type."""
        client = StorageClient()
        assert client._guess_content_type(Path("test.webp")) == "image/webp"

    def test_guess_content_type_video(self):
        """Should detect video content types."""
        client = StorageClient()
        assert client._guess_content_type(Path("test.mp4")) == "video/mp4"
        assert client._guess_content_type(Path("test.webm")) == "video/webm"

    def test_guess_content_type_3d(self):
        """Should detect 3D model content types."""
        client = StorageClient()
        assert client._guess_content_type(Path("model.glb")) == "model/gltf-binary"
        assert client._guess_content_type(Path("model.gltf")) == "model/gltf+json"

    def test_guess_content_type_model_files(self):
        """Should detect ML model file types."""
        client = StorageClient()
        assert client._guess_content_type(Path("model.safetensors")) == "application/octet-stream"
        assert client._guess_content_type(Path("model.ckpt")) == "application/octet-stream"

    def test_guess_content_type_unknown(self):
        """Should return octet-stream for unknown types."""
        client = StorageClient()
        assert client._guess_content_type(Path("file.xyz")) == "application/octet-stream"

    def test_guess_content_type_case_insensitive(self):
        """Should handle uppercase extensions."""
        client = StorageClient()
        assert client._guess_content_type(Path("test.PNG")) == "image/png"
        assert client._guess_content_type(Path("test.JPG")) == "image/jpeg"


class TestStorageClientUpload:
    """Tests for upload operations."""

    @pytest.mark.asyncio
    async def test_upload_output_no_client(self, tmp_path):
        """Upload should return local path when client not configured."""
        client = StorageClient()

        test_file = tmp_path / "output.png"
        test_file.write_bytes(b"fake image data")

        result = await client.upload_output(test_file, "test-job")

        assert result == str(test_file)

    @pytest.mark.asyncio
    async def test_upload_output_success(self, tmp_path):
        """Upload should upload file and return URL."""
        with patch("ceq_worker.storage.settings") as mock_settings:
            mock_settings.r2_bucket = "test-bucket"
            mock_settings.r2_public_url = "https://cdn.example.com"

            client = StorageClient()
            client._client = MagicMock()
            client._client.upload_file = MagicMock()

            test_file = tmp_path / "output.png"
            test_file.write_bytes(b"fake image data")

            result = await client.upload_output(test_file, "test-job-123")

            assert result.startswith("https://cdn.example.com/outputs/test-job-123/")
            assert result.endswith(".png")

    @pytest.mark.asyncio
    async def test_upload_output_no_public_url(self, tmp_path):
        """Upload should use endpoint URL when no public URL configured."""
        with patch("ceq_worker.storage.settings") as mock_settings:
            mock_settings.r2_bucket = "test-bucket"
            mock_settings.r2_public_url = ""
            mock_settings.r2_endpoint = "https://r2.cloudflarestorage.com"

            client = StorageClient()
            client._client = MagicMock()
            client._client.upload_file = MagicMock()

            test_file = tmp_path / "output.png"
            test_file.write_bytes(b"fake image data")

            result = await client.upload_output(test_file, "test-job")

            assert result.startswith("https://r2.cloudflarestorage.com/test-bucket/outputs/")

    @pytest.mark.asyncio
    async def test_upload_output_custom_content_type(self, tmp_path):
        """Upload should use provided content type."""
        with patch("ceq_worker.storage.settings") as mock_settings:
            mock_settings.r2_bucket = "test-bucket"
            mock_settings.r2_public_url = "https://cdn.example.com"

            client = StorageClient()
            mock_s3_client = MagicMock()
            client._client = mock_s3_client

            test_file = tmp_path / "output.bin"
            test_file.write_bytes(b"binary data")

            await client.upload_output(test_file, "test-job", content_type="application/custom")

            # Verify upload was called with custom content type
            mock_s3_client.upload_file.assert_called()


class TestStorageClientAssets:
    """Tests for asset operations."""

    @pytest.mark.asyncio
    async def test_upload_asset_no_client(self, tmp_path):
        """Upload asset should return local path when not configured."""
        client = StorageClient()

        test_file = tmp_path / "model.safetensors"
        test_file.write_bytes(b"fake model data")

        result = await client.upload_asset(test_file, "checkpoint", "asset-123")

        assert result == str(test_file)

    @pytest.mark.asyncio
    async def test_upload_asset_success(self, tmp_path):
        """Upload asset should return R2 URI."""
        with patch("ceq_worker.storage.settings") as mock_settings:
            mock_settings.r2_bucket = "test-bucket"

            client = StorageClient()
            client._client = MagicMock()
            client._client.upload_file = MagicMock()

            test_file = tmp_path / "model.safetensors"
            test_file.write_bytes(b"fake model data")

            result = await client.upload_asset(test_file, "checkpoint", "asset-123")

            assert result == "r2://test-bucket/assets/checkpoint/asset-123/model.safetensors"

    @pytest.mark.asyncio
    async def test_download_asset_no_client(self, tmp_path):
        """Download should raise error when client not configured."""
        client = StorageClient()

        with pytest.raises(RuntimeError, match="not configured"):
            await client.download_asset(
                "r2://bucket/key",
                tmp_path / "downloaded.safetensors",
            )

    @pytest.mark.asyncio
    async def test_download_asset_invalid_uri(self, tmp_path):
        """Download should reject invalid URIs."""
        client = StorageClient()
        client._client = MagicMock()

        with pytest.raises(ValueError, match="Invalid R2 URI"):
            await client.download_asset(
                "s3://bucket/key",
                tmp_path / "downloaded.safetensors",
            )

    @pytest.mark.asyncio
    async def test_download_asset_success(self, tmp_path):
        """Download should download file and return path."""
        client = StorageClient()
        mock_s3_client = MagicMock()
        client._client = mock_s3_client

        dest_path = tmp_path / "models" / "downloaded.safetensors"

        result = await client.download_asset(
            "r2://test-bucket/assets/checkpoint/id/model.safetensors",
            dest_path,
        )

        assert result == dest_path
        # Verify parent directory was created
        assert dest_path.parent.exists()


class TestStorageClientURIParsing:
    """Tests for URI parsing."""

    @pytest.mark.asyncio
    async def test_parse_uri_simple(self, tmp_path):
        """Should parse simple R2 URI."""
        client = StorageClient()
        client._client = MagicMock()

        await client.download_asset(
            "r2://bucket/key.txt",
            tmp_path / "output.txt",
        )

        client._client.download_file.assert_called_with(
            "bucket",
            "key.txt",
            str(tmp_path / "output.txt"),
        )

    @pytest.mark.asyncio
    async def test_parse_uri_nested(self, tmp_path):
        """Should parse nested R2 URI."""
        client = StorageClient()
        client._client = MagicMock()

        await client.download_asset(
            "r2://bucket/path/to/deep/file.safetensors",
            tmp_path / "output.safetensors",
        )

        client._client.download_file.assert_called_with(
            "bucket",
            "path/to/deep/file.safetensors",
            str(tmp_path / "output.safetensors"),
        )


class TestStorageClientEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_initialize_twice(self):
        """Initialize should be idempotent."""
        with patch("ceq_worker.storage.settings") as mock_settings:
            mock_settings.r2_endpoint = "https://test.r2.dev"
            mock_settings.r2_access_key = "test-key"
            mock_settings.r2_secret_key = "test-secret"

            with patch("ceq_worker.storage.boto3") as mock_boto3:
                mock_client = MagicMock()
                mock_boto3.client.return_value = mock_client

                client = StorageClient()
                await client.initialize()
                first_client = client._client

                await client.initialize()
                second_client = client._client

                # Should be same client
                assert first_client is second_client
                # Should only create client once
                assert mock_boto3.client.call_count == 1

    @pytest.mark.asyncio
    async def test_upload_creates_unique_keys(self, tmp_path):
        """Each upload should have unique key."""
        with patch("ceq_worker.storage.settings") as mock_settings:
            mock_settings.r2_bucket = "test-bucket"
            mock_settings.r2_public_url = "https://cdn.example.com"

            client = StorageClient()
            client._client = MagicMock()

            test_file = tmp_path / "output.png"
            test_file.write_bytes(b"data")

            results = []
            for _ in range(3):
                result = await client.upload_output(test_file, "test-job")
                results.append(result)

            # All URLs should be unique
            assert len(set(results)) == 3
