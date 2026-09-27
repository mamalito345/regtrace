from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from mcp.server import MCPServer
from pydantic import BaseModel, Field


mcp = MCPServer("RegTrace")

adapter_root = Path(__file__).resolve().parent
skill_path = adapter_root / "skills" / "regtrace.md"

ignored_directories = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
}

blocked_file_names = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "credentials.json",
}

blocked_suffixes = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}

readable_suffixes = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".cs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".kts",
    ".sql",
    ".graphql",
    ".proto",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".html",
    ".css",
    ".scss",
    ".vue",
    ".svelte",
    ".md",
    ".txt",
}

max_snapshot_chars = 260_000
max_file_chars = 80_000
max_write_chars = 1_500_000
max_changes_per_call = 40


class FileReplacement(BaseModel):
    path: str = Field(min_length=1)
    content: str


def _repository_root(repo_path: str) -> Path:
    root = Path(repo_path).expanduser().resolve()

    if not root.exists():
        raise ValueError(
            f"Repository does not exist: {root}"
        )

    if not root.is_dir():
        raise ValueError(
            f"Repository path is not a directory: {root}"
        )

    return root


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _safe_repo_path(
    root: Path,
    relative_path: str,
) -> Path:
    candidate = (root / relative_path).resolve()

    if not _is_inside(candidate, root):
        raise ValueError(
            f"Path escapes repository: {relative_path}"
        )

    return candidate


def _blocked_file(path: Path) -> bool:
    name = path.name.lower()

    if name in blocked_file_names:
        return True

    if name.startswith(".env"):
        return True

    if path.suffix.lower() in blocked_suffixes:
        return True

    return False


def _readable_file(path: Path) -> bool:
    return (
        path.is_file()
        and not _blocked_file(path)
        and path.suffix.lower() in readable_suffixes
    )


def _repository_files(root: Path) -> list[Path]:
    files: list[Path] = []

    for directory, dirnames, filenames in os.walk(
        root,
        followlinks=False,
    ):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in ignored_directories
        )

        base = Path(directory)

        for filename in sorted(filenames):
            path = base / filename

            if _readable_file(path):
                files.append(path)

    return sorted(
        files,
        key=lambda path: path.relative_to(root).as_posix(),
    )


def _read_text(path: Path) -> str:
    try:
        text = path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return (
            "[RegTrace could not read this file: "
            f"{exc}]"
        )

    if "\x00" in text:
        return "[Binary content omitted]"

    if len(text) > max_file_chars:
        return (
            text[:max_file_chars]
            + "\n\n[RegTrace truncated this file]"
        )

    return text


def _repository_tree(
    root: Path,
    files: list[Path],
) -> str:
    entries = [
        path.relative_to(root).as_posix()
        for path in files[:4000]
    ]

    if len(files) > 4000:
        entries.append(
            f"... [{len(files) - 4000} more files]"
        )

    return "\n".join(entries)


def _selected_files(
    root: Path,
    all_files: list[Path],
    focus_paths: list[str] | None,
) -> list[Path]:
    if not focus_paths:
        return all_files

    selected: list[Path] = []

    for raw_path in focus_paths:
        target = _safe_repo_path(
            root,
            raw_path,
        )

        if target.is_file():
            if (
                _readable_file(target)
                and target not in selected
            ):
                selected.append(target)

            continue

        if target.is_dir():
            for candidate in all_files:
                if (
                    _is_inside(candidate, target)
                    and candidate not in selected
                ):
                    selected.append(candidate)

    return selected


def _snapshot(
    root: Path,
    focus_paths: list[str] | None,
) -> dict[str, object]:
    all_files = _repository_files(root)

    selected = _selected_files(
        root,
        all_files,
        focus_paths,
    )

    files: list[dict[str, str]] = []
    used_chars = 0
    truncated = False

    for path in selected:
        relative = path.relative_to(root).as_posix()
        content = _read_text(path)

        cost = len(relative) + len(content) + 100

        if used_chars + cost > max_snapshot_chars:
            truncated = True
            break

        files.append(
            {
                "path": relative,
                "content": content,
            }
        )

        used_chars += cost

    return {
        "repository": str(root),
        "repository_tree": _repository_tree(
            root,
            all_files,
        ),
        "files": files,
        "included_file_count": len(files),
        "total_readable_file_count": len(all_files),
        "snapshot_truncated": truncated,
    }


def _skill() -> str:
    if not skill_path.exists():
        raise RuntimeError(
            f"RegTrace skill not found: {skill_path}"
        )

    return skill_path.read_text(
        encoding="utf-8",
        errors="replace",
    )


