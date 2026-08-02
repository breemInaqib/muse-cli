#!/usr/bin/env python3
"""Deterministically verify the museCLI runtime wheel."""

from __future__ import annotations

import argparse
import configparser
import re
import zipfile
from email.parser import Parser
from pathlib import Path, PurePosixPath
from typing import Optional

_EXPECTED_ENTRY_POINTS = {
    "muse": "musecli.cli:app",
    "muse-code": "musecli.code_cli:app",
}
_EXPECTED_RUNTIME_DEPENDENCIES = {"textual", "typer"}
_FORBIDDEN_PREFIXES = ("docs/", "scripts/", "tests/")


class WheelVerificationError(RuntimeError):
    """Raised when a built wheel does not match the runtime package contract."""


def verify_wheel(wheel_path: Path, *, source_root: Path) -> None:
    """Verify runtime modules, metadata, entry points, and private-file exclusions."""
    if not wheel_path.is_file():
        raise WheelVerificationError(f"wheel not found: {wheel_path}")

    try:
        with zipfile.ZipFile(wheel_path) as archive:
            members = archive.namelist()
            _verify_member_names(members)
            member_set = set(members)
            _verify_runtime_modules(member_set, source_root=source_root)
            metadata_name = _single_member(member_set, ".dist-info/METADATA")
            entry_points_name = _single_member(member_set, ".dist-info/entry_points.txt")
            wheel_metadata_name = _single_member(member_set, ".dist-info/WHEEL")
            _single_member(member_set, ".dist-info/RECORD")
            _verify_metadata(archive.read(metadata_name).decode("utf-8"))
            _verify_entry_points(archive.read(entry_points_name).decode("utf-8"))
            _verify_wheel_metadata(archive.read(wheel_metadata_name).decode("utf-8"))
    except (OSError, UnicodeError, zipfile.BadZipFile) as exc:
        raise WheelVerificationError(f"could not read wheel: {wheel_path.name}") from exc


def _verify_member_names(members: list[str]) -> None:
    if len(members) != len(set(members)):
        raise WheelVerificationError("wheel contains duplicate members")
    for member in members:
        path = PurePosixPath(member)
        if path.is_absolute() or ".." in path.parts:
            raise WheelVerificationError(f"wheel contains unsafe member: {member}")
        if (
            member.startswith(_FORBIDDEN_PREFIXES)
            or member.endswith((".pyc", ".pyo", ".DS_Store"))
            or "__pycache__" in path.parts
        ):
            raise WheelVerificationError(f"wheel contains non-runtime member: {member}")


def _verify_runtime_modules(members: set[str], *, source_root: Path) -> None:
    package_root = source_root / "musecli"
    expected = {
        path.relative_to(source_root).as_posix()
        for path in package_root.rglob("*.py")
        if path.is_file()
    }
    actual = {
        member for member in members if member.startswith("musecli/") and not member.endswith("/")
    }
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        raise WheelVerificationError(f"wheel is missing runtime modules: {', '.join(missing)}")
    if unexpected:
        raise WheelVerificationError(
            f"wheel contains unexpected runtime package files: {', '.join(unexpected)}"
        )


def _single_member(members: set[str], suffix: str) -> str:
    matches = sorted(member for member in members if member.endswith(suffix))
    if len(matches) != 1:
        raise WheelVerificationError(
            f"wheel must contain exactly one {suffix.lstrip('.')}: found {len(matches)}"
        )
    return matches[0]


def _verify_metadata(raw: str) -> None:
    metadata = Parser().parsestr(raw)
    if metadata.get("Name") != "musecli":
        raise WheelVerificationError("wheel metadata name must be musecli")
    if metadata.get("Requires-Python") != ">=3.9":
        raise WheelVerificationError("wheel metadata must require Python >=3.9")
    dependencies = {
        match.group(0).lower().replace("_", "-")
        for requirement in metadata.get_all("Requires-Dist", [])
        if (match := re.match(r"[A-Za-z0-9_.-]+", requirement))
    }
    missing = sorted(_EXPECTED_RUNTIME_DEPENDENCIES - dependencies)
    if missing:
        raise WheelVerificationError(
            f"wheel metadata is missing runtime dependencies: {', '.join(missing)}"
        )


def _verify_entry_points(raw: str) -> None:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(raw)
    if not parser.has_section("console_scripts"):
        raise WheelVerificationError("wheel is missing console_scripts entry points")
    scripts = dict(parser.items("console_scripts"))
    if scripts != _EXPECTED_ENTRY_POINTS:
        raise WheelVerificationError(
            "wheel console scripts do not match the muse and muse-code contract"
        )


def _verify_wheel_metadata(raw: str) -> None:
    metadata = Parser().parsestr(raw)
    if metadata.get("Root-Is-Purelib") != "true":
        raise WheelVerificationError("wheel must install as pure Python")
    if metadata.get("Tag") != "py3-none-any":
        raise WheelVerificationError("wheel tag must be py3-none-any")


def main(argv: Optional[list[str]] = None) -> int:  # noqa: UP045
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, help="Path to the built wheel.")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root used to enumerate runtime Python modules.",
    )
    arguments = parser.parse_args(argv)
    try:
        verify_wheel(
            arguments.wheel.expanduser().resolve(),
            source_root=arguments.source_root.expanduser().resolve(),
        )
    except WheelVerificationError as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"verified wheel: {arguments.wheel.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
