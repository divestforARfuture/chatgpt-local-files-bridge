from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.errors import AccessDeniedError, InvalidPathError, NotFoundError
from src.security import PathPolicy, ensure_local_bind


def test_rejects_parent_traversal(workspace: Path) -> None:
    policy = PathPolicy(workspace)
    with pytest.raises(AccessDeniedError):
        policy.resolve("../outside.txt")
    with pytest.raises(AccessDeniedError):
        policy.resolve("folder\\..\\..\\outside.txt")


def test_rejects_absolute_and_drive_paths(workspace: Path) -> None:
    policy = PathPolicy(workspace)
    with pytest.raises(InvalidPathError):
        policy.resolve("/etc/passwd")
    with pytest.raises(InvalidPathError):
        policy.resolve(r"C:\\Windows\\System32")
    with pytest.raises(InvalidPathError):
        policy.resolve(r"\\server\\share\\file.txt")


def test_rejects_sensitive_paths(workspace: Path) -> None:
    policy = PathPolicy(workspace)
    for raw in (".env", ".ssh/id_rsa", "private.pem", ".git/config"):
        with pytest.raises(AccessDeniedError):
            policy.resolve(raw)


def test_missing_path_raises_not_found(workspace: Path) -> None:
    with pytest.raises(NotFoundError):
        PathPolicy(workspace).resolve("missing.txt", must_exist=True)


def test_symlink_escape_is_rejected(workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    link = workspace / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable on this platform")
    with pytest.raises(AccessDeniedError):
        PathPolicy(workspace).resolve("escape/secret.txt")


def test_bind_is_loopback_only() -> None:
    assert ensure_local_bind("127.0.0.1") == "127.0.0.1"
    assert ensure_local_bind("localhost") == "127.0.0.1"
    with pytest.raises(RuntimeError):
        ensure_local_bind("0.0.0.0")
