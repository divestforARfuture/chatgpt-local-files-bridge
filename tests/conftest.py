from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app import create_app
from src.service import LocalFilesService


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "hello.txt").write_text("hello world", encoding="utf-8")
    (root / "folder").mkdir()
    (root / "folder" / "notes.md").write_text("bridge notes", encoding="utf-8")
    return root


@pytest.fixture()
def service(workspace: Path, tmp_path: Path) -> LocalFilesService:
    return LocalFilesService(workspace, tmp_path / "state", write_enabled=False)


@pytest.fixture()
def client(service: LocalFilesService):
    app = create_app(service)
    app.config.update(TESTING=True)
    return app.test_client()
