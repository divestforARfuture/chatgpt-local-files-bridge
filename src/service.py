from __future__ import annotations

import fnmatch
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .audit import AuditLog
from .backups import BackupManager, atomic_write_text
from .errors import (
    AccessDeniedError,
    ConflictError,
    NotFoundError,
    TooLargeError,
    WriteDisabledError,
)
from .extractors import extract_text
from .security import PathPolicy


@dataclass(slots=True)
class Limits:
    max_read_bytes: int = 10 * 1024 * 1024
    max_write_bytes: int = 5 * 1024 * 1024
    max_list_entries: int = 500
    max_search_results: int = 200


class LocalFilesService:
    def __init__(
        self,
        root: Path,
        state_dir: Path,
        *,
        write_enabled: bool = False,
        limits: Limits | None = None,
    ) -> None:
        self.root = root.expanduser().resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_dir = state_dir.expanduser().resolve(strict=False)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.write_enabled = write_enabled
        self.limits = limits or Limits()
        self.paths = PathPolicy(self.root)
        self.audit = AuditLog(self.state_dir / "audit.jsonl")
        self.backups = BackupManager(self.state_dir / "backups")

    def _require_write(self) -> None:
        if not self.write_enabled:
            raise WriteDisabledError(
                "Write operations are disabled. Start the bridge in read/write mode to enable them."
            )

    def _check_read_size(self, path: Path) -> None:
        size = path.stat().st_size
        if size > self.limits.max_read_bytes:
            raise TooLargeError(
                "File exceeds the configured read limit.",
                details={"size": size, "limit": self.limits.max_read_bytes},
            )

    def _entry(self, path: Path) -> dict:
        stat = path.lstat()
        return {
            "name": path.name,
            "path": self.paths.relative(path),
            "type": "symlink" if path.is_symlink() else "directory" if path.is_dir() else "file",
            "size": stat.st_size if path.is_file() else None,
            "modified": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        }

    def health(self) -> dict:
        return {
            "ok": True,
            "root": str(self.root),
            "write_enabled": self.write_enabled,
            "limits": {
                "max_read_bytes": self.limits.max_read_bytes,
                "max_write_bytes": self.limits.max_write_bytes,
                "max_list_entries": self.limits.max_list_entries,
            },
        }

    def list_directory(self, raw_path: str = "") -> dict:
        path = self.paths.resolve(raw_path, must_exist=True)
        if not path.is_dir():
            raise ConflictError("Path is not a directory.")
        entries: list[dict] = []
        for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold())):
            if len(entries) >= self.limits.max_list_entries:
                break
            try:
                # Re-run policy checks on each returned item so denied names never leak.
                self.paths.resolve(self.paths.relative(child), must_exist=True)
            except AccessDeniedError:
                continue
            entries.append(self._entry(child))
        self.audit.record("list", path=raw_path, metadata={"count": len(entries)})
        return {"path": self.paths.relative(path), "entries": entries, "truncated": len(entries) >= self.limits.max_list_entries}

    def stat(self, raw_path: str) -> dict:
        path = self.paths.resolve(raw_path, must_exist=True)
        result = self._entry(path)
        self.audit.record("stat", path=raw_path)
        return result

    def read(self, raw_path: str, *, start: int = 0, limit: int | None = None) -> dict:
        path = self.paths.resolve(raw_path, must_exist=True)
        if not path.is_file():
            raise ConflictError("Path is not a regular file.")
        self._check_read_size(path)
        kind, text = extract_text(path)
        start = max(0, int(start))
        if limit is None:
            limit = len(text) - start
        limit = max(0, min(int(limit), self.limits.max_read_bytes))
        sliced = text[start : start + limit]
        self.audit.record("read", path=raw_path, metadata={"characters": len(sliced), "format": kind})
        return {
            "path": self.paths.relative(path),
            "format": kind,
            "content": sliced,
            "start": start,
            "returned": len(sliced),
            "total_characters": len(text),
            "truncated": start + len(sliced) < len(text),
        }

    def search(self, query: str, raw_path: str = "", *, max_results: int | None = None) -> dict:
        base = self.paths.resolve(raw_path, must_exist=True)
        if not base.is_dir():
            raise ConflictError("Search root is not a directory.")
        query = query.strip()
        if not query:
            raise ConflictError("Search query cannot be empty.")
        cap = min(max_results or self.limits.max_search_results, self.limits.max_search_results)
        pattern = query.casefold()
        results: list[dict] = []
        for current, directories, filenames in os.walk(base, followlinks=False):
            current_path = Path(current)
            safe_directories: list[str] = []
            for name in directories:
                candidate = current_path / name
                try:
                    self.paths.resolve(self.paths.relative(candidate), must_exist=True)
                except AccessDeniedError:
                    continue
                safe_directories.append(name)
            directories[:] = safe_directories
            for name in filenames:
                candidate = current_path / name
                relative = self.paths.relative(candidate)
                try:
                    self.paths.resolve(relative, must_exist=True)
                except AccessDeniedError:
                    continue
                if pattern in relative.casefold() or fnmatch.fnmatch(relative.casefold(), pattern):
                    results.append(self._entry(candidate))
                    if len(results) >= cap:
                        self.audit.record("search", path=raw_path, metadata={"query": query, "count": len(results)})
                        return {"query": query, "results": results, "truncated": True}
        self.audit.record("search", path=raw_path, metadata={"query": query, "count": len(results)})
        return {"query": query, "results": results, "truncated": False}

    def make_directory(self, raw_path: str) -> dict:
        self._require_write()
        path = self.paths.resolve(raw_path)
        if path.exists():
            raise ConflictError("Path already exists.")
        path.mkdir(parents=True, exist_ok=False)
        self.audit.record("mkdir", path=raw_path)
        return self._entry(path)

    def write(self, raw_path: str, content: str, *, overwrite: bool = False) -> dict:
        self._require_write()
        encoded = content.encode("utf-8")
        if len(encoded) > self.limits.max_write_bytes:
            raise TooLargeError(
                "Content exceeds the configured write limit.",
                details={"size": len(encoded), "limit": self.limits.max_write_bytes},
            )
        path = self.paths.resolve(raw_path)
        if path.exists() and path.is_dir():
            raise ConflictError("Cannot overwrite a directory with text.")
        if path.exists() and not overwrite:
            raise ConflictError("File already exists; set overwrite=true to replace it.")
        backup = None
        if path.exists():
            backup = self.backups.backup(path, self.paths.relative(path))
        atomic_write_text(path, content)
        self.audit.record("write", path=raw_path, metadata={"bytes": len(encoded), "backup": str(backup) if backup else None})
        return self._entry(path)

    def move(self, source_raw: str, destination_raw: str, *, overwrite: bool = False) -> dict:
        self._require_write()
        source = self.paths.resolve(source_raw, must_exist=True)
        destination = self.paths.resolve(destination_raw)
        if source == self.root:
            raise AccessDeniedError("The workspace root cannot be moved.")
        if destination.exists() and not overwrite:
            raise ConflictError("Destination already exists; set overwrite=true to replace it.")
        backup = None
        if destination.exists():
            backup = self.backups.backup(destination, self.paths.relative(destination))
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        self.audit.record("move", path=source_raw, metadata={"destination": destination_raw, "backup": str(backup) if backup else None})
        return self._entry(destination)

    def delete(self, raw_path: str) -> dict:
        self._require_write()
        path = self.paths.resolve(raw_path, must_exist=True)
        if path == self.root:
            raise AccessDeniedError("The workspace root cannot be deleted.")
        backup = self.backups.backup(path, self.paths.relative(path))
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        self.audit.record("delete", path=raw_path, metadata={"backup": str(backup) if backup else None})
        return {"deleted": raw_path, "backup": str(backup) if backup else None}
