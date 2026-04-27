"""Shared helpers for timestamps, local IO, and terminal output."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    """Return UTC time without microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_utc(value: datetime) -> datetime:
    """Normalize a datetime into UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc, microsecond=0)
    return value.astimezone(timezone.utc).replace(microsecond=0)


def iso_utc(value: datetime) -> str:
    """Serialize a datetime with a stable UTC `Z` suffix."""
    return to_utc(value).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: Any) -> datetime:
    """Parse an ISO timestamp string into UTC."""
    if isinstance(value, datetime):
        return to_utc(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp is required")
    return to_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def ensure_private_dir(path: Path) -> Path:
    """Create a directory and try to set `0700` permissions."""
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except PermissionError:
        pass
    return path


def ensure_private_file(path: Path) -> Path:
    """Try to set `0600` permissions on an existing file."""
    if path.exists():
        try:
            os.chmod(path, 0o600)
        except PermissionError:
            pass
    return path


def truncate(text: str, width: int) -> str:
    """Trim text to a fixed width using `...` when needed."""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    limit = width - 3
    trimmed = text[:limit].rstrip()
    word_end = trimmed.rfind(" ")
    if word_end >= max(limit - 12, (limit * 2) // 3, 1):
        trimmed = trimmed[:word_end]
    return trimmed + "..."


class ClipboardUnavailableError(RuntimeError):
    """Raised when no supported clipboard provider can be used."""


def read_clipboard_text() -> str:
    """Read clipboard text using the first available system provider."""
    system = platform.system().lower()
    commands: list[list[str]]
    if system == "darwin":
        commands = [["pbpaste"]]
    elif system == "linux":
        commands = [
            ["wl-paste", "--no-newline"],
            ["xclip", "-selection", "clipboard", "-o"],
            ["xsel", "--clipboard", "--output"],
        ]
    elif system == "windows":
        commands = [["powershell", "-NoProfile", "-Command", "Get-Clipboard"]]
    else:
        commands = []

    checked_any = False
    for command in commands:
        executable = command[0]
        if shutil.which(executable) is None:
            continue
        checked_any = True
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise ClipboardUnavailableError(
                f"Could not read clipboard via {executable}: {exc}"
            ) from exc
        return result.stdout

    if not checked_any:
        raise ClipboardUnavailableError(
            "No supported clipboard command found. Install pbpaste, wl-paste, "
            "xclip, xsel, or PowerShell Get-Clipboard support."
        )
    raise ClipboardUnavailableError("Clipboard text could not be read.")
