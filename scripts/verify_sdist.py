#!/usr/bin/env python3
"""Deterministically verify the reproducible museCLI source distribution."""

from __future__ import annotations

import argparse
import tarfile
from pathlib import Path, PurePosixPath
from typing import Optional

_REQUIRED_DEVELOPER_PATHS = {
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "MANIFEST.in",
    "README.md",
    "pyproject.toml",
    "uv.lock",
    "docs/architecture.md",
    "docs/design.md",
    "docs/muse-code.md",
    "docs/product-contract.md",
    "docs/recovery.md",
    "docs/workspace.md",
    "docs/decisions/README.md",
    "docs/decisions/0001-product-surfaces.md",
    "docs/decisions/0002-agent-run-evidence-and-activity-projection.md",
    "docs/decisions/0003-first-read-only-muse-code-capability.md",
    "docs/decisions/0004-permissions-and-record-time-privacy.md",
    "docs/decisions/0005-session-durability-and-workspace.md",
    "docs/decisions/0006-local-data-recovery-policy.md",
    "scripts/check.sh",
    "scripts/measure_startup.py",
    "scripts/verify_sdist.py",
    "scripts/verify_wheel.py",
}
_FORBIDDEN_PARTS = {
    ".git",
    ".muse",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "agent/runs",
    "build",
    "dist",
}
_FORBIDDEN_FILENAMES = {".ds_store", ".env", "config.json", "muse.db"}
_FORBIDDEN_SUFFIXES = (".db", ".jsonl", ".pyc", ".pyo", ".sqlite", ".sqlite3")


class SdistVerificationError(RuntimeError):
    """Raised when a source distribution does not match the project contract."""


def verify_sdist(sdist_path: Path, *, source_root: Path) -> None:
    """Verify reproducibility files, source coverage, and private-data exclusions."""
    if not sdist_path.is_file():
        raise SdistVerificationError(f"source distribution not found: {sdist_path}")

    try:
        with tarfile.open(sdist_path, mode="r:gz") as archive:
            members = archive.getmembers()
    except (OSError, tarfile.TarError) as exc:
        raise SdistVerificationError(
            f"could not read source distribution: {sdist_path.name}"
        ) from exc

    root, relative_files = _verify_members(members)
    _verify_required_files(relative_files)
    _verify_python_tree(relative_files, source_root=source_root, folder="musecli")
    _verify_python_tree(relative_files, source_root=source_root, folder="tests")
    if f"{root}/PKG-INFO" not in {member.name for member in members}:
        raise SdistVerificationError("source distribution is missing PKG-INFO")


def _verify_members(members: list[tarfile.TarInfo]) -> tuple[str, set[str]]:
    names = [member.name for member in members]
    if len(names) != len(set(names)):
        raise SdistVerificationError("source distribution contains duplicate members")

    roots: set[str] = set()
    relative_files: set[str] = set()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise SdistVerificationError(
                f"source distribution contains unsafe member: {member.name}"
            )
        if len(path.parts) == 1:
            if not member.isdir():
                raise SdistVerificationError(
                    f"source distribution contains unsafe member: {member.name}"
                )
            roots.add(path.parts[0])
            continue
        if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
            raise SdistVerificationError(
                f"source distribution contains unsupported member: {member.name}"
            )
        roots.add(path.parts[0])
        relative = PurePosixPath(*path.parts[1:])
        _verify_private_path(relative)
        if member.isfile():
            relative_files.add(relative.as_posix())

    if len(roots) != 1:
        raise SdistVerificationError("source distribution must contain one top-level directory")
    return roots.pop(), relative_files


def _verify_private_path(path: PurePosixPath) -> None:
    lowered_parts = tuple(part.lower() for part in path.parts)
    lowered = path.as_posix().lower()
    if any(part in _FORBIDDEN_PARTS for part in lowered_parts):
        raise SdistVerificationError(f"source distribution contains private member: {path}")
    if "agent/runs" in lowered:
        raise SdistVerificationError(f"source distribution contains private member: {path}")
    name = path.name.lower()
    if (
        name in _FORBIDDEN_FILENAMES
        or name.startswith(".env.")
        or name.endswith(_FORBIDDEN_SUFFIXES)
    ):
        raise SdistVerificationError(f"source distribution contains private member: {path}")


def _verify_required_files(relative_files: set[str]) -> None:
    missing = sorted(_REQUIRED_DEVELOPER_PATHS - relative_files)
    if missing:
        raise SdistVerificationError(
            f"source distribution is missing developer files: {', '.join(missing)}"
        )


def _verify_python_tree(relative_files: set[str], *, source_root: Path, folder: str) -> None:
    expected = {
        path.relative_to(source_root).as_posix()
        for path in (source_root / folder).rglob("*.py")
        if path.is_file()
    }
    actual = {
        name for name in relative_files if name.startswith(f"{folder}/") and name.endswith(".py")
    }
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        raise SdistVerificationError(
            f"source distribution is missing {folder} files: {', '.join(missing)}"
        )
    if unexpected:
        raise SdistVerificationError(
            f"source distribution contains unexpected {folder} files: {', '.join(unexpected)}"
        )


def main(argv: Optional[list[str]] = None) -> int:  # noqa: UP045
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdist", type=Path, help="Path to the source distribution archive.")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root used to enumerate source and test modules.",
    )
    arguments = parser.parse_args(argv)
    try:
        verify_sdist(
            arguments.sdist.expanduser().resolve(),
            source_root=arguments.source_root.expanduser().resolve(),
        )
    except SdistVerificationError as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"verified source distribution: {arguments.sdist.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
