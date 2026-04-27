"""Configuration values and persistence for museCLI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .utils import ensure_private_dir, ensure_private_file

_CONFIG_FILENAME = "config.json"


@dataclass
class AppConfig:
    """Runtime configuration shared across CLI commands."""

    data_dir: Path
    journal_dir: Path

    @classmethod
    def defaults(cls, base_dir: Path | None = None) -> AppConfig:
        """Return default paths for a museCLI install."""
        root = (base_dir or _default_data_dir()).expanduser()
        return cls(
            data_dir=root,
            journal_dir=root / "journal",
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize config for JSON storage."""
        return {
            "data_dir": str(self.data_dir),
            "journal_dir": str(self.journal_dir),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, base_dir: Path | None = None) -> AppConfig:
        """Merge stored values onto defaults."""
        defaults = cls.defaults(base_dir)
        return cls(
            data_dir=_coerce_path(data.get("data_dir"), defaults.data_dir),
            journal_dir=_coerce_path(data.get("journal_dir"), defaults.journal_dir),
        )


def config_path(config: AppConfig) -> Path:
    """Return the config file path under the active data directory."""
    return config.data_dir / _CONFIG_FILENAME


def load_config(base_dir: Path | None = None) -> tuple[AppConfig, bool]:
    """Load config from disk, returning `(config, malformed)`."""
    defaults = AppConfig.defaults(base_dir)
    path = config_path(defaults)
    if not path.exists():
        return defaults, False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return defaults, True
    return AppConfig.from_dict(payload, base_dir=defaults.data_dir), False


def save_config(config: AppConfig) -> Path:
    """Persist config JSON and return the written path."""
    ensure_private_dir(config.data_dir)
    target = config_path(config)
    target.write_text(
        json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    ensure_private_file(target)
    return target


def _coerce_path(value: Any, fallback: Path) -> Path:
    if isinstance(value, Path):
        return value.expanduser()
    if isinstance(value, str) and value.strip():
        return Path(value).expanduser()
    return fallback


def _default_data_dir() -> Path:
    return Path.home() / ".muse"
