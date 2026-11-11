"""Persistent manifest used for incremental update detection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from . import config
from .fsutil import write_json_atomic


class ManifestError(RuntimeError):
    """The manifest exists but cannot be used."""


@dataclass(frozen=True)
class Manifest:
    path: Path
    entries: Mapping[str, Mapping[str, Any]]

    @classmethod
    def load(cls, path: Path) -> Manifest:
        if not path.exists():
            return cls(path=path, entries={})
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestError(f"cannot read manifest {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ManifestError(f"manifest {path} is not a JSON object")
        schema = payload.get("schema")
        if schema != config.SCHEMA_VERSION:
            raise ManifestError(f"manifest {path} has unsupported schema {schema!r}")
        entries = payload.get("entries", {})
        if not isinstance(entries, dict):
            raise ManifestError(f"manifest {path} has non-object 'entries'")
        for key, value in entries.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                raise ManifestError(f"manifest {path} has malformed entry {key!r}")
        return cls(path=path, entries=entries)

    def contains(self, source_key: str) -> bool:
        return source_key in self.entries

    def with_entry(self, source_key: str, entry: Mapping[str, Any]) -> Manifest:
        updated = dict(self.entries)
        updated[source_key] = dict(entry)
        return replace(self, entries=updated)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": config.SCHEMA_VERSION,
            "entries": {key: self.entries[key] for key in sorted(self.entries)},
        }

    def save(self) -> None:
        write_json_atomic(self.path, self.to_payload())
