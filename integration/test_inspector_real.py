"""The inspector against a real device: record a tap and replay the generated script."""

import json
import os
import threading
import time
import urllib.request

import pytest

from geppetto.inspector import InspectorServer

from .conftest import make_device

SETTINGS = "com.android.settings"


@pytest.fixture(scope="module")
def dev(serial, tmp_path_factory, pytestconfig):
    device = make_device(pytestconfig, serial, tmp_path_factory.mktemp("results"))
    try:
        yield device
    finally:
        device.close()


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


def test_recorded_tap_replays(dev, server, pytestconfig, monkeypatch):
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
    assert linha.startswith("device.get(By.") and linha.rstrip().endswith(".click()")

    script = json.loads(_get(server, "api/code"))["script"]
    # Release the inspector's backend session before replaying the standalone script
    # (Android allows one active UiAutomation session at a time), then restore Settings.
    dev.kill_app(SETTINGS)
    dev.open_app(SETTINGS)
    assert dev.await_for_activity(SETTINGS, timeout=20)
    if carlo_bin := (
        pytestconfig.getoption("geppetto_carlo_binary") or os.environ.get("GEPPETTO_CARLO_BINARY")
    ):
        monkeypatch.setenv("GEPPETTO_CARLO_BINARY", str(carlo_bin))
    dev.close()
    exec(compile(script, "recorded_flow.py", "exec"), {"__name__": "__main__"})
    dev.kill_app(SETTINGS)
