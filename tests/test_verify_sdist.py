from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from scripts.verify_sdist import (
    _REQUIRED_DEVELOPER_PATHS,
    SdistVerificationError,
    main,
    verify_sdist,
)


def _source_tree(root: Path) -> None:
    for name in ("musecli/__init__.py", "musecli/cli.py", "tests/test_cli.py"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")


def _sdist(
    path: Path,
    *,
    omit: frozenset[str] = frozenset(),
    extra: tuple[str, bytes] | None = None,
) -> None:
    root = "musecli-0.1.0"
    members = {
        *(_REQUIRED_DEVELOPER_PATHS - omit),
        "musecli/__init__.py",
        "musecli/cli.py",
        "tests/test_cli.py",
        "PKG-INFO",
    }
    with tarfile.open(path, mode="w:gz") as archive:
        for name in sorted(members):
            if name in omit:
                continue
            content = b""
            info = tarfile.TarInfo(f"{root}/{name}")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        if extra is not None:
            info = tarfile.TarInfo(f"{root}/{extra[0]}")
            info.size = len(extra[1])
            archive.addfile(info, io.BytesIO(extra[1]))


def test_valid_sdist_matches_source_and_developer_contract(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _source_tree(tmp_path)
    sdist = tmp_path / "musecli-0.1.0.tar.gz"
    _sdist(sdist)

    assert main([str(sdist), "--source-root", str(tmp_path)]) == 0
    assert capsys.readouterr().out == f"verified source distribution: {sdist.name}\n"


def test_missing_developer_file_fails_closed(tmp_path: Path) -> None:
    _source_tree(tmp_path)
    sdist = tmp_path / "missing.tar.gz"
    _sdist(sdist, omit=frozenset({"uv.lock"}))

    with pytest.raises(SdistVerificationError, match="missing developer files.*uv.lock"):
        verify_sdist(sdist, source_root=tmp_path)


@pytest.mark.parametrize(
    "name",
    [
        "muse.db",
        "agent/runs/private.jsonl",
        ".env.local",
        "musecli/__pycache__/cli.pyc",
        "tests/.DS_Store",
    ],
)
def test_private_or_generated_payload_is_rejected(tmp_path: Path, name: str) -> None:
    _source_tree(tmp_path)
    sdist = tmp_path / "private.tar.gz"
    _sdist(sdist, extra=(name, b"PRIVATE"))

    with pytest.raises(SdistVerificationError, match="private member"):
        verify_sdist(sdist, source_root=tmp_path)


def test_missing_source_module_fails_closed(tmp_path: Path) -> None:
    _source_tree(tmp_path)
    (tmp_path / "musecli" / "new_module.py").write_text("", encoding="utf-8")
    sdist = tmp_path / "missing-module.tar.gz"
    _sdist(sdist)

    with pytest.raises(SdistVerificationError, match="missing musecli files.*new_module.py"):
        verify_sdist(sdist, source_root=tmp_path)
