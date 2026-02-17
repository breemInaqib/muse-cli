from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from .model import AppConfig


def resolve_editor(config: AppConfig, override: str | None = None) -> list[str]:
    """Resolve the command used to launch an editor."""
    candidate = override or os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not candidate and config.editor:
        candidate = config.editor
    if not candidate:
        raise RuntimeError(
            "no editor configured; set $EDITOR or update via muse settings"
        )
    return shlex.split(candidate)


def launch_editor(
    config: AppConfig,
    initial: str = "",
    override: str | None = None,
    suffix: str = ".txt",
) -> str:
    """Open an editor with optional initial text and return the result."""
    command = resolve_editor(config, override)
    with tempfile.NamedTemporaryFile("w+", suffix=suffix, delete=False) as handle:
        path = Path(handle.name)
        handle.write(initial)
        handle.flush()
    try:
        subprocess.run(command + [str(path)], check=True)
        content = path.read_text(encoding="utf-8")
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    return content
