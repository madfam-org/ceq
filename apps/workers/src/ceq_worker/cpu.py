"""CPU worker: runs Cinematic Pointer's CLI for job kinds that need no GPU.

RFC 0061: "the CPU worker image is Cinematic Pointer's own image with CEQ's
lease client added." This module is that lease client's job handler. It leases
``capture.page`` and ``export`` jobs, runs the CLI in a child process, and moves
every file through presigned URLs.

What this process is trusted with, and what it is not:

- It opens web pages, so it is treated as the most exposed process CEQ runs.
- It holds one credential, the worker token. It has no storage keys, no Redis
  and no database. The child process that runs the browser is not given even
  the worker credentials: its environment is rebuilt from a short allow-list.
- A page may be opened only if its host is on this worker's own list
  (``CEQ_CAPTURE_ALLOWED_HOSTS``). The API checked the same rule when the
  production was submitted; it is checked again here because this is where
  the page is actually opened, and the list is passed to the CLI so the
  browser refuses every other host too.
- Parameters are a closed set per kind. An unknown parameter fails the job.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shlex
import shutil
import signal
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ceq_worker.config import get_settings
from ceq_worker.lease import LeaseConsumer

settings = get_settings()

CONTENT_TYPES = {
    ".png": "image/png",
    ".json": "application/json",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".gif": "image/gif",
}
VIDEO_TYPES = ("video/mp4", "video/webm", "video/quicktime")
# What the child process may inherit. Nothing named CEQ_* or JANUA_* is here.
CHILD_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "PLAYWRIGHT_BROWSERS_PATH", "NODE_ENV")
_HOSTNAME = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]*[a-z][a-z0-9-]*$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")


class JobRefusedError(Exception):
    """The job cannot run here, and running it again would not change that."""


class CapturePageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    width: int = Field(default=1440, ge=320, le=7680)
    tile: int = Field(default=2048, ge=256, le=8192)
    max_height: int = Field(default=60000, ge=256, le=200000)


class ExportParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formats: list[Literal["mp4", "webm", "hevc", "gif", "prores"]] = Field(
        default_factory=list, max_length=5
    )
    aspects: list[Literal["16:9", "9:16", "1:1", "4:5", "4:3", "21:9"]] = Field(
        default_factory=list, max_length=6
    )
    platforms: list[str] = Field(default_factory=list, max_length=10)
    quality: Literal["draft", "standard", "high"] = "standard"
    # Which dependency's video to export, when more than one step feeds this one.
    from_step: str | None = Field(default=None, max_length=64)


def host_allowed(host: str, allowed: list[str]) -> bool:
    """Same rule as the API: an entry is exact, a leading dot is any subdomain."""
    host = host.lower().rstrip(".")
    for entry in allowed:
        entry = entry.lower().strip()
        if not entry:
            continue
        if entry.startswith("."):
            if host.endswith(entry) and len(host) > len(entry):
                return True
        elif host == entry:
            return True
    return False


def check_capture_url(url: str, allowed: list[str]) -> str:
    """The host of a page this worker may open, or ``JobRefusedError``."""
    if not re.fullmatch(r"[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", url):
        raise JobRefusedError("the url has characters a url here may not contain")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise JobRefusedError("the url cannot be parsed") from None
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme.lower() != "https" or port not in (None, 443) or "@" in parts.netloc:
        raise JobRefusedError("only plain https urls on the default port are opened")
    if not _HOSTNAME.match(host):
        raise JobRefusedError("the url needs a plain host name")
    if not host_allowed(host, allowed):
        raise JobRefusedError(f"host {host!r} is not one this worker may open")
    return host


def child_environment() -> dict[str, str]:
    return {name: os.environ[name] for name in CHILD_ENV if name in os.environ}


async def run_cli(args: list[str], *, cwd: Path, timeout: float) -> tuple[int, str]:
    """Run the Cinematic Pointer CLI. Returns its exit code and the tail of its output.

    The child gets its own process group, so a cancel or a timeout takes the
    browser and FFmpeg down with it instead of leaving them running.
    """
    command = [*shlex.split(settings.cinematic_pointer_cli), *args]
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        env=child_environment(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )

    def kill() -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)

    try:
        out, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        kill()
        await process.wait()
        raise RuntimeError(f"the job ran past its {int(timeout)}s limit") from None
    except asyncio.CancelledError:
        kill()
        await process.wait()
        raise
    return process.returncode or 0, out.decode("utf-8", "replace")[-2000:]


Uploader = Callable[[str, Path, str], Awaitable[dict[str, Any]]]
Downloader = Callable[[str, str, Path], Awaitable[Path]]


def content_type_of(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


async def capture_page(
    job_id: str, params: dict[str, Any], work: Path, upload: Uploader
) -> list[dict[str, Any]]:
    p = CapturePageParams(**params)
    allowed = settings.capture_allowed_hosts
    check_capture_url(p.url, allowed)
    out = work / "out"
    code, tail = await run_cli(
        [
            "capture",
            "page",
            p.url,
            "--out",
            str(out),
            "--width",
            str(p.width),
            "--tile",
            str(p.tile),
            "--max-height",
            str(p.max_height),
            "--allow-hosts",
            ",".join(allowed),
        ],
        cwd=work,
        timeout=settings.cpu_job_timeout_seconds,
    )
    if code != 0:
        raise RuntimeError(f"capture page exited {code}: {tail[-600:]}")

    manifest = json.loads((out / "manifest.json").read_text())
    outputs = [await upload(job_id, out / "manifest.json", "application/json")]
    for tile in manifest["tiles"]:
        name = str(tile["file"])
        if not _NAME.match(name):
            raise RuntimeError(f"the manifest names a file this worker will not read: {name!r}")
        descriptor = await upload(job_id, out / name, "image/png")
        outputs.append({**descriptor, "width": int(tile["w"]), "height": int(tile["h"])})
    return outputs


def pick_input(inputs: dict[str, list[dict[str, Any]]], from_step: str | None) -> dict[str, Any]:
    """The one video this export is for."""
    steps = [from_step] if from_step else list(inputs)
    videos = [
        output
        for step in steps
        for output in inputs.get(step or "", [])
        if output.get("file_type") in VIDEO_TYPES
    ]
    if len(videos) != 1:
        raise JobRefusedError(
            f"an export needs exactly one video from the steps it depends on, found {len(videos)}"
        )
    return videos[0]


async def export(
    job_id: str,
    params: dict[str, Any],
    inputs: dict[str, list[dict[str, Any]]],
    work: Path,
    upload: Uploader,
    download: Downloader,
) -> list[dict[str, Any]]:
    p = ExportParams(**params)
    source = pick_input(inputs, p.from_step)
    suffix = Path(str(source.get("filename", ""))).suffix.lower()
    if suffix not in (".mp4", ".webm", ".mov"):
        raise JobRefusedError("the input is not a video file this worker exports")
    take = await download(job_id, str(source["storage_uri"]), work / f"take{suffix}")

    out = work / "out"
    args = ["export", str(take), "--out", str(out), "--quality", p.quality]
    if p.formats:
        args += ["--formats", ",".join(p.formats)]
    if p.aspects:
        args += ["--aspects", ",".join(p.aspects)]
    if p.platforms:
        if not all(re.fullmatch(r"[a-z0-9_-]{1,32}", name) for name in p.platforms):
            raise JobRefusedError("a platform name is not a plain word")
        args += ["--platforms", ",".join(p.platforms)]
    code, tail = await run_cli(args, cwd=work, timeout=settings.cpu_job_timeout_seconds)
    # 0: every target passed. 1: some did not, and export.json says which.
    if code not in (0, 1) or not (out / "export.json").exists():
        raise RuntimeError(f"export exited {code}: {tail[-600:]}")

    manifest = json.loads((out / "export.json").read_text())
    if manifest.get("failed"):
        reasons = "; ".join(
            f"{f.get('format')} {f.get('aspect')}: {f.get('reason')}" for f in manifest["failed"]
        )
        # Not uploaded: a production must not carry on with part of an export.
        raise JobRefusedError(f"{len(manifest['failed'])} export target(s) failed: {reasons}")

    outputs = [await upload(job_id, out / "export.json", "application/json")]
    for item in manifest["outputs"]:
        name = str(item["file"])
        if not _NAME.match(name):
            raise RuntimeError(f"the manifest names a file this worker will not read: {name!r}")
        descriptor = await upload(job_id, out / name, content_type_of(out / name))
        outputs.append(
            {
                **descriptor,
                "width": int(item["width"]),
                "height": int(item["height"]),
                "duration_seconds": float(item["seconds"]),
                "metadata": {"format": item["format"], "aspect": item["aspect"]},
            }
        )
    return outputs


def make_handler(
    upload: Uploader, download: Downloader
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """The job handler a ``LeaseConsumer`` calls, bound to its transfer functions."""

    async def handler(event: dict[str, Any]) -> dict[str, Any]:
        started = time.time()
        job_id = str(event.get("id", ""))
        kind = event.get("kind")
        body = event.get("input") or {}
        work = Path(settings.cpu_work_dir) / re.sub(r"[^A-Za-z0-9-]", "_", job_id)
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)

        def failed(error: str, *, retryable: bool) -> dict[str, Any]:
            return {
                "success": False,
                "error": error[:4000],
                "retryable": retryable,
                "execution_time": time.time() - started,
                "metadata": {"kind": kind},
            }

        try:
            if kind not in settings.cpu_capabilities:
                raise JobRefusedError(f"this worker does not run {kind!r} jobs")
            if kind == "capture.page":
                outputs = await capture_page(job_id, body.get("params") or {}, work, upload)
            elif kind == "export":
                outputs = await export(
                    job_id,
                    body.get("params") or {},
                    body.get("inputs") or {},
                    work,
                    upload,
                    download,
                )
            else:
                raise JobRefusedError(f"no runner exists for {kind!r} jobs")
            return {
                "success": True,
                "outputs": outputs,
                "execution_time": time.time() - started,
                "metadata": {"kind": kind},
            }
        except asyncio.CancelledError:
            return {
                "success": False,
                "cancelled": True,
                "error": "Job cancelled",
                "execution_time": time.time() - started,
            }
        except (JobRefusedError, ValidationError) as exc:
            return failed(str(exc), retryable=False)
        except Exception as exc:  # noqa: BLE001 - reported, and worth another try
            return failed(str(exc), retryable=True)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    return handler


async def main() -> None:
    """Entry point of the CPU worker."""
    if not settings.lease_mode_enabled:
        raise SystemExit(
            "The CPU worker runs in lease mode only: set CEQ_LEASE_URL, "
            "CEQ_WORKER_CLIENT_ID and CEQ_WORKER_CLIENT_SECRET."
        )
    consumer = LeaseConsumer(capabilities=settings.cpu_capabilities)

    async def upload(job_id: str, path: Path, content_type: str) -> dict[str, Any]:
        return await consumer.upload_artifact(job_id, path, content_type=content_type)

    consumer._handler = make_handler(upload, consumer.download_input)
    await consumer.initialize()
    Path(settings.cpu_work_dir).mkdir(parents=True, exist_ok=True)
    print(f"🧮 CPU worker: {', '.join(settings.cpu_capabilities)}")

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(consumer.stop()))
    try:
        await consumer.run()
    finally:
        await consumer.close()


if __name__ == "__main__":
    asyncio.run(main())
