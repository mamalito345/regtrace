"""
regtrace.repository
~~~~~~~~~~~~~~~~~~~
Repository-level Python source analysis.
"""
from __future__ import annotations

import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Collection

from regtrace.codefacts import (
    AnalysisError,
    CodeFactSet,
    PythonCodeFactsProvider,
)


_DEFAULT_IGNORED: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        ".env",
        "env",
        "__pycache__",
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
    }
)


class RepositoryAnalysisError(Exception):
    """Raised when the repository path cannot be analysed."""


@dataclass(frozen=True)
class RepositoryAnalysisIssue:
    filename: str
    reason: str


@dataclass
class RepositoryAnalysis:
    analyzed_files: tuple[str, ...]
    issues: tuple[RepositoryAnalysisIssue, ...]
    fact_sets: tuple[CodeFactSet, ...]


class RepositoryAnalyzer:
    def __init__(
        self,
        ignored_directories: Collection[str] | None = None,
    ) -> None:
        extra = (
            set(ignored_directories)
            if ignored_directories
            else set()
        )

        self._ignored = _DEFAULT_IGNORED | extra
        self._provider = PythonCodeFactsProvider()

    def analyze(
        self,
        repository_path: str | Path,
    ) -> RepositoryAnalysis:
        root = Path(
            repository_path
        ).expanduser().resolve()

        if not root.exists():
            raise RepositoryAnalysisError(
                f"Repository path does not exist: {root}"
            )

        if not root.is_dir():
            raise RepositoryAnalysisError(
                f"Repository path is not a directory: {root}"
            )

        fact_sets: list[CodeFactSet] = []
        issues: list[RepositoryAnalysisIssue] = []
        analyzed: list[str] = []

        for path in sorted(
            self._collect_python_files(root)
        ):
            relative = path.relative_to(
                root
            ).as_posix()

            try:
                with tokenize.open(path) as handle:
                    source = handle.read()

                fact_set = self._provider.analyze_source(
                    source,
                    filename=relative,
                )

            except (
                AnalysisError,
                OSError,
                UnicodeError,
                SyntaxError,
            ) as exc:
                issues.append(
                    RepositoryAnalysisIssue(
                        filename=relative,
                        reason=str(exc),
                    )
                )

                continue

            fact_sets.append(fact_set)
            analyzed.append(relative)

        return RepositoryAnalysis(
            analyzed_files=tuple(analyzed),
            issues=tuple(issues),
            fact_sets=tuple(fact_sets),
        )

    def _collect_python_files(
        self,
        root: Path,
    ) -> list[Path]:
        results: list[Path] = []

        for item in root.iterdir():
            if item.is_symlink():
                continue

            if item.is_dir():
                if not self._should_ignore_directory(
                    item.name
                ):
                    results.extend(
                        self._collect_python_files(
                            item
                        )
                    )

            elif (
                item.is_file()
                and item.suffix == ".py"
            ):
                results.append(item)

        return results

    def _should_ignore_directory(
        self,
        name: str,
    ) -> bool:
        return (
            name in self._ignored
            or name.endswith(".egg-info")
        )