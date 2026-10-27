import json
import threading
import urllib.request
from urllib.error import HTTPError

import pytest
from lxml import etree

from geppetto import By, WindowDump
from geppetto.inspector import InspectorServer, Recorder, Selector, recommend, xpath_literal

# A list where every row shares the resource-id, duplicated texts, quotes and a node with nothing.
LISTA = """<hierarchy>
<node index="0" class="android.widget.FrameLayout" resource-id="com.app:id/root" bounds="[0,0][1080,2000]">
  <node index="0" class="android.widget.TextView" resource-id="com.app:id/title" text="Settings" bounds="[0,0][1080,100]"/>
  <node index="1" class="androidx.recyclerview.widget.RecyclerView" resource-id="com.app:id/list" bounds="[0,100][1080,1900]">
    <node index="0" class="android.widget.TextView" resource-id="com.app:id/row" text="Wi-Fi" bounds="[0,100][1080,200]"/>
    <node index="1" class="android.widget.TextView" resource-id="com.app:id/row" text="Bluetooth" bounds="[0,200][1080,300]"/>
    <node index="2" class="android.widget.TextView" resource-id="com.app:id/row" text="Don't &quot;disturb&quot;" bounds="[0,300][1080,400]"/>
    <node index="3" class="android.widget.ImageView" content-desc="More options" bounds="[0,400][100,500]"/>
    <node index="4" class="android.widget.TextView" resource-id="com.app:id/row" text="Settings" bounds="[0,500][1080,600]"/>
  </node>
  <node index="2" class="android.widget.Button" text="OK" bounds="[0,1900][540,2000]"/>
  <node index="3" class="android.widget.Button" text="OK" bounds="[540,1900][1080,2000]"/>
  <node index="4" class="android.view.View" bounds="[0,0][1,1]"/>
  <node index="6" class="android.widget.LinearLayout" clickable="true" bounds="[0,1700][1080,1800]">
    <node index="0" class="android.widget.TextView" text="Network &amp; internet" bounds="[40,1710][900,1790]"/>
  </node>
  <node index="7" class="android.widget.LinearLayout" clickable="true" bounds="[0,1600][1080,1700]">
    <node index="0" class="android.widget.TextView" text="Connected devices" bounds="[40,1610][900,1690]"/>
  </node>
  <node index="5" class="android.widget.TextView" resource-id="com.app:id/footer" text="Don't &quot;disturb&quot;" bounds="[0,1800][1080,1900]"/>
</node>
</hierarchy>"""


@pytest.fixture
def root():
    return etree.fromstring(LISTA.encode())


def _find(root, text):
    return root.xpath(f"//node[@text={xpath_literal(text)}]")[0]


def test_unique_id_wins(root):
    assert recommend(root, root.xpath("//node[@resource-id='com.app:id/title']")[0]) == Selector(
        By.ID, "com.app:id/title"
    )


def test_unique_text_beats_a_shared_id(root):
    assert recommend(root, _find(root, "Bluetooth")) == Selector(By.TEXT, "Bluetooth")


def test_shared_id_and_repeated_text_use_both(root):
    linha = root.xpath("//node[@resource-id='com.app:id/row' and @text='Settings']")[0]
    selector = recommend(root, linha)
    assert selector == Selector(
        By.XPATH, "//node[@resource-id='com.app:id/row' and @text='Settings']"
    )


def test_clickable_row_is_found_by_its_label(root):
    """The usual Android row: a clickable container without attributes, the text in a child."""
    linha = root.xpath("//node[@clickable='true' and .//node[@text='Network & internet']]")[0]
    selector = recommend(root, linha)
    assert not selector.fragile
    assert selector.value == (
        "//node[@class='android.widget.LinearLayout' and @clickable='true' "
        "and .//node[@text='Network & internet']]"
    )
    assert root.xpath(selector.value) == [linha]


def test_content_desc(root):
    node = root.xpath("//node[@content-desc='More options']")[0]
    assert recommend(root, node) == Selector(By.CONTENT_DESC, "More options")


def test_quotes_in_text_are_valid_xpath(root):
    texto = 'Don\'t "disturb"'
    linha = root.xpath(f"//node[@resource-id='com.app:id/row' and @text={xpath_literal(texto)}]")[0]
    selector = recommend(root, linha)  # text repeated in the footer: id + text, with concat()
    assert selector.by is By.XPATH and "concat(" in selector.value
    assert root.xpath(selector.value) == [linha]


def test_duplicate_buttons_get_a_fragile_position(root):
    segundo = root.xpath("//node[@text='OK']")[1]
    selector = recommend(root, segundo)
    assert selector.fragile and selector.value.endswith("[2]")


