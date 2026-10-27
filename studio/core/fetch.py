"""Getting the source video onto the server.

The point of this module is that your office connection never has to carry a
two-gigabyte file. If the recording is already in Google Drive, YouTube,
Dropbox or anywhere else with a shareable link, the server pulls it directly at
datacentre speed and you only ever sent a URL.

Uploading stays available for footage that exists nowhere but your desktop.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from . import config

ProgressCallback = Callable[[str], None]


class FetchError(RuntimeError):
    """The source could not be retrieved, in terms worth showing to a person."""


def looks_like_url(value: str) -> bool:
    return value.strip().lower().startswith(("http://", "https://"))


def _ensure_yt_dlp() -> str:
    path = shutil.which("yt-dlp")
    if path is None:
        raise FetchError(
            "yt-dlp is not installed on the server, so links cannot be "
            "fetched. The Docker image installs it."
        )
    return path


def fetch_from_url(url: str, destination_dir: Path,
                   progress: ProgressCallback | None = None) -> Path:
    """Download a video from a shareable link.

    yt-dlp handles YouTube, Google Drive, Dropbox, Vimeo and several hundred
    other sources, which is why it is used in place of a plain HTTP download.
    """
    executable = _ensure_yt_dlp()
    destination_dir.mkdir(parents=True, exist_ok=True)

    if progress:
        progress("Fetching the video from the link")

    # Prefer a single already-muxed MP4 where one exists: merging separate
    # audio and video streams doubles the work for no gain here.
    command = [
        executable,
        "--no-playlist",
        "--no-warnings",
        "--max-filesize", f"{int(config.MAX_SOURCE_GB * 1024)}m",
        "-f", "best[ext=mp4]/bv*[ext=mp4]+ba[ext=m4a]/best",
        "--merge-output-format", "mp4",
        "-o", str(destination_dir / "source.%(ext)s"),
        url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip().splitlines()
        detail = message[-1] if message else "unknown error"
        if "private" in detail.lower() or "sign in" in detail.lower():
            raise FetchError(
                "That link is private. Set the file's sharing to 'anyone with "
                "the link' and try again."
            )
        raise FetchError(f"Could not fetch that link: {detail[:300]}")

    downloaded = sorted(
        (path for path in destination_dir.glob("source.*") if path.is_file()),
        key=lambda path: path.stat().st_size,
        reverse=True,
    )
    if not downloaded:
        raise FetchError(
            "The link was reached but no video came back. It may point at a "
            "page rather than a file."
        )
    return downloaded[0]


def check_size(path: Path) -> None:
    """Guard the server's disk against one enormous file."""
    gigabytes = path.stat().st_size / (1024 ** 3)
    if gigabytes > config.MAX_SOURCE_GB:
        path.unlink(missing_ok=True)
        raise FetchError(
            f"That file is {gigabytes:.1f}GB, over the {config.MAX_SOURCE_GB}GB "
            "limit. Trim it first, or raise STUDIO_MAX_SOURCE_GB if the server "
            "has the disk for it."
        )
