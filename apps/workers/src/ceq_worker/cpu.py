"""CPU worker: runs Cinematic Pointer's CLI for job kinds that need no GPU.

RFC 0061: "the CPU worker image is Cinematic Pointer's own image with CEQ's
lease client added." This module is that lease client's job handler. It leases
``capture.page`` and ``export`` jobs, runs the CLI in a child process, and moves
every file through presigned URLs.

What this process is trusted with, and what it is not:

- It opens web pages, so it is treated as the most exposed process CEQ runs.
- It holds one credential, the worker token. It has no storage keys, no Redis
  and no database. The child process that runs the browser is not handed the
  worker credentials: its environment is rebuilt from a short allow-list, the
  credentials are removed from this process's own environment once read, and
  this process is marked non-dumpable so a same-user child cannot read its
  memory or `/proc` entries. A child running as a different user would be a
  stronger wall; that is a deployment change, not made here.
- Files the CLI names are read only if they are plain files inside the job's
  own output directory. A symlink is refused.
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
import ctypes
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
from ceq_worker.lease import ArtifactTooLargeError, LeaseConsumer

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
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,200}")
_JOB_ID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_PLATFORM = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
KNOWN_KINDS = frozenset({"capture.page", "export"})
MAX_MANIFEST_BYTES = 1024 * 1024
# Environment names that carry the worker's credential. Removed from this
# process once the settings have read them.
CREDENTIAL_ENV = (
    "CEQ_WORKER_CLIENT_SECRET",
    "JANUA_CLIENT_SECRET",
    "CEQ_WORKER_CLIENT_ID",
    "JANUA_CLIENT_ID",
)


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
    host = (parts.hostname or "").lower()
    if host.endswith("."):
        raise JobRefusedError("the host may not end in a dot")
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

    tail = bytearray()

    async def drain() -> None:
        # Only the end of the output is kept, however much the CLI prints.
        assert process.stdout is not None
        while chunk := await process.stdout.read(65536):
            tail.extend(chunk)
            del tail[:-4000]
        await process.wait()

    try:
        await asyncio.wait_for(drain(), timeout=timeout)
    except TimeoutError:
        kill()
        await process.wait()
        raise RuntimeError(f"the job ran past its {int(timeout)}s limit") from None
    except asyncio.CancelledError:
        kill()
        await process.wait()
        raise
    # A child killed by a signal has a negative return code: never read as success.
    code = process.returncode if process.returncode is not None else -1
    return code, bytes(tail).decode("utf-8", "replace")


Uploader = Callable[[str, Path, str], Awaitable[dict[str, Any]]]
Downloader = Callable[[str, str, Path], Awaitable[Path]]


def output_file(out: Path, name: str) -> Path:
    """A file the CLI named, if it is a plain file directly inside ``out``.

    The CLI's own manifest is not trusted to name what gets uploaded: a name
    with a path in it, a symlink, or anything that is not a regular file is
    refused, so a misbehaving child cannot have this worker upload something
    from elsewhere on the disk.
    """
    if not _NAME.fullmatch(name):
        raise RuntimeError(f"the CLI named a file this worker will not read: {name!r}")
    path = out / name
    if path.is_symlink() or not path.is_file() or path.resolve().parent != out.resolve():
        raise RuntimeError(f"{name!r} is not a plain file in the job's output")
    return path


def read_manifest(out: Path, name: str) -> dict[str, Any]:
    path = output_file(out, name)
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise RuntimeError(f"{name} is larger than a manifest can be")
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise RuntimeError(f"{name} is not a manifest")
    return data


def cli_failure(what: str, code: int, tail: str) -> RuntimeError:
    """The CLI failed. Its output goes to the worker's log, not to the job's error.

    The job's error is shown to the client that submitted it, and the CLI's
    output can carry paths, command lines and text taken from the page.
    """
    print(f"   {what} exited {code}; last output:\n{tail[-1500:]}")
    return RuntimeError(f"{what} exited with code {code}")


def content_type_of(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


async def capture_page(
    job_id: str, params: dict[str, Any], work: Path, upload: Uploader
) -> list[dict[str, Any]]:
    p = CapturePageParams(**params)
    # One normalised list, used for the check here and handed to the CLI.
    allowed = [h.strip().lower() for h in settings.capture_allowed_hosts if h.strip()]
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
        raise cli_failure("capture page", code, tail)

    manifest = read_manifest(out, "manifest.json")
    tiles = [(output_file(out, str(tile["file"])), tile) for tile in manifest["tiles"]]
    outputs = [await upload(job_id, output_file(out, "manifest.json"), "application/json")]
    for path, tile in tiles:
        descriptor = await upload(job_id, path, "image/png")
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
        if not all(_PLATFORM.fullmatch(name) for name in p.platforms):
            raise JobRefusedError("a platform name is not a plain word")
        args += ["--platforms", ",".join(p.platforms)]
    code, tail = await run_cli(args, cwd=work, timeout=settings.cpu_job_timeout_seconds)
    # 0: every target passed. 1: some did not, and export.json says which.
    if code not in (0, 1) or not (out / "export.json").is_file():
        raise cli_failure("export", code, tail)

    manifest = read_manifest(out, "export.json")
    failed = manifest.get("failed") or []
    if failed or code == 1:
        targets = ", ".join(f"{f.get('format')} {f.get('aspect')}" for f in failed) or "unnamed"
        print(f"   export failed targets: {failed}")
        # Not uploaded: a production must not carry on with part of an export.
        raise JobRefusedError(f"{max(1, len(failed))} export target(s) failed: {targets}")

    files = [(output_file(out, str(item["file"])), item) for item in manifest["outputs"]]
    if not files:
        raise RuntimeError("the export produced no output")
    outputs = [await upload(job_id, output_file(out, "export.json"), "application/json")]
    for path, item in files:
        descriptor = await upload(job_id, path, content_type_of(path))
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

        def failed(error: str, *, retryable: bool) -> dict[str, Any]:
            return {
                "success": False,
                "error": error[:4000],
                "retryable": retryable,
                "execution_time": time.time() - started,
                "metadata": {"kind": kind},
            }

        # The job id names a directory that is created and removed. Anything
        # that is not a UUID never touches the disk.
        if not _JOB_ID.fullmatch(job_id):
            return failed("the job has no usable id", retryable=False)
        work = Path(settings.cpu_work_dir) / job_id.lower()
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)

        try:
            if kind not in settings.cpu_capabilities:
                raise JobRefusedError(f"this worker does not run {kind!r} jobs")
            body = event.get("input")
            params = body.get("params") if isinstance(body, dict) else None
            inputs = body.get("inputs") if isinstance(body, dict) else None
            if not isinstance(params, dict) or not isinstance(inputs or {}, dict):
                raise JobRefusedError("the job's parameters are not in the expected shape")
            if kind == "capture.page":
                outputs = await capture_page(job_id, params, work, upload)
            elif kind == "export":
                outputs = await export(job_id, params, inputs or {}, work, upload, download)
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
        except (JobRefusedError, ValidationError, ArtifactTooLargeError) as exc:
            return failed(str(exc), retryable=False)
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            # A payload or manifest that is not shaped as expected will be
            # shaped the same way on the next attempt.
            return failed(f"malformed job data: {type(exc).__name__}", retryable=False)
        except Exception as exc:  # noqa: BLE001 - reported, and worth another try
            return failed(str(exc), retryable=True)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    return handler


def harden_process() -> None:
    """Keep the worker's credential out of reach of the child it starts.

    The settings have already read the credential, so it is removed from this
    process's environment (which a same-user process can read through /proc).
    On Linux the process is also marked non-dumpable, which hands its /proc
    entries to root and stops a same-user process attaching to it.
    """
    for name in CREDENTIAL_ENV:
        os.environ.pop(name, None)
    with contextlib.suppress(Exception):
        libc = ctypes.CDLL(None, use_errno=True)
        pr_set_dumpable = 4
        libc.prctl(pr_set_dumpable, 0, 0, 0, 0)


async def main() -> None:
    """Entry point of the CPU worker."""
    if not settings.lease_mode_enabled:
        raise SystemExit(
            "The CPU worker runs in lease mode only: set CEQ_LEASE_URL, "
            "CEQ_WORKER_CLIENT_ID and CEQ_WORKER_CLIENT_SECRET."
        )
    capabilities = list(settings.cpu_capabilities)
    if not capabilities or not set(capabilities) <= KNOWN_KINDS:
        raise SystemExit(
            f"CEQ_CPU_CAPABILITIES must be a non-empty subset of {sorted(KNOWN_KINDS)}; "
            f"got {capabilities!r}"
        )
    harden_process()

    async def upload(job_id: str, path: Path, content_type: str) -> dict[str, Any]:
        return await consumer.upload_artifact(job_id, path, content_type=content_type)

    async def download(job_id: str, storage_uri: str, dest: Path) -> Path:
        return await consumer.download_input(job_id, storage_uri, dest)

    consumer = LeaseConsumer(handler=make_handler(upload, download), capabilities=capabilities)
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
