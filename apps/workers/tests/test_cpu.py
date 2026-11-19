"""The CPU worker: what it agrees to run, what it hands the CLI, what it reports."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ceq_worker import cpu
from ceq_worker.cpu import (
    JobRefusedError,
    check_capture_url,
    child_environment,
    make_handler,
    pick_input,
)
from ceq_worker.lease import LeaseConsumer

HOSTS = ["enclii.dev", ".madfam.io"]


@pytest.fixture
def worker(tmp_path, monkeypatch):
    """A handler whose CLI is a stub script and whose transfers are recorded."""
    monkeypatch.setattr(cpu.settings, "cpu_work_dir", str(tmp_path / "work"))
    monkeypatch.setattr(cpu.settings, "capture_allowed_hosts", HOSTS)
    monkeypatch.setattr(cpu.settings, "cpu_capabilities", ["capture.page", "export"])
    monkeypatch.setattr(cpu.settings, "cpu_job_timeout_seconds", 30)
    uploaded: list[tuple[str, str, bytes]] = []

    async def upload(job_id, path, content_type):
        uploaded.append((path.name, content_type, path.read_bytes()))
        return {
            "filename": path.name,
            "storage_uri": f"r2://b/outputs/{job_id}/{path.name}",
            "file_type": content_type,
            "file_size_bytes": path.stat().st_size,
        }

    async def download(job_id, storage_uri, dest):
        dest.write_bytes(b"take")
        return dest

    def cli(script: str) -> Path:
        """Install a stub CLI. It receives the real argument vector."""
        path = tmp_path / "cli.py"
        path.write_text(script)
        monkeypatch.setattr(cpu.settings, "cinematic_pointer_cli", f"{sys.executable} {path}")
        return path

    return type(
        "Worker", (), {"handle": make_handler(upload, download), "uploaded": uploaded, "cli": cli}
    )


CAPTURE_CLI = """
import json, os, sys
args = sys.argv[1:]
out = args[args.index("--out") + 1]
os.makedirs(out)
open(os.path.join(out, "tile-r000-c000.png"), "wb").write(b"png")
json.dump({"tiles": [{"file": "tile-r000-c000.png", "w": 1440, "h": 900}], "argv": args,
           "env": sorted(os.environ)}, open(os.path.join(out, "manifest.json"), "w"))
"""

EXPORT_CLI = """
import json, os, sys
args = sys.argv[1:]
out = args[args.index("--out") + 1]
os.makedirs(out)
open(os.path.join(out, "take_mp4_16x9.mp4"), "wb").write(b"mp4")
failed = [{"format": "webm", "aspect": "16:9", "reason": "empty"}] if "webm" in " ".join(args) else []
json.dump({"outputs": [{"file": "take_mp4_16x9.mp4", "format": "mp4", "aspect": "16:9",
                        "width": 1920, "height": 1080, "seconds": 16.4}],
           "failed": failed, "argv": args}, open(os.path.join(out, "export.json"), "w"))
