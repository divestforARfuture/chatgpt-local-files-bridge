from __future__ import annotations

from pathlib import Path

import pytest

from src.errors import ConflictError, TooLargeError, WriteDisabledError
from src.service import Limits, LocalFilesService


def test_list_and_read(service: LocalFilesService) -> None:
    listing = service.list_directory("")
    assert {entry["name"] for entry in listing["entries"]} == {"folder", "hello.txt"}
    result = service.read("hello.txt")
    assert result["content"] == "hello world"
    assert result["format"] == "text"


def test_search(service: LocalFilesService) -> None:
    result = service.search("notes")
    assert [item["path"] for item in result["results"]] == ["folder/notes.md"]


def test_write_is_disabled_by_default(service: LocalFilesService) -> None:
    with pytest.raises(WriteDisabledError):
        service.write("new.txt", "blocked")


def test_write_overwrite_and_backup(workspace: Path, tmp_path: Path) -> None:
    service = LocalFilesService(workspace, tmp_path / "state", write_enabled=True)
    created = service.write("new.txt", "first")
    assert created["path"] == "new.txt"
    with pytest.raises(ConflictError):
        service.write("new.txt", "second")
    service.write("new.txt", "second", overwrite=True)
    assert (workspace / "new.txt").read_text(encoding="utf-8") == "second"
    backups = list((tmp_path / "state" / "backups").rglob("new.txt"))
    assert backups and backups[0].read_text(encoding="utf-8") == "first"


def test_delete_creates_backup(workspace: Path, tmp_path: Path) -> None:
    service = LocalFilesService(workspace, tmp_path / "state", write_enabled=True)
    result = service.delete("hello.txt")
    assert result["backup"]
    assert not (workspace / "hello.txt").exists()
    assert list((tmp_path / "state" / "backups").rglob("hello.txt"))


def test_read_limit_is_enforced(workspace: Path, tmp_path: Path) -> None:
    limits = Limits(max_read_bytes=4)
    service = LocalFilesService(workspace, tmp_path / "state", limits=limits)
    with pytest.raises(TooLargeError):
        service.read("hello.txt")


def test_audit_log_omits_contents(service: LocalFilesService) -> None:
    service.read("hello.txt")
    log = (service.state_dir / "audit.jsonl").read_text(encoding="utf-8")
    assert "hello world" not in log
    assert '"operation":"read"' in log
