import re
from pathlib import Path, PurePath
from typing import Iterable


SKIP_DIRS = {".git", "vendor", "node_modules", "testdata"}
MAX_FILE_CHARS = 30_000
MAX_LIST_FILES = 200
MAX_SEARCH_RESULTS = 20


def _safe_path(repo_path: str, path: str = "") -> Path:
    parent = Path(repo_path).resolve()
    child = (parent / path).resolve()
    if child != parent and parent not in child.parents:
        raise ValueError("Path traversal not allowed")
    return child


def _validate_glob_pattern(pattern: str) -> None:
    pattern_path = PurePath(pattern)
    if pattern_path.is_absolute() or ".." in pattern_path.parts:
        raise ValueError("Path traversal not allowed")


def _is_skipped(path: Path, repo_root: Path) -> bool:
    rel_parts = path.relative_to(repo_root).parts
    return any(part in SKIP_DIRS for part in rel_parts)


def _normalize_extensions(extensions: Iterable[str] | None) -> set[str] | None:
    if not extensions:
        return None
    return {ext if ext.startswith(".") else f".{ext}" for ext in extensions}


def read_file(repo_path: str, path: str) -> str:
    file_path = _safe_path(repo_path, path)
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    content = file_path.read_text(encoding="utf-8", errors="replace")
    if len(content) > MAX_FILE_CHARS:
        return f"{content[:MAX_FILE_CHARS]}\n...[truncated]"
    return content


def write_file(repo_path: str, path: str, content: str) -> dict:
    file_path = _safe_path(repo_path, path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return {"written": True, "path": path, "bytes": len(content)}


def list_files(
    repo_path: str,
    directory: str = "",
    recursive: bool = False,
    extensions: list[str] | None = None,
) -> list[str]:
    repo_root = Path(repo_path).resolve()
    start_dir = _safe_path(repo_path, directory)
    if not start_dir.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    if not start_dir.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    extension_filter = _normalize_extensions(extensions)
    files: list[str] = []
    candidates = start_dir.rglob("*") if recursive else start_dir.iterdir()

    for candidate in candidates:
        if _is_skipped(candidate, repo_root):
            continue
        relative_path = candidate.relative_to(repo_root).as_posix()
        safe_candidate = _safe_path(repo_path, relative_path)
        if not safe_candidate.is_file():
            continue
        if extension_filter and candidate.suffix not in extension_filter:
            continue
        files.append(relative_path)

    return sorted(files)[:MAX_LIST_FILES]


def search_code(
    repo_path: str,
    pattern: str,
    file_pattern: str = "*.go",
    is_regex: bool = False,
    max_results: int = MAX_SEARCH_RESULTS,
) -> list[dict]:
    repo_root = Path(repo_path).resolve()
    _validate_glob_pattern(file_pattern)
    regex = re.compile(pattern) if is_regex else None
    max_results = min(
        _positive_int(max_results, MAX_SEARCH_RESULTS),
        MAX_SEARCH_RESULTS,
    )
    results: list[dict] = []

    for file_path in repo_root.rglob(file_pattern):
        if len(results) >= max_results:
            break
        if file_path.suffix != ".go" or _is_skipped(file_path, repo_root):
            continue
        relative_path = file_path.relative_to(repo_root).as_posix()
        safe_file_path = _safe_path(repo_path, relative_path)
        if not safe_file_path.is_file():
            continue

        lines = safe_file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for index, line in enumerate(lines):
            if len(results) >= max_results:
                break
            matched = bool(regex.search(line)) if regex else pattern in line
            if not matched:
                continue

            context_start = max(0, index - 2)
            context_end = min(len(lines), index + 3)
            results.append(
                {
                    "file": file_path.relative_to(repo_root).as_posix(),
                    "line_number": index + 1,
                    "line": line.strip(),
                    "context": "\n".join(lines[context_start:context_end]),
                }
            )

    return results


def file_exists(repo_path: str, path: str) -> bool:
    return _safe_path(repo_path, path).exists()


def _positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)