def _apply_changes(
    root: Path,
    changes: list[FileReplacement],
) -> list[str]:
    if not changes:
        raise ValueError(
            "No file changes were supplied."
        )

    if len(changes) > max_changes_per_call:
        raise ValueError(
            f"A maximum of {max_changes_per_call} files "
            "may be changed in one operation."
        )

    total_chars = sum(
        len(change.content)
        for change in changes
    )

    if total_chars > max_write_chars:
        raise ValueError(
            "Requested changes are too large "
            "for one RegTrace operation."
        )

    pending: list[
        tuple[Path, FileReplacement]
    ] = []

    for change in changes:
        target = _safe_repo_path(
            root,
            change.path,
        )

        if _blocked_file(target):
            raise ValueError(
                "RegTrace refuses to modify "
                f"secret or credential file: {change.path}"
            )

        pending.append(
            (target, change)
        )

    changed_files: list[str] = []

    for target, change in pending:
        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        target.write_text(
            change.content,
            encoding="utf-8",
        )

        changed_files.append(
            target.relative_to(root).as_posix()
        )

    return changed_files


@mcp.tool()
def regtrace_review_plan(
    repo_path: str,
    feature_intent: str,
    proposed_plan: str,
    focus_paths: list[str] | None = None,
) -> dict[str, object]:
    """
    Review Claude's proposed implementation plan before coding.

    The user supplies company/legal policy documents directly in the current
    Claude conversation. Claude must use those documents together with the
    repository returned by this tool and the RegTrace skill.

    Claude should first create its own plan, then call this tool.
    This tool never writes files.
    """

    root = _repository_root(repo_path)

    snapshot = _snapshot(
        root,
        focus_paths,
    )

    return {
        "stage": "pre_implementation_plan_review",
        "feature_intent": feature_intent,
        "proposed_plan": proposed_plan,
        "regtrace_skill": _skill(),
        "instruction": (
            "Use the company and legal policy documents supplied "
            "by the user in this Claude conversation as the policy "
            "source of truth. Review the proposed plan against those "
            "documents and against the actual repository returned here. "
            "Do not write code yet. Identify concrete conflicts, missing "
            "controls, risky data flows, authorization requirements, "
            "retention requirements, logging requirements, security "
            "requirements, or other engineering consequences explicitly "
            "supported by the supplied policies. Revise the implementation "
            "plan before coding. Do not invent policy requirements. "
            "If necessary source files are not included, inspect the "
            "repository_tree and call regtrace_review_plan again with "
            "focus_paths for the relevant files or directories."
        ),
        **snapshot,
    }


@mcp.tool()
def regtrace_review_fix(
    repo_path: str,
    feature_intent: str,
    approved_plan: str = "",
    focus_paths: list[str] | None = None,
    action: Literal["review", "apply"] = "review",
    reason: str = "",
    changes: list[FileReplacement] | None = None,
) -> dict[str, object]:
    """
    Review or modify the actual repository after planning.

    The user supplies company/legal policies directly in the current Claude
    conversation.

    action='review':
        Return actual repository source for policy-aware code review.

    action='apply':
        Apply Claude's complete file replacements to the local repository.

    After every apply operation Claude must call action='review' again.
    """

    root = _repository_root(repo_path)

    if action == "apply":
        changed_files = _apply_changes(
            root,
            changes or [],
        )

        return {
            "stage": "changes_applied",
            "changed_files": changed_files,
            "reason": reason,
            "instruction": (
                "The requested code changes were written to the "
                "repository. Perform a fresh independent policy review "
                "now by calling regtrace_review_fix again with "
                "action='review'."
            ),
        }

    snapshot = _snapshot(
        root,
        focus_paths,
    )

    return {
        "stage": "post_implementation_policy_review",
        "feature_intent": feature_intent,
        "approved_plan": approved_plan,
        "regtrace_skill": _skill(),
        "instruction": (
            "Use the company and legal policy documents supplied "
            "by the user in this Claude conversation as the policy "
            "source of truth. Review the actual source code returned "
            "by RegTrace. Follow behavior across files, helpers, wrappers, "
            "data transformations, authorization checks, external APIs, "
            "storage, logging, and other relevant code paths. Do not judge "
            "only by identifier names. For every issue actually supported "
            "by a supplied policy, identify the policy requirement, exact "
            "file and function/code path, current behavior, conflict, and "
            "minimal correction. Do not invent legal requirements. "
            "If context is incomplete, call this tool again with "
            "focus_paths before reaching a conclusion. If code must change, "
            "prepare complete replacement contents and call action='apply'. "
            "After applying fixes, call action='review' again and review "
            "the resulting implementation from scratch."
        ),
        **snapshot,
    }


if __name__ == "__main__":
    mcp.run()