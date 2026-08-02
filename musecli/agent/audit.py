"""Append-only local JSONL audit storage for agent runs."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from musecli.utils import ensure_private_dir, ensure_private_file, iso_utc, parse_timestamp, utc_now

from .contracts import TraceEvent

_SCHEMA_VERSION = 1
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class AuditLogError(RuntimeError):
    """Raised when persisted evidence is malformed or inconsistent."""


class JsonlTraceStore:
    """Store each run as a private, append-only JSONL file."""

    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.root = root.expanduser().resolve()
        self._clock = clock

    def record(self, run_id: str, event_type: str, data: Mapping[str, Any]) -> TraceEvent:
        """Append one validated event with the next sequence number."""
        path = self.path_for(run_id)
        event_name = event_type.strip()
        if not event_name:
            raise ValueError("event_type is required")
        existing = self.read(run_id)
        event = TraceEvent(
            schema_version=_SCHEMA_VERSION,
            run_id=run_id,
            sequence=len(existing) + 1,
            timestamp=self._clock(),
            event_type=event_name,
            data=dict(data),
        )
        payload = _event_to_dict(event)
        encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        ensure_private_dir(path.parent)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
        ensure_private_file(path)
        return event

    def read(self, run_id: str) -> list[TraceEvent]:
        """Read and validate all events for one run."""
        events = self.read_path(self.path_for(run_id))
        for event in events:
            if event.run_id != run_id:
                raise AuditLogError(f"run id mismatch at {run_id}.jsonl:{event.sequence}")
        return events

    def read_path(self, path: Path) -> list[TraceEvent]:
        """Read one discovered trace without trusting its filename as metadata."""
        if path.is_symlink():
            raise ValueError("trace path must not be a symbolic link")
        target = path.expanduser().resolve()
        if target.parent != self.root or target.suffix != ".jsonl":
            raise ValueError("trace path must be a JSONL file under the trace root")
        if not target.exists():
            return []
        events: list[TraceEvent] = []
        try:
            with target.open("r", encoding="utf-8") as handle:
                for line_number, raw in enumerate(handle, start=1):
                    try:
                        payload = json.loads(raw)
                        event = _event_from_dict(payload)
                    except (TypeError, ValueError, json.JSONDecodeError) as exc:
                        raise AuditLogError(
                            f"invalid audit event at {target.name}:{line_number}"
                        ) from exc
                    if event.sequence != line_number:
                        raise AuditLogError(f"sequence mismatch at {target.name}:{line_number}")
                    events.append(event)
        except UnicodeError as exc:
            raise AuditLogError(f"invalid audit encoding in {target.name}") from exc
        recorded_ids = {event.run_id for event in events}
        if len(recorded_ids) > 1:
            raise AuditLogError(f"recorded run ids disagree in {target.name}")
        return events

    def path_for(self, run_id: str) -> Path:
        """Return the validated file path for one run identifier."""
        if not is_safe_run_id(run_id):
            raise ValueError("run_id must be a safe local identifier")
        return self.root / f"{run_id}.jsonl"

    def trace_paths(self) -> list[Path]:
        """Discover candidate trace files in stable filename order."""
        if not self.root.exists():
            return []
        return sorted(
            (path for path in self.root.iterdir() if path.suffix == ".jsonl"),
            key=lambda path: path.name,
        )

    def list_run_ids(self) -> list[str]:
        """List stored run identifiers in filename order."""
        return [path.stem for path in self.trace_paths()]


def is_safe_run_id(value: str) -> bool:
    """Return whether a value is safe to use as a local trace filename."""
    return _RUN_ID_PATTERN.fullmatch(value) is not None


def _event_to_dict(event: TraceEvent) -> dict[str, Any]:
    return {
        "schema_version": event.schema_version,
        "run_id": event.run_id,
        "sequence": event.sequence,
        "timestamp": iso_utc(event.timestamp),
        "event_type": event.event_type,
        "data": dict(event.data),
    }


def _event_from_dict(data: Mapping[str, Any]) -> TraceEvent:
    if not isinstance(data, Mapping):
        raise TypeError("audit event must be an object")
    payload = data.get("data")
    if not isinstance(payload, Mapping):
        raise TypeError("audit event data must be an object")
    schema_version = int(data.get("schema_version", 0))
    if schema_version != _SCHEMA_VERSION:
        raise ValueError(f"unsupported audit schema version: {schema_version}")
    return TraceEvent(
        schema_version=schema_version,
        run_id=str(data.get("run_id", "")),
        sequence=int(data.get("sequence", 0)),
        timestamp=parse_timestamp(data.get("timestamp")),
        event_type=str(data.get("event_type", "")),
        data=dict(payload),
    )
