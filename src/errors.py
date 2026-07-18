from __future__ import annotations


class BridgeError(Exception):
    """Base error that can be returned safely as JSON."""

    status_code = 400
    code = "bridge_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        payload = {"error": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class InvalidPathError(BridgeError):
    status_code = 400
    code = "invalid_path"


class AccessDeniedError(BridgeError):
    status_code = 403
    code = "access_denied"


class NotFoundError(BridgeError):
    status_code = 404
    code = "not_found"


class ConflictError(BridgeError):
    status_code = 409
    code = "conflict"


class TooLargeError(BridgeError):
    status_code = 413
    code = "too_large"


class UnsupportedFileError(BridgeError):
    status_code = 415
    code = "unsupported_file"


class WriteDisabledError(BridgeError):
    status_code = 403
    code = "write_disabled"