sys.exit(1 if failed else 0)
"""


def event(kind, params, inputs=None):
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "kind": kind,
        "input": {"params": params, "inputs": inputs or {}},
    }


TAKE = {
    "take": [
        {
            "filename": "take.mp4",
            "storage_uri": "r2://b/outputs/x/take.mp4",
            "file_type": "video/mp4",
        }
    ]
}


class TestCapturePage:
    async def test_runs_the_cli_and_reports_manifest_and_tiles(self, worker):
        worker.cli(CAPTURE_CLI)

        result = await worker.handle(event("capture.page", {"url": "https://enclii.dev/"}))

        assert result["success"] is True
        assert [o["filename"] for o in result["outputs"]] == ["manifest.json", "tile-r000-c000.png"]
        assert result["outputs"][1]["width"] == 1440
        argv = json.loads(worker.uploaded[0][2])["argv"]
        assert argv[:3] == ["capture", "page", "https://enclii.dev/"]
        assert argv[argv.index("--allow-hosts") + 1] == "enclii.dev,.madfam.io"

    async def test_the_browser_process_is_not_given_the_worker_credentials(
        self, worker, monkeypatch
    ):
        monkeypatch.setenv("CEQ_WORKER_CLIENT_SECRET", "s3cret")
        monkeypatch.setenv("JANUA_CLIENT_SECRET", "s3cret")
        monkeypatch.setenv("R2_SECRET_KEY", "s3cret")
        worker.cli(CAPTURE_CLI)

        await worker.handle(event("capture.page", {"url": "https://enclii.dev/"}))

        env = json.loads(worker.uploaded[0][2])["env"]
        assert not [name for name in env if "SECRET" in name or name.startswith(("CEQ_", "R2_"))]
        assert "PATH" in env

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/",
            "http://enclii.dev/",
            "https://evil.example\\.cv.madfam.io/",
            "https://127.0.0.1/",
            "https://enclii.dev:8443/",
            "https://u:p@enclii.dev/",
        ],
    )
    async def test_a_page_it_may_not_open_is_refused_without_running_anything(self, worker, url):
        ran = worker.cli("open('ran', 'w')")

        result = await worker.handle(event("capture.page", {"url": url}))

        assert result["success"] is False
        assert result["retryable"] is False
        assert not (ran.parent / "ran").exists()
        assert worker.uploaded == []

    async def test_an_empty_host_list_refuses_everything(self, worker, monkeypatch):
        monkeypatch.setattr(cpu.settings, "capture_allowed_hosts", [])
        result = await worker.handle(event("capture.page", {"url": "https://enclii.dev/"}))
        assert result["success"] is False and result["retryable"] is False

    async def test_an_unknown_parameter_fails_the_job(self, worker):
        result = await worker.handle(
            event("capture.page", {"url": "https://enclii.dev/", "script": "x"})
        )
        assert result["success"] is False and result["retryable"] is False

    async def test_a_cli_failure_is_retryable_and_leaves_nothing_behind(self, worker):
        worker.cli("import sys; print('boom'); sys.exit(2)")

        result = await worker.handle(event("capture.page", {"url": "https://enclii.dev/"}))

        assert result["success"] is False and result["retryable"] is True
        assert "boom" in result["error"]
        assert list(Path(cpu.settings.cpu_work_dir).iterdir()) == []

    async def test_a_manifest_cannot_name_a_file_outside_the_output(self, worker):
        worker.cli(
            CAPTURE_CLI.replace('"file": "tile-r000-c000.png"', '"file": "../../etc/passwd"')
        )
        result = await worker.handle(event("capture.page", {"url": "https://enclii.dev/"}))
        assert result["success"] is False
        assert "will not read" in result["error"]


class TestExport:
    async def test_downloads_the_take_runs_the_cli_and_reports_each_output(self, worker):
        worker.cli(EXPORT_CLI)

        result = await worker.handle(
            event("export", {"formats": ["mp4"], "aspects": ["16:9"], "quality": "draft"}, TAKE)
        )

        assert result["success"] is True
        video = result["outputs"][1]
        assert video["filename"] == "take_mp4_16x9.mp4"
        assert (video["width"], video["height"], video["duration_seconds"]) == (1920, 1080, 16.4)
        argv = json.loads(worker.uploaded[0][2])["argv"]
        assert argv[0] == "export" and argv[1].endswith("take.mp4")
        assert argv[argv.index("--formats") + 1] == "mp4"
        assert argv[argv.index("--quality") + 1] == "draft"

    async def test_a_partly_failed_export_uploads_nothing(self, worker):
        worker.cli(EXPORT_CLI)

        result = await worker.handle(
            event("export", {"formats": ["mp4", "webm"], "aspects": ["16:9"]}, TAKE)
        )

        assert result["success"] is False and result["retryable"] is False
        assert "webm 16:9: empty" in result["error"]
        assert worker.uploaded == []

    @pytest.mark.parametrize(
        "params",
        [
            {"formats": ["avi"], "aspects": ["16:9"]},
            {"input": "/etc/passwd"},
            {"formats": ["mp4"], "aspects": ["16:9"], "platforms": ["a b"]},
        ],
    )
    async def test_bad_parameters_fail_without_a_retry(self, worker, params):
        worker.cli(EXPORT_CLI)
        result = await worker.handle(event("export", params, TAKE))
        assert result["success"] is False and result["retryable"] is False

    def test_exactly_one_video_is_needed(self):
        two = {"a": TAKE["take"], "b": TAKE["take"]}
        assert pick_input(two, "a")["filename"] == "take.mp4"
        with pytest.raises(JobRefusedError, match="found 2"):
            pick_input(two, None)
        with pytest.raises(JobRefusedError, match="found 0"):
            pick_input({"a": [{"filename": "m.json", "file_type": "application/json"}]}, None)


class TestHandler:
    async def test_a_kind_it_does_not_run_is_refused(self, worker):
        result = await worker.handle(event("comfy", {}))
        assert result["success"] is False and result["retryable"] is False

    async def test_a_job_past_its_time_limit_is_killed(self, worker, monkeypatch):
        monkeypatch.setattr(cpu.settings, "cpu_job_timeout_seconds", 1)
        worker.cli("import time; time.sleep(30)")

        result = await worker.handle(event("capture.page", {"url": "https://enclii.dev/"}))

        assert result["success"] is False
        assert "limit" in result["error"]

    def test_child_environment_is_an_allow_list(self, monkeypatch):
        monkeypatch.setenv("SOMETHING_ELSE", "x")
        assert "SOMETHING_ELSE" not in child_environment()
        assert set(child_environment()) <= set(cpu.CHILD_ENV)

    def test_url_rule_matches_the_api(self):
        assert check_capture_url("https://cv.madfam.io/x?y=1", HOSTS) == "cv.madfam.io"
        for bad in ("https://madfam.io/", "https://www.enclii.dev/", "https://cv.madfam.io\t/"):
            with pytest.raises(JobRefusedError):
                check_capture_url(bad, HOSTS)


class TestLeaseClient:
    def consumer(self, **kwargs) -> LeaseConsumer:
        consumer = LeaseConsumer(**kwargs)
        consumer._client = MagicMock()
        consumer._tokens = MagicMock()
        consumer._tokens.get_token = AsyncMock(return_value="tok")
        return consumer

    def response(self, status=204, body=None):
        r = MagicMock()
        r.status_code = status
        r.json.return_value = body or {}
        return r

    async def test_capabilities_are_sent_when_declared(self):
        consumer = self.consumer(capabilities=["capture.page", "export"])
        consumer._client.post = AsyncMock(return_value=self.response())

        await consumer._lease_one()

        assert consumer._client.post.call_args.kwargs["json"]["capabilities"] == [
            "capture.page",
            "export",
        ]

    async def test_a_gpu_worker_still_sends_none(self):
        consumer = self.consumer()
        consumer._client.post = AsyncMock(return_value=self.response())

        await consumer._lease_one()

        assert "capabilities" not in consumer._client.post.call_args.kwargs["json"]

    async def test_a_handler_can_say_a_retry_will_not_help(self):
        consumer = self.consumer()
        consumer._client.post = AsyncMock(return_value=self.response(200))

        await consumer._report_result(
            "j", {"success": False, "error": "x", "retryable": False}, 1.0
        )

        assert consumer._client.post.call_args.kwargs["json"]["retryable"] is False

    async def test_upload_goes_through_a_presigned_url_with_the_signed_content_type(self, tmp_path):
        consumer = self.consumer()
        grant = self.response(
            200, {"upload_url": "https://r2/put", "storage_uri": "r2://b/outputs/j/a.png"}
        )
        consumer._client.post = AsyncMock(return_value=grant)
        consumer._client.put = AsyncMock(return_value=self.response(200))
        path = tmp_path / "a.png"
        path.write_bytes(b"12345")

        descriptor = await consumer.upload_artifact("j", path, content_type="image/png")

        assert consumer._client.post.call_args.args[0].endswith("/v1/worker/jobs/j/upload-url")
        put = consumer._client.put.call_args
        assert put.args[0] == "https://r2/put"
        assert put.kwargs["headers"] == {"Content-Type": "image/png"}
        assert "Authorization" not in put.kwargs["headers"]
        assert descriptor == {
            "filename": "a.png",
            "storage_uri": "r2://b/outputs/j/a.png",
            "file_type": "image/png",
            "file_size_bytes": 5,
        }
