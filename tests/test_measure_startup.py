from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_measurement_module() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "measure_startup.py"
    specification = importlib.util.spec_from_file_location("muse_measure_startup", path)
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


MEASUREMENT = _load_measurement_module()


@pytest.mark.skipif(MEASUREMENT.pty is None, reason="requires a Unix pseudo-terminal")
def test_measurement_requires_clean_exit_after_readiness() -> None:
    elapsed = MEASUREMENT._measure_once(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "print('READY', flush=True); "
                "line = sys.stdin.readline(); "
                "raise SystemExit(0 if line.strip() == '/exit' else 7)"
            ),
        ],
        marker=b"READY",
        timeout=2.0,
        exit_timeout=1.0,
    )

    assert elapsed >= 0


@pytest.mark.skipif(MEASUREMENT.pty is None, reason="requires a Unix pseudo-terminal")
def test_measurement_does_not_report_forced_termination_as_success() -> None:
    with pytest.raises(RuntimeError, match="did not exit within 0.1s after /exit"):
        MEASUREMENT._measure_once(
            [
                sys.executable,
                "-c",
                (
                    "import sys, time; "
                    "print('READY', flush=True); "
                    "sys.stdin.readline(); "
                    "time.sleep(10)"
                ),
            ],
            marker=b"READY",
            timeout=2.0,
            exit_timeout=0.1,
        )
