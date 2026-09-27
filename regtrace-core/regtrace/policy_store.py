"""
regtrace.policy_store
~~~~~~~~~~~~~~~~~~~~~
Generic PolicySpec store.

Loads PolicySpec objects from JSON files. Validates on load via Pydantic.
No domain-specific logic. Does not know about consent, CRM, refunds, etc.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from regtrace.models.constraint import PolicySpec


class PolicyLoadError(Exception):
    """Raised when a policy file cannot be parsed or fails validation."""


class PolicyStore:
    """
    In-memory store for PolicySpec objects.

    Usage:
        store = PolicyStore()
        store.load_file("policies/P-001.json")
        spec = store.get("P-001")
    """

    def __init__(self) -> None:
        self._specs: dict[str, PolicySpec] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_file(self, path: str | Path) -> PolicySpec:
        """
        Load a single PolicySpec from a JSON file.
        Raises PolicyLoadError on missing file, bad JSON, or schema violation.
        """
        p = Path(path)
        try:
            raw = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise PolicyLoadError(f"Policy file not found: {path}")
        except OSError as exc:
            raise PolicyLoadError(f"Cannot read {path}: {exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PolicyLoadError(f"Invalid JSON in {path}: {exc}") from exc

        try:
            spec = PolicySpec.model_validate(data)
        except ValidationError as exc:
            raise PolicyLoadError(f"Schema error in {path}:\n{exc}") from exc

        if spec.policy_id in self._specs:
            # Overwrite is intentional (reload semantics)
            pass
        self._specs[spec.policy_id] = spec
        return spec

    def load_directory(self, path: str | Path) -> list[PolicySpec]:
        """
        Load all *.json files in a directory as PolicySpec objects.
        Raises PolicyLoadError on the first file that fails.
        """
        d = Path(path)
        if not d.is_dir():
            raise PolicyLoadError(f"Not a directory: {path}")
        loaded: list[PolicySpec] = []
        for json_file in sorted(d.glob("*.json")):
            loaded.append(self.load_file(json_file))
        return loaded

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get(self, policy_id: str) -> PolicySpec:
        """Return the PolicySpec for the given ID. Raises KeyError if absent."""
        try:
            return self._specs[policy_id]
        except KeyError:
            raise KeyError(f"Policy not found: {policy_id!r}")

    def all(self) -> list[PolicySpec]:
        """Return all loaded PolicySpec objects."""
        return list(self._specs.values())
