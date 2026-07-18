from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from .errors import AccessDeniedError, InvalidPathError, NotFoundError

_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_DENIED_PARTS = {
    ".aws",
    ".azure",
    ".git",
    ".gnupg",
    ".kube",
    ".npmrc",
    ".pypirc",
    ".ssh",
    ".env",
    "credentials",
    "secrets",
}
_DENIED_NAMES = {
    "cookies",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "login data",
    "web data",
}
_DENIED_SUFFIXES = {".key", ".p12", ".pfx", ".pem"}


@dataclass(frozen=True, slots=True)
class PathPolicy:
    root: Path

    def __post_init__(self) -> None:
        resolved = self.root.expanduser().resolve(strict=False)
        object.__setattr__(self, "root", resolved)

    @staticmethod
    def _parts(raw: str) -> list[str]:
        normalized = raw.replace("\\", "/")
        return [part for part in normalized.split("/") if part not in {"", "."}]

    def _validate_raw(self, raw: str) -> list[str]:
        if not isinstance(raw, str):
            raise InvalidPathError("Path must be a string.")
        if "\x00" in raw:
            raise InvalidPathError("NUL bytes are not allowed in paths.")
        if raw.startswith(("/", "\\", "//")):
            raise InvalidPathError("Absolute and UNC paths are not allowed.")
        if _DRIVE_RE.match(raw) or PureWindowsPath(raw).drive:
            raise InvalidPathError("Drive-qualified paths are not allowed.")

        parts = self._parts(raw)
        if any(part == ".." for part in parts):
            raise AccessDeniedError("Parent-directory traversal is not allowed.")
        self._check_sensitive(parts)
        return parts

    @staticmethod
    def _check_sensitive(parts: list[str]) -> None:
        lowered = [part.casefold() for part in parts]
        for part in lowered:
            if part in _DENIED_PARTS or part in _DENIED_NAMES:
                raise AccessDeniedError("Access to sensitive paths is blocked.")
            if Path(part).suffix.casefold() in _DENIED_SUFFIXES:
                raise AccessDeniedError("Access to private-key material is blocked.")

    def resolve(self, raw: str = "", *, must_exist: bool = False) -> Path:
        parts = self._validate_raw(raw)
        candidate = self.root.joinpath(*parts).resolve(strict=False)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise AccessDeniedError("Resolved path escapes the approved workspace.") from exc

        # Resolve existing parents as well, catching junction and symlink escapes for new paths.
        probe = candidate
        while not probe.exists() and probe != self.root:
            probe = probe.parent
        resolved_probe = probe.resolve(strict=False)
        try:
            resolved_probe.relative_to(self.root)
        except ValueError as exc:
            raise AccessDeniedError("A symlink or junction escapes the approved workspace.") from exc

        if must_exist and not candidate.exists():
            raise NotFoundError("Path does not exist.", details={"path": raw})
        return candidate

    def relative(self, path: Path) -> str:
        return path.resolve(strict=False).relative_to(self.root).as_posix()


def ensure_local_bind(host: str) -> str:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("The bridge may only bind to the local loopback interface.")
    return "127.0.0.1"


def default_workspace() -> Path:
    return Path(os.environ.get("CHATGPT_LOCAL_ROOT", Path.home() / "ChatGPT-Workspace"))
