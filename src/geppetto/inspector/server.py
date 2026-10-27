"""Local web inspector: the device screen with its hierarchy, selectors and a code recorder.

Standard library only (``http.server``). It listens on ``127.0.0.1`` by default: the page can tap
and type on the device, so exposing it on the network is an explicit choice (``host=``).

Routes::

    GET  /                  the page (inspector/static/index.html)
    GET  /api/screenshot    PNG of the screen
    GET  /api/hierarchy     {"serial", "nodes": [{index, parent, depth, bounds, attrs, selector}]}
    POST /api/action        {"type": "click", "node": i} | {"type": "tap", "x", "y"}
                            | {"type": "text", "text"} | {"type": "key", "key"}; "record": bool
    GET  /api/code          {"script": "..."}
    POST /api/code/clear
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import TYPE_CHECKING, Any

from lxml import etree

from ..ui.bounds import Bounds
from .recorder import KEYS, Recorder
from .selectors import recommend

if TYPE_CHECKING:
    from ..device import Device

logger = logging.getLogger("geppetto.inspector")


@dataclass
class _Estado:
    device: Device
    recorder: Recorder
    lock: threading.Lock = field(default_factory=threading.Lock)
    #: Nodes of the last /api/hierarchy, so actions refer to what the user saw.
    nodes: list[etree._Element] = field(default_factory=list)


def hierarchy_json(xml: str) -> tuple[list[dict[str, Any]], list[etree._Element]]:
    """Flatten a UI dump into JSON nodes (pre-order) with bounds and the recommended selector."""
    root = etree.fromstring(xml.encode("utf-8"))
    elementos = list(root.iter("node"))
    indice = {id(n): i for i, n in enumerate(elementos)}
    saida = []
    for i, node in enumerate(elementos):
        pai = node.getparent()
        bounds = node.get("bounds", "")
        caixa = None
        if bounds:
            b = Bounds(bounds)
            caixa = [b.x1, b.y1, b.x2, b.y2]
        selector = recommend(root, node)
        saida.append(
            {
                "index": i,
                "parent": indice.get(id(pai)) if pai is not None else None,
                "depth": sum(1 for _ in node.iterancestors("node")),
                "bounds": caixa,
                "attrs": dict(node.attrib),
                "selector": {
                    "by": selector.by.name,
                    "value": selector.value,
                    "code": selector.code(),
                    "fragile": selector.fragile,
                },
            }
        )
    return saida, elementos


def _handler(estado: _Estado) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "GeppettoInspector"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 — stdlib name
            logger.debug("%s " + format, self.address_string(), *args)

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data: Any, status: int = HTTPStatus.OK) -> None:
            self._send(status, json.dumps(data).encode(), "application/json")

        def _erro(self, status: int, mensagem: str) -> None:
            self._json({"error": mensagem}, status)

        def do_GET(self) -> None:  # noqa: N802 — stdlib name
            try:
                if self.path == "/":
                    page = resources.files(__package__).joinpath("static/index.html").read_bytes()
                    self._send(HTTPStatus.OK, page, "text/html; charset=utf-8")
                elif self.path.startswith("/api/screenshot"):
                    with estado.lock:
                        png = estado.device.adb.exec_out("screencap -p")
                    self._send(HTTPStatus.OK, png, "image/png")
                elif self.path == "/api/hierarchy":
                    with estado.lock:
                        nodes, elementos = hierarchy_json(str(estado.device.get_window_dump()))
                        estado.nodes = elementos
                    self._json({"serial": estado.device.serial, "nodes": nodes})
                elif self.path == "/api/code":
                    self._json({"script": estado.recorder.script(), "steps": estado.recorder.steps})
                else:
                    self._erro(HTTPStatus.NOT_FOUND, "not found")
            except Exception as erro:  # noqa: BLE001 — the page shows it; the server keeps running
                logger.exception("inspector GET %s", self.path)
                self._erro(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(erro).__name__}: {erro}")

        def do_POST(self) -> None:  # noqa: N802 — stdlib name
            try:
                tamanho = int(self.headers.get("Content-Length") or 0)
                dados = json.loads(self.rfile.read(tamanho) or b"{}") if tamanho else {}
                if self.path == "/api/action":
                    self._json({"code": self._acao(dados)})
                elif self.path == "/api/code/clear":
                    estado.recorder.clear()
                    self._json({"script": estado.recorder.script()})
                else:
                    self._erro(HTTPStatus.NOT_FOUND, "not found")
            except (KeyError, ValueError, IndexError, TypeError) as erro:
                self._erro(HTTPStatus.BAD_REQUEST, str(erro))
            except Exception as erro:  # noqa: BLE001
                logger.exception("inspector POST %s", self.path)
                self._erro(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(erro).__name__}: {erro}")

        def _acao(self, dados: dict[str, Any]) -> str | None:
            tipo, gravar = dados["type"], bool(dados.get("record"))
            device, recorder = estado.device, estado.recorder
            with estado.lock:
                if tipo == "click":
                    node = estado.nodes[int(dados["node"])]
                    device.click(Bounds(node.get("bounds", "")))
                    root = node.getroottree().getroot()
                    return recorder.click(recommend(root, node)) if gravar else None
                if tipo == "tap":
                    x, y = float(dados["x"]), float(dados["y"])
                    device.click((x, y))
                    return recorder._add(f"device.click(({x:.0f}, {y:.0f}))") if gravar else None
                if tipo == "text":
                    texto = str(dados["text"])
                    device.input_text(texto)
                    return recorder.type_text(texto) if gravar else None
                if tipo == "key":
                    nome = str(dados["key"])
                    if nome not in KEYS:
                        raise ValueError(f"unknown key {nome!r}")
                    device.key_event(KEYS[nome])
                    return recorder.key(nome) if gravar else None
            raise ValueError(f"unknown action {tipo!r}")

    return Handler


class InspectorServer:
    """The inspector for one device.

    ``serve_forever()`` blocks; call ``shutdown()`` from another thread.
    """

    def __init__(self, device: Device, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.estado = _Estado(device, Recorder(device.serial))
        self.httpd = ThreadingHTTPServer((host, port), _handler(self.estado))
        self.httpd.daemon_threads = True

    @property
    def recorder(self) -> Recorder:
        return self.estado.recorder

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address[:2]
        nome = host.decode() if isinstance(host, bytes) else str(host)
        return f"http://{'127.0.0.1' if nome in ('0.0.0.0', '') else nome}:{port}/"

    def serve_forever(self) -> None:
        self.httpd.serve_forever(poll_interval=0.2)

    def shutdown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
