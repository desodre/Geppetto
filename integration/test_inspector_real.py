"""The inspector against a real device: record a tap and replay the generated script."""

import json
import threading
import time
import urllib.request

import pytest

from geppetto import Device
from geppetto.inspector import InspectorServer

SETTINGS = "com.android.settings"


@pytest.fixture(scope="module")
def dev(serial, tmp_path_factory):
    return Device(serial, output_dir=tmp_path_factory.mktemp("results"), log_to_console=False)


@pytest.fixture
def server(dev):
    srv = InspectorServer(dev, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def _get(srv, path):
    with urllib.request.urlopen(srv.url + path, timeout=60) as r:
        return r.read()


def _post(srv, path, body):
    req = urllib.request.Request(
        srv.url + path, json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def test_recorded_tap_replays(dev, server):
    dev.kill_app(SETTINGS)
    dev.open_app(SETTINGS)
    assert dev.await_for_activity(SETTINGS, timeout=20)
    assert _get(server, "api/screenshot")[:4] == b"\x89PNG"

    # Settings resumes before its list is drawn: wait for a clickable item with a stable selector.
    alvo, clicaveis = None, []
    for _ in range(20):
        nodes = json.loads(_get(server, "api/hierarchy"))["nodes"]
        clicaveis = [n for n in nodes if n["attrs"].get("clickable") == "true"]
        alvo = next(
            (
                n
                for n in clicaveis
                if n["attrs"].get("package") == SETTINGS
                and not n["selector"]["fragile"]
                and n["bounds"]
                and n["bounds"][1] > 0
            ),
            None,
        )
        if alvo is not None:
            break
        time.sleep(1)
    resumo = "\n".join(
        f"{n['attrs'].get('package')} {n['attrs'].get('class')} {n['bounds']} -> {n['selector']}"
        for n in clicaveis
    )
    assert alvo is not None, f"no clickable Settings element with a stable selector:\n{resumo}"
    linha = _post(server, "api/action", {"type": "click", "node": alvo["index"], "record": True})[
        "code"
    ]
    assert linha.startswith("device.click(device.await_widget(")

    script = json.loads(_get(server, "api/code"))["script"]
    # Back to where the recording started, then run the generated program as a user would.
    dev.kill_app(SETTINGS)
    dev.open_app(SETTINGS)
    assert dev.await_for_activity(SETTINGS, timeout=20)
    exec(compile(script, "recorded_flow.py", "exec"), {"__name__": "__main__"})
    dev.kill_app(SETTINGS)
