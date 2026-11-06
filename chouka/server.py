"""本地预览服务：页面先问类型或区，再开一包。只监听本机。"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from chouka.categories import PACK_SIZE, list_categories
from chouka.engine import draw_card
from chouka.errors import ChoukaError
from chouka.paths import load_paths
from chouka.preview import payload_from_draw


def bind_preview_server(root: Path, port: int = 8765) -> ThreadingHTTPServer:
    handler = _handler(root)
    if port == 0:
        return ThreadingHTTPServer(("127.0.0.1", 0), handler)
    last: OSError | None = None
    for candidate in range(port, port + 10):
        try:
            return ThreadingHTTPServer(("127.0.0.1", candidate), handler)
        except OSError as exc:
            last = exc
    raise ChoukaError(f"从 {port} 起的 10 个端口都被占用: {last}")


def serve_preview(root: Path | None = None, port: int = 8765) -> None:
    paths = load_paths(root)
    httpd = bind_preview_server(paths.root, port)
    host, bound = httpd.server_address
    print(f"先选类型，再开一包：http://{host}:{bound}/", flush=True)
    print("在浏览器打开这个地址。关掉这个命令即停止。", flush=True)
    if not paths.preview_html.is_file():
        print(f"找不到预览页: {paths.preview_html}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()


def _handler(root: Path):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                page = load_paths(root).preview_html
                if not page.is_file():
                    self._json(404, {"error": f"找不到预览页: {page}"})
                    return
                body = page.read_bytes()
                self._bytes(200, "text/html; charset=utf-8", body)
                return
            if parsed.path == "/favicon.ico":
                self.send_response(204)
                self._common()
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if parsed.path == "/api/categories":
                deck = (parse_qs(parsed.query).get("deck") or [""])[0]
                try:
                    self._json(200, list_categories(deck, root=root))
                except ChoukaError as exc:
                    self._json(400, {"error": str(exc)})
                return
            self._json(404, {"error": "没有这个地址"})

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/api/draw":
                self._json(404, {"error": "没有这个地址"})
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                self._json(400, {"error": "请求不完整"})
                return
            if length < 0 or length > 10000:
                self._json(400, {"error": "请求太大"})
                return
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json(400, {"error": "请求必须是 JSON"})
                return
            if not isinstance(body, dict):
                self._json(400, {"error": "请求必须是 JSON 对象"})
                return
            try:
                payload = _draw_pack(root, body)
            except ChoukaError as exc:
                self._json(400, {"error": str(exc)})
                return
            except Exception:
                self._json(500, {"error": "开包失败"})
                return
            self._json(200, payload)

        def log_message(self, fmt: str, *args) -> None:
            return

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._bytes(status, "application/json; charset=utf-8", body)

        def _bytes(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self._common()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _common(self) -> None:
            self.send_header("Cache-Control", "no-store")

    return Handler


def _draw_pack(root: Path, body: dict) -> dict:
    deck = body.get("deck")
    category = body.get("category")
    if not isinstance(category, str) or not category.strip():
        raise ChoukaError("先选择类型或区")
    constraints: dict = {}
    if deck == "lunch":
        constraints["tag"] = category.strip()
    elif deck == "bili_featured":
        constraints["zone"] = category.strip()
    else:
        raise ChoukaError("deck 只能是 lunch 或 bili_featured")
    result = draw_card(
        {"deck": deck, "count": PACK_SIZE, "constraints": constraints},
        root=root,
    )
    payload = payload_from_draw(result)
    payload["pity"] = result.get("pity")
    return payload
