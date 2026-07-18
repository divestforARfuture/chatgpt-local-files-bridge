from __future__ import annotations

import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from .errors import TooLargeError


class BackupManager:
    def __init__(self, backup_root: Path, *, max_bytes: int = 100 * 1024 * 1024) -> None:
        self.backup_root = backup_root
        self.max_bytes = max_bytes
        self.backup_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _size(path: Path) -> int:
        if path.is_file() or path.is_symlink():
            return path.stat().st_size
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())

    def backup(self, source: Path, relative_path: str) -> Path | None:
        if not source.exists() and not source.is_symlink():
            return None
        size = self._size(source)
        if size > self.max_bytes:
            raise TooLargeError(
                "Backup exceeds the configured size limit.",
                details={"size": size, "limit": self.max_bytes},
            )
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        destination = self.backup_root / stamp / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, destination, symlinks=True)
        else:
            shutil.copy2(source, destination, follow_symlinks=False)
        return destination


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