def test_every_recommended_selector_finds_exactly_its_node():
    """The property that matters: the code we generate points at the element the user picked."""
    dump = WindowDump(LISTA)
    for node in dump.root.iter("node"):
        selector = recommend(dump.root, node)
        if selector.by is By.XPATH:
            assert dump.root.xpath(selector.value) == [node], selector
        else:
            achado = dump.find_widget(selector.by, selector.value)
            assert achado.node is node, selector


def test_xpath_literal():
    assert xpath_literal("abc") == "'abc'"
    assert xpath_literal("it's") == '"it\'s"'
    expr = xpath_literal("a'b\"c")
    assert etree.fromstring("<r/>").xpath(expr) == "a'b\"c"


def test_recorded_script_runs(monkeypatch):
    rec = Recorder("SERIAL1")
    rec.click(Selector(By.ID, "com.app:id/login"))
    rec.type_text("olá mundo")
    rec.key("back")
    rec.click(Selector(By.XPATH, "(//node[@class='x'])[2]", fragile=True))
    script = rec.script()
    assert "# fragile" in script and "device.key_event(4)  # back" in script

    feito = []

    class FakeDevice:
        def __init__(self, serial):
            feito.append(("device", serial))

        def await_widget(self, by, value):
            return (by, value)

        def click(self, alvo):
            feito.append(("click", alvo))

        def input_text(self, text):
            feito.append(("text", text))

        def key_event(self, code):
            feito.append(("key", code))

    import geppetto

    monkeypatch.setattr(geppetto, "Device", FakeDevice)
    namespace: dict[str, object] = {"__name__": "__main__"}
    exec(compile(script, "recorded_flow.py", "exec"), namespace)
    assert feito == [
        ("device", "SERIAL1"),
        ("click", (By.ID, "com.app:id/login")),
        ("text", "olá mundo"),
        ("key", 4),
        ("click", (By.XPATH, "(//node[@class='x'])[2]")),
    ]


def test_unknown_key():
    with pytest.raises(ValueError):
        Recorder("S").key("volume")


# ── HTTP server ──────────────────────────────────────────────────────


@pytest.fixture
def servidor(device, adb_run):
    adb_run.responder = lambda argv: b"\x89PNG" if "exec-out" in argv else ""
    server = InspectorServer(device, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


def _get(server, path):
    with urllib.request.urlopen(server.url + path.lstrip("/"), timeout=5) as r:
        return r.headers.get("Content-Type"), r.read()


def _post(server, path, body):
    req = urllib.request.Request(
        server.url + path.lstrip("/"),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def test_server_serves_page_screenshot_and_hierarchy(servidor):
    tipo, page = _get(servidor, "/")
    assert tipo.startswith("text/html") and b"Geppetto Inspector" in page
    assert _get(servidor, "/api/screenshot")[1] == b"\x89PNG"
    dados = json.loads(_get(servidor, "/api/hierarchy")[1])
    login = next(
        n
        for n in dados["nodes"]
        if n["attrs"].get("text") == "Login" and n["attrs"]["class"].endswith("Button")
    )
    assert login["bounds"] == [100, 400, 500, 500]
    assert login["selector"]["code"] == "device.await_widget(By.ID, 'com.app:id/login')"


def test_server_records_actions(servidor, adb_run):
    nodes = json.loads(_get(servidor, "/api/hierarchy")[1])["nodes"]
    login = next(n for n in nodes if n["attrs"].get("resource-id") == "com.app:id/login")

    assert _post(
        servidor, "/api/action", {"type": "click", "node": login["index"], "record": True}
    )["code"] == ("device.click(device.await_widget(By.ID, 'com.app:id/login'))")
    assert _post(servidor, "/api/action", {"type": "text", "text": "a b", "record": True})[
        "code"
    ] == ("device.input_text('a b')")
    assert (
        _post(servidor, "/api/action", {"type": "key", "key": "back", "record": False})["code"]
        is None
    )
    assert adb_run.shell_lines()[-3:] == [
        "input tap 300.0 450.0",
        "input text a%sb",
        "input keyevent 4",
    ]

    script = json.loads(_get(servidor, "/api/code")[1])["script"]
    assert "com.app:id/login" in script and "keyevent" not in script
    _post(servidor, "/api/code/clear", {})
    assert json.loads(_get(servidor, "/api/code")[1])["steps"] == []


def test_server_rejects_bad_actions(servidor):
    with pytest.raises(HTTPError) as erro:
        _post(servidor, "/api/action", {"type": "explode"})
    assert erro.value.code == 400


def test_cli_inspect_parser():
    from geppetto.cli import build_parser

    args = build_parser().parse_args(["inspect", "-s", "S", "--port", "0", "--no-browser"])
    assert (args.serial, args.port, args.no_browser, args.host) == ("S", 0, True, "127.0.0.1")
