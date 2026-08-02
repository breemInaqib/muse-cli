#!/usr/bin/env python3
"""Measure fresh-process muse prompt readiness through a pseudo-terminal."""

from __future__ import annotations

import argparse
import importlib.metadata
import os
import platform
import select
import statistics
import struct
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
    import pty
    import termios
except ImportError:  # pragma: no cover - Unix-only measurement helper
    fcntl = None
    pty = None
    termios = None

_SIMPLE_MARKER = "› ".encode()
_WORKSPACE_MARKER = b"ask, direct, reference or command"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure cold and warm muse prompt readiness in fresh processes."
    )
    parser.add_argument(
        "--muse",
        default="muse",
        help="Path to the muse console executable (default: muse).",
    )
    parser.add_argument(
        "--warm-runs",
        type=int,
        default=5,
        help="Fresh-process launches used for the warm median (default: 5).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Optional local data directory passed to each muse process.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Seconds allowed for each presentation to become ready (default: 10).",
    )
    args = parser.parse_args()
    if args.warm_runs < 1:
        parser.error("--warm-runs must be at least 1")
    if pty is None or fcntl is None or termios is None:
        parser.error("startup measurement requires a Unix pseudo-terminal")

    executable = _resolve_executable(args.muse)
    base_command = [executable]
    if args.data_dir is not None:
        base_command.extend(("--data-dir", str(args.data_dir.expanduser())))
    simple = _measure_series(
        base_command,
        marker=_SIMPLE_MARKER,
        warm_runs=args.warm_runs,
        timeout=args.timeout,
    )
    workspace = _measure_series(
        [*base_command, "--tui"],
        marker=_WORKSPACE_MARKER,
        warm_runs=args.warm_runs,
        timeout=args.timeout,
    )

    print("muse startup measurement")
    print(f"  measured at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"  platform: {platform.platform()}")
    print(f"  python: {platform.python_version()}")
    print(f"  textual: {_package_version('textual')}")
    print("  boundary: fresh process start to visible input-ready marker")
    print(f"  warm samples: {args.warm_runs}")
    print(f"  simple cold: {simple[0]:.1f} ms")
    print(f"  simple warm median: {simple[1]:.1f} ms")
    print(f"  workspace cold: {workspace[0]:.1f} ms")
    print(f"  workspace warm median: {workspace[1]:.1f} ms")
    return 0


def _measure_series(
    command: list[str],
    *,
    marker: bytes,
    warm_runs: int,
    timeout: float,
) -> tuple[float, float]:
    cold = _measure_once(command, marker=marker, timeout=timeout)
    warm = [_measure_once(command, marker=marker, timeout=timeout) for _ in range(warm_runs)]
    return cold, statistics.median(warm)


def _measure_once(
    command: list[str],
    *,
    marker: bytes,
    timeout: float,
    exit_timeout: float = 3.0,
) -> float:
    master, slave = pty.openpty()
    _set_terminal_size(slave, columns=120, rows=36)
    environment = os.environ.copy()
    environment.setdefault("TERM", "xterm-256color")
    started = time.perf_counter_ns()
    process = subprocess.Popen(
        command,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        close_fds=True,
        env=environment,
    )
    os.close(slave)
    captured = bytearray()
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], min(0.1, deadline - time.monotonic()))
            if not ready:
                if process.poll() is not None:
                    break
                continue
            chunk = os.read(master, 65536)
            if not chunk:
                break
            captured.extend(chunk)
            if marker in captured:
                elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
                _request_clean_exit(process, master, timeout=exit_timeout)
                return elapsed_ms
        exit_code = process.poll()
        suffix = f"; process exited with status {exit_code}" if exit_code is not None else ""
        raise RuntimeError(f"presentation did not become ready within {timeout:.1f}s{suffix}")
    finally:
        os.close(master)
        if process.poll() is None:
            _terminate_process(process)


def _request_clean_exit(
    process: subprocess.Popen[bytes],
    master: int,
    *,
    timeout: float,
) -> None:
    """Request `/exit` and require a clean status instead of hiding termination."""
    os.write(master, b"/exit\r")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            if exit_code != 0:
                raise RuntimeError(f"presentation exited with status {exit_code} after /exit")
            return
        remaining = deadline - time.monotonic()
        ready, _, _ = select.select([master], [], [], min(0.1, remaining))
        if ready:
            try:
                os.read(master, 65536)
            except OSError:
                if process.poll() is None:
                    raise

    raise RuntimeError(f"presentation did not exit within {timeout:.1f}s after /exit")


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    """Best-effort cleanup used only after a measurement has failed."""
    process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass


def _set_terminal_size(file_descriptor: int, *, columns: int, rows: int) -> None:
    size = struct.pack("HHHH", rows, columns, 0, 0)
    fcntl.ioctl(file_descriptor, termios.TIOCSWINSZ, size)


def _resolve_executable(value: str) -> str:
    candidate = Path(value).expanduser()
    if candidate.parent != Path("."):
        if not candidate.is_file():
            raise SystemExit(f"error: muse executable not found: {candidate}")
        return str(candidate)
    from shutil import which

    resolved = which(value)
    if resolved is None:
        raise SystemExit(f"error: muse executable not found: {value}")
    return resolved


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


if __name__ == "__main__":
    raise SystemExit(main())
