from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_file
from werkzeug.exceptions import HTTPException

from .errors import BridgeError
from .security import default_workspace, ensure_local_bind
from .service import Limits, LocalFilesService

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"


def default_state_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "ChatGPTLocalFiles"
    return Path.home() / ".chatgpt-local-files"


def _json_body() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise BridgeError("JSON request body must be an object.")
    return payload


def create_app(service: LocalFilesService) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = service.limits.max_write_bytes + 1024 * 1024
    app.extensions["local_files_service"] = service

    @app.after_request
    def harden_response(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Deliberately do not add wildcard CORS headers.
        return response

    @app.errorhandler(BridgeError)
    def handle_bridge_error(error: BridgeError):
        service.audit.record("error", success=False, metadata={"code": error.code})
        return jsonify(error.to_dict()), error.status_code

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        return jsonify({"error": "http_error", "message": error.description}), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        app.logger.exception("Unhandled bridge error")
        service.audit.record("error", success=False, metadata={"code": "internal_error"})
        return jsonify({"error": "internal_error", "message": "An internal error occurred."}), 500

    @app.get("/health")
    def health():
        return jsonify(service.health())

    @app.get("/list")
    def list_directory():
        return jsonify(service.list_directory(request.args.get("path", "")))

    @app.get("/stat")
    def stat_path():
        return jsonify(service.stat(request.args.get("path", "")))

    @app.get("/read")
    def read_file():
        start = request.args.get("start", default=0, type=int)
        limit = request.args.get("limit", default=None, type=int)
        return jsonify(service.read(request.args.get("path", ""), start=start, limit=limit))

    @app.get("/search")
    def search_files():
        maximum = request.args.get("max_results", default=None, type=int)
        return jsonify(
            service.search(
                request.args.get("query", ""),
                request.args.get("path", ""),
                max_results=maximum,
            )
        )

    @app.post("/mkdir")
    def make_directory():
        payload = _json_body()
        return jsonify(service.make_directory(str(payload.get("path", "")))), 201

    @app.post("/write")
    def write_file():
        payload = _json_body()
        return jsonify(
            service.write(
                str(payload.get("path", "")),
                str(payload.get("content", "")),
                overwrite=bool(payload.get("overwrite", False)),
            )
        )

    @app.post("/move")
    def move_path():
        payload = _json_body()
        return jsonify(
            service.move(
                str(payload.get("source", "")),
                str(payload.get("destination", "")),
                overwrite=bool(payload.get("overwrite", False)),
            )
        )

    @app.post("/delete")
    def delete_path():
        payload = _json_body()
        return jsonify(service.delete(str(payload.get("path", ""))))

    @app.get("/.well-known/ai-plugin.json")
    def plugin_manifest():
        base = request.host_url.rstrip("/")
        template = json.loads((STATIC_DIR / "ai-plugin.json").read_text(encoding="utf-8"))
        template["api"]["url"] = f"{base}/openapi.yaml"
        template["logo_url"] = f"{base}/icon.svg"
        return jsonify(template)

    @app.get("/openapi.yaml")
    def openapi_schema():
        return send_file(STATIC_DIR / "openapi.yaml", mimetype="application/yaml", max_age=0)

    @app.get("/icon.svg")
    def icon():
        return send_file(STATIC_DIR / "icon.svg", mimetype="image/svg+xml", max_age=0)

    return app


def build_service(args: argparse.Namespace) -> LocalFilesService:
    limits = Limits(
        max_read_bytes=args.max_read_bytes,
        max_write_bytes=args.max_write_bytes,
        max_list_entries=args.max_list_entries,
        max_search_results=args.max_search_results,
    )
    return LocalFilesService(
        Path(args.root),
        Path(args.state_dir),
        write_enabled=args.write,
        limits=limits,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local-only filesystem bridge for ChatGPT Desktop")
    parser.add_argument("--root", default=str(default_workspace()), help="Only directory exposed to ChatGPT")
    parser.add_argument("--state-dir", default=str(default_state_dir()), help="Audit and backup directory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9900)
    parser.add_argument("--write", action="store_true", help="Enable write operations")
    parser.add_argument("--max-read-bytes", type=int, default=10 * 1024 * 1024)
    parser.add_argument("--max-write-bytes", type=int, default=5 * 1024 * 1024)
    parser.add_argument("--max-list-entries", type=int, default=500)
    parser.add_argument("--max-search-results", type=int, default=200)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    host = ensure_local_bind(args.host)
    service = build_service(args)
    app = create_app(service)
    from waitress import serve

    mode = "READ/WRITE" if args.write else "READ ONLY"
    print(f"ChatGPT Local Files Bridge {mode}")
    print(f"Workspace: {service.root}")
    print(f"Listening: http://{host}:{args.port}")
    serve(app, host=host, port=args.port, threads=8, channel_timeout=60)


if __name__ == "__main__":
    main()
