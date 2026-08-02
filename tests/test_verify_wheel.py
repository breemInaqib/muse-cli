from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.verify_wheel import WheelVerificationError, main, verify_wheel

_METADATA = """\
Metadata-Version: 2.4
Name: musecli
Version: 0.1.0
Requires-Python: >=3.9
Requires-Dist: textual<9,>=8.2
Requires-Dist: typer<0.25,>=0.23
"""
_ENTRY_POINTS = """\
[console_scripts]
muse = musecli.cli:app
muse-code = musecli.code_cli:app
"""
_WHEEL_METADATA = """\
Wheel-Version: 1.0
Root-Is-Purelib: true
Tag: py3-none-any
"""


def _source_tree(root: Path) -> None:
    package = root / "musecli"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text("", encoding="utf-8")
    (package / "code_cli.py").write_text("", encoding="utf-8")


def _wheel(
    path: Path,
    *,
    omit: frozenset[str] = frozenset(),
    extra: tuple[str, str] | None = None,
    entry_points: str = _ENTRY_POINTS,
) -> None:
    members = {
        "musecli/__init__.py": "",
        "musecli/cli.py": "",
        "musecli/code_cli.py": "",
        "musecli-0.1.0.dist-info/METADATA": _METADATA,
        "musecli-0.1.0.dist-info/entry_points.txt": entry_points,
        "musecli-0.1.0.dist-info/WHEEL": _WHEEL_METADATA,
        "musecli-0.1.0.dist-info/RECORD": "",
    }
    if extra is not None:
        members[extra[0]] = extra[1]
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            if name not in omit:
                archive.writestr(name, content)


def test_valid_wheel_matches_source_and_public_entry_points(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _source_tree(tmp_path)
    wheel = tmp_path / "musecli-0.1.0-py3-none-any.whl"
    _wheel(wheel)

    assert main([str(wheel), "--source-root", str(tmp_path)]) == 0
    assert capsys.readouterr().out == f"verified wheel: {wheel.name}\n"


def test_missing_runtime_module_fails_closed(tmp_path: Path) -> None:
    _source_tree(tmp_path)
    wheel = tmp_path / "missing.whl"
    _wheel(wheel, omit=frozenset({"musecli/code_cli.py"}))

    with pytest.raises(WheelVerificationError, match="missing runtime modules.*code_cli.py"):
        verify_wheel(wheel, source_root=tmp_path)


def test_non_runtime_payload_is_rejected(tmp_path: Path) -> None:
    _source_tree(tmp_path)
    wheel = tmp_path / "private.whl"
    _wheel(wheel, extra=("tests/private-evidence.txt", "must not ship"))

    with pytest.raises(WheelVerificationError, match="non-runtime member"):
        verify_wheel(wheel, source_root=tmp_path)


def test_unexpected_package_payload_is_rejected(tmp_path: Path) -> None:
    _source_tree(tmp_path)
    wheel = tmp_path / "private-package-data.whl"
    _wheel(wheel, extra=("musecli/private-evidence.jsonl", "must not ship"))

    with pytest.raises(WheelVerificationError, match="unexpected runtime package files"):
        verify_wheel(wheel, source_root=tmp_path)


def test_console_entry_point_mismatch_is_rejected(tmp_path: Path) -> None:
    _source_tree(tmp_path)
    wheel = tmp_path / "wrong-entry.whl"
    _wheel(
        wheel,
        entry_points="[console_scripts]\nmuse = other.cli:app\n",
    )

    with pytest.raises(WheelVerificationError, match="console scripts"):
        verify_wheel(wheel, source_root=tmp_path)
