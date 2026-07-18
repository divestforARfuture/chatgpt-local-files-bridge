from __future__ import annotations

from pathlib import Path

from src.app import create_app
from src.service import LocalFilesService


def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert response.get_json()["write_enabled"] is False


def test_list_and_read_endpoints(client) -> None:
    listing = client.get("/list")
    assert listing.status_code == 200
    response = client.get("/read", query_string={"path": "hello.txt"})
    assert response.status_code == 200
    assert response.get_json()["content"] == "hello world"


def test_traversal_returns_403(client) -> None:
    response = client.get("/read", query_string={"path": "../outside.txt"})
    assert response.status_code == 403
    assert response.get_json()["error"] == "access_denied"


def test_write_endpoint_is_blocked_in_read_only_mode(client) -> None:
    response = client.post("/write", json={"path": "new.txt", "content": "blocked"})
    assert response.status_code == 403
    assert response.get_json()["error"] == "write_disabled"


def test_write_endpoint_in_write_mode(workspace: Path, tmp_path: Path) -> None:
    service = LocalFilesService(workspace, tmp_path / "state-write", write_enabled=True)
    app = create_app(service)
    app.config.update(TESTING=True)
    client = app.test_client()
    response = client.post("/write", json={"path": "new.txt", "content": "created"})
    assert response.status_code == 200
    assert (workspace / "new.txt").read_text(encoding="utf-8") == "created"


def test_manifest_and_schema_are_served(client) -> None:
    manifest = client.get("/.well-known/ai-plugin.json")
    assert manifest.status_code == 200
    assert manifest.get_json()["api"]["url"].endswith("/openapi.yaml")
    schema = client.get("/openapi.yaml")
    assert schema.status_code == 200
    assert b"openapi: 3.0.3" in schema.data


def test_no_wildcard_cors_header(client) -> None:
    response = client.get("/health")
    assert response.headers.get("Access-Control-Allow-Origin") != "*"
