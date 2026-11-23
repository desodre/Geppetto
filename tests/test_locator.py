"""Locators resolve on XML dumps, actions wait and build the right adb commands, expect retries."""

from __future__ import annotations

import re

import pytest
from lxml import etree

from geppetto import By, DeviceTimeoutError, ExpectationError, Locator, expect
from geppetto.locator.query import Filter, Find, Has, Match, Nth, Query, Relative, Side, Within

# A settings-like screen: a title, two rows sharing a resource-id (label + switch each), a
# disabled button, a hidden (zero-size) node and a field with text.
SCREEN = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.app"
        content-desc="" enabled="true" bounds="[0,0][1080,2000]">
    <node index="0" text="Settings" resource-id="com.app:id/title" class="android.widget.TextView"
          package="com.app" content-desc="" enabled="true" bounds="[40,100][400,180]" />
    <node index="1" text="" resource-id="com.app:id/row" class="android.widget.LinearLayout"
          package="com.app" content-desc="" clickable="true" enabled="true"
          bounds="[0,200][1080,320]">
      <node index="0" text="Wi-Fi" resource-id="com.app:id/label" class="android.widget.TextView"
            package="com.app" content-desc="" enabled="true" bounds="[40,220][500,300]" />
      <node index="1" text="" resource-id="com.app:id/switch" class="android.widget.Switch"
            package="com.app" content-desc="Wi-Fi switch" checkable="true" checked="true"
            enabled="true" bounds="[900,230][1040,290]" />
    </node>
    <node index="2" text="" resource-id="com.app:id/row" class="android.widget.LinearLayout"
          package="com.app" content-desc="" clickable="true" enabled="true"
          bounds="[0,340][1080,460]">
      <node index="0" text="Bluetooth" resource-id="com.app:id/label"
            class="android.widget.TextView"
            package="com.app" content-desc="" enabled="true" bounds="[40,360][500,440]" />
      <node index="1" text="" resource-id="com.app:id/switch" class="android.widget.Switch"
            package="com.app" content-desc="Bluetooth switch" checkable="true" checked="false"
            enabled="true" bounds="[900,370][1040,430]" />
    </node>
    <node index="3" text="Reset" resource-id="com.app:id/reset" class="android.widget.Button"
          package="com.app" content-desc="" clickable="true" enabled="false"
          bounds="[40,500][400,580]" />
    <node index="4" text="Ghost" resource-id="com.app:id/ghost" class="android.widget.TextView"
          package="com.app" content-desc="" enabled="true" bounds="[0,0][0,0]" />
    <node index="5" text="old value" resource-id="com.app:id/field" class="android.widget.EditText"
          package="com.app" content-desc="" clickable="true" enabled="true" focused="true"
          bounds="[40,600][1040,680]" />
  </node>
</hierarchy>
"""


@pytest.fixture
def root():
    return etree.fromstring(SCREEN.encode())


@pytest.fixture
def screen(device, monkeypatch):
    """The fake device showing SCREEN, with sleeps removed so timeouts are instant."""
    device._u2.dump = SCREEN
    monkeypatch.setattr("geppetto.locator.locator.time.sleep", lambda s: None)
    monkeypatch.setattr("geppetto.locator.assertions.time.sleep", lambda s: None)
    return device


def q(by, value, exact=True):
    return Query((Find(Match(by, value, exact)),))


def texts(nodes):
    return [n.get("text") or n.get("content-desc") for n in nodes]


# ── Query resolution (pure) ──────────────────────────────────────────


def test_find_by_each_strategy(root):
    assert texts(q(By.TEXT, "Wi-Fi").resolve(root)) == ["Wi-Fi"]
    assert len(q(By.ID, "com.app:id/row").resolve(root)) == 2
    assert len(q(By.CLASS, "android.widget.Switch").resolve(root)) == 2
    assert texts(q(By.CONTENT_DESC, "Bluetooth switch").resolve(root)) == ["Bluetooth switch"]
    assert texts(q(By.XPATH, "//node[@resource-id='com.app:id/title']").resolve(root)) == [
        "Settings"
    ]


def test_substring_and_regex(root):
    assert texts(q(By.TEXT, "blue", exact=False).resolve(root)) == ["Bluetooth"]
    assert texts(q(By.TEXT, re.compile(r"^(Wi-Fi|Bluetooth)$")).resolve(root)) == [
        "Wi-Fi",
        "Bluetooth",
    ]
    assert texts(q(By.CONTENT_DESC, re.compile("switch$")).resolve(root)) == [
        "Wi-Fi switch",
        "Bluetooth switch",
    ]


def test_xpath_returning_a_number_is_no_match(root):
    assert q(By.XPATH, "count(//node)").resolve(root) == []


def test_descendant_and_filter(root):
    rows = q(By.ID, "com.app:id/row")
    switches = rows.then(Find(Match(By.CLASS, "android.widget.Switch")))
    assert texts(switches.resolve(root)) == ["Wi-Fi switch", "Bluetooth switch"]
    # A chained XPath is relative to each candidate, even when written with `//`.
    assert texts(rows.then(Find(Match(By.XPATH, "//node[@checked='true']"))).resolve(root)) == [
        "Wi-Fi switch"
    ]
    assert texts(
        q(By.CLASS, "android.widget.TextView")
        .then(Filter(Match(By.TEXT, "Blue", False)))
        .resolve(root)
    ) == ["Bluetooth"]


def test_has_keeps_rows_with_a_matching_descendant(root):
    rows = q(By.ID, "com.app:id/row").then(Has(q(By.TEXT, "Bluetooth")))
    found = rows.resolve(root)
    assert len(found) == 1 and found[0].get("index") == "2"


def test_within_restricts_to_the_anchor(root):
    row = q(By.ID, "com.app:id/row").then(Has(q(By.TEXT, "Wi-Fi")))
    inside = q(By.CLASS, "android.widget.Switch").then(Within(row))
    assert texts(inside.resolve(root)) == ["Wi-Fi switch"]


def test_relative_sides_are_sorted_by_distance(root):
    title = q(By.TEXT, "Settings")
    below = q(By.CLASS, "android.widget.TextView").then(Relative(Side.BELOW, title))
    assert texts(below.resolve(root)) == ["Wi-Fi", "Bluetooth"]
    wifi = q(By.TEXT, "Wi-Fi")
    right = q(By.CLASS, "android.widget.Switch").then(Relative(Side.RIGHT_OF, wifi))
    assert texts(right.resolve(root)) == ["Wi-Fi switch", "Bluetooth switch"][:1] + [
        "Bluetooth switch"
    ]
    above = q(By.CLASS, "android.widget.TextView").then(Relative(Side.ABOVE, q(By.TEXT, "Reset")))
    assert texts(above.resolve(root))[0] == "Bluetooth"
    left = q(By.CLASS, "android.widget.TextView").then(
        Relative(Side.LEFT_OF, q(By.CONTENT_DESC, "Bluetooth switch"))
    )
    assert texts(left.resolve(root))[0] == "Bluetooth"
    # No anchor on screen: nothing is relative to it.
    assert q(By.TEXT, "Wi-Fi").then(Relative(Side.BELOW, q(By.TEXT, "Nope"))).resolve(root) == []


def test_nth_and_out_of_range(root):
    labels = q(By.ID, "com.app:id/label")
    assert texts(labels.then(Nth(-1)).resolve(root)) == ["Bluetooth"]
    assert labels.then(Nth(5)).resolve(root) == []


def test_match_rejects_bad_input():
    with pytest.raises(ValueError):
        Match(By.WIDGET, "x")
    with pytest.raises(TypeError):
        Match(By.XPATH, re.compile("x"))
    with pytest.raises(TypeError):
        Match(By.TEXT, 3)  # type: ignore[arg-type]


def test_query_describes_itself():
    query = q(By.TEXT, "Wi-Fi").then(Find(Match(By.CLASS, "Switch", False)))
    assert str(query) == "get(By.TEXT, 'Wi-Fi').get(By.CLASS, 'Switch', exact=False)"


# ── Locator through Device ───────────────────────────────────────────


def test_device_get_is_lazy_and_chainable(screen):
    loc = screen.get(By.ID, "com.app:id/row").filter(has=screen.get(By.TEXT, "Wi-Fi"))
    assert isinstance(loc, Locator)
    assert screen._u2.selectors == []  # nothing dumped yet
    switch = loc.get(By.CLASS, "android.widget.Switch")
    assert switch.count() == 1 and switch.is_checked()
    assert screen.get(By.ID, "com.app:id/row").nth(1).get(By.ID, "com.app:id/label").text == (
        "Bluetooth"
    )
    assert screen.get(By.ID, "com.app:id/label").last.widget().text == "Bluetooth"
    assert (
        screen.get(By.CLASS, "android.widget.TextView")
        .below(screen.get(By.TEXT, "Settings"))
        .first.text
        == "Wi-Fi"
    )
    assert (
        screen.get(By.TEXT, "Wi-Fi").within(screen.get(By.ID, "com.app:id/row").first).count() == 1
    )


def test_filter_argument_validation(screen):
    with pytest.raises(TypeError):
        screen.get(By.TEXT, "x").filter(By.TEXT)
    with pytest.raises(TypeError):
        screen.get(By.TEXT, "x").filter()


def test_chained_xpath_cannot_escape_its_base(screen):
    rows = screen.get(By.ID, "com.app:id/row")
    # `(//...)[1]` does not start with `//`, so it is evaluated from the document root.
    assert rows.get(By.XPATH, "(//node[@text='Settings'])[1]").count() == 0
    assert [w.text for w in rows.get(By.XPATH, "(//node[@text='Wi-Fi'])[1]").all()] == ["Wi-Fi"]


def test_filter_has_xpath_cannot_escape_its_candidate(screen):
    rows = screen.get(By.ID, "com.app:id/row")
    bluetooth = rows.filter(has=screen.get(By.XPATH, "(//node[@text='Bluetooth'])[1]"))
    assert bluetooth.count() == 1
    assert bluetooth.get(By.ID, "com.app:id/label").text == "Bluetooth"


def test_widget_has_children_from_the_same_dump(screen):
    row = screen.get(By.ID, "com.app:id/row").first.widget()
    assert row.children is not None and [c.text for c in row.children] == ["Wi-Fi", ""]


def test_click_taps_the_center_once_visible_and_enabled(screen, adb_run):
    screen.get(By.TEXT, "Wi-Fi").click()
    assert adb_run.shell_lines()[-1] == "input tap 270.0 260.0"


def test_click_waits_for_the_element_to_appear(screen, monkeypatch, adb_run):
    dumps = iter(["<hierarchy/>", "<hierarchy/>", SCREEN])
    monkeypatch.setattr(screen._u2, "dump_hierarchy", lambda: next(dumps))
    screen.get(By.TEXT, "Bluetooth").click(timeout=5)
    assert adb_run.shell_lines()[-1] == "input tap 270.0 400.0"


def test_click_times_out_with_the_last_state(screen):
    with pytest.raises(DeviceTimeoutError, match="0 matches"):
        screen.get(By.TEXT, "Nope").click(timeout=0)
    with pytest.raises(DeviceTimeoutError, match="enabled=False"):
        screen.get(By.TEXT, "Reset").click(timeout=0)
    with pytest.raises(DeviceTimeoutError, match=r"bounds=\[0,0\]\[0,0\]"):
        screen.get(By.TEXT, "Ghost").click(timeout=0)


def test_default_timeout_comes_from_the_device(screen):
    screen.default_timeout = 0
    with pytest.raises(DeviceTimeoutError, match="Timeout after 0s"):
        screen.get(By.TEXT, "Nope").widget()


def test_long_press_and_swipe_to(screen, adb_run):
    screen.get(By.TEXT, "Wi-Fi").long_press(duration=0.5)
    assert adb_run.shell_lines()[-1] == "input touchscreen swipe 270.0 260.0 270.0 260.0 500"
    screen.get(By.TEXT, "Wi-Fi").swipe_to(screen.get(By.TEXT, "Bluetooth"), duration=0.3)
    assert adb_run.shell_lines()[-1] == "input touchscreen swipe 270.0 260.0 270.0 400.0 300"
    screen.get(By.TEXT, "Wi-Fi").swipe_to((10, 20))
    assert adb_run.shell_lines()[-1] == "input touchscreen swipe 270.0 260.0 10 20 1000"


def test_fill_clears_the_current_text_first(screen, adb_run):
    screen.get(By.ID, "com.app:id/field").fill("new text")
    assert adb_run.shell_lines()[-4:] == [
        "input tap 540.0 640.0",
        "input keyevent 123",
        "input keyevent " + " ".join(["67"] * len("old value") + ["112"] * len("old value")),
        "input text new%stext",
    ]


def test_fill_on_an_empty_field_only_types(screen, adb_run, caplog):
    with caplog.at_level("INFO", logger="geppetto"):
        screen.get(By.CONTENT_DESC, "Wi-Fi switch").fill("s3cr3t", log_text=False)
    assert adb_run.shell_lines()[-2:] == ["input tap 970.0 260.0", "input text s3cr3t"]
    assert "s3cr3t" not in caplog.text


def test_type_text_clicks_then_types(screen, adb_run):
    screen.get(By.ID, "com.app:id/field").type_text("more")
    assert adb_run.shell_lines()[-2:] == ["input tap 540.0 640.0", "input text more"]


def test_wait_for_states(screen):
    assert screen.get(By.TEXT, "Wi-Fi").wait_for("visible").text == "Wi-Fi"
    assert screen.get(By.TEXT, "Nope").wait_for("hidden") is None
    assert screen.get(By.TEXT, "Ghost").wait_for("hidden") is None
    assert screen.get(By.TEXT, "Reset").wait_for("attached").enabled is False
    with pytest.raises(DeviceTimeoutError):
        screen.get(By.TEXT, "Reset").wait_for("enabled", timeout=0)
    with pytest.raises(ValueError):
        screen.get(By.TEXT, "Reset").wait_for("sparkly")


def test_booleans_do_not_wait(screen):
    assert screen.get(By.TEXT, "Nope").is_visible() is False
    assert screen.get(By.TEXT, "Ghost").is_visible() is False
    assert screen.get(By.TEXT, "Wi-Fi").is_visible() is True
    assert screen.get(By.TEXT, "Reset").is_enabled() is False
    assert screen.get(By.CONTENT_DESC, "Bluetooth switch").is_checked() is False


def test_locator_str_reads_like_code(screen):
    loc = screen.get(By.ID, "com.app:id/row").filter(has=screen.get(By.TEXT, "Wi-Fi")).nth(0)
    assert str(loc) == (
        "device.get(By.ID, 'com.app:id/row').filter(has=get(By.TEXT, 'Wi-Fi')).nth(0)"
    )
    assert repr(loc).startswith("Locator(device.get(")


# ── expect() ─────────────────────────────────────────────────────────


def test_expect_passes_on_the_current_state(screen):
    title = screen.get(By.ID, "com.app:id/title")
    expect(title).to_be_visible()
    expect(title).to_have_text("Settings")
    expect(title).to_have_text(" settings ".strip().title())
    expect(title).to_contain_text("sett")
    expect(title).to_have_text(re.compile(r"^Sett"))
    expect(screen.get(By.TEXT, "Nope")).to_be_hidden()
    expect(screen.get(By.TEXT, "Ghost")).to_be_hidden()
    expect(screen.get(By.TEXT, "Reset")).to_be_disabled()
    expect(screen.get(By.TEXT, "Wi-Fi")).to_be_enabled()
    expect(screen.get(By.CONTENT_DESC, "Wi-Fi switch")).to_be_checked()
    expect(screen.get(By.CONTENT_DESC, "Bluetooth switch")).to_be_checked(checked=False)
    expect(screen.get(By.CONTENT_DESC, "Bluetooth switch")).to_have_content_desc("Bluetooth switch")
    expect(screen.get(By.ID, "com.app:id/field")).to_be_focused()
    expect(screen.get(By.ID, "com.app:id/row")).to_have_count(2)
    expect(screen.get(By.TEXT, "Nope")).to_have_count(0)


def test_expect_not(screen):
    expect(screen.get(By.TEXT, "Nope")).not_.to_be_visible()
    expect(screen.get(By.TEXT, "Reset")).not_.to_be_enabled()
    expect(screen.get(By.ID, "com.app:id/title")).not_.to_have_text("Other")
    with pytest.raises(ExpectationError, match="not to be visible"):
        expect(screen.get(By.TEXT, "Wi-Fi"), timeout=0).not_.to_be_visible()


def test_negated_state_assertions_need_a_match(screen):
    missing = expect(screen.get(By.TEXT, "Nope"), timeout=0).not_
    with pytest.raises(ExpectationError, match="not to be enabled.*last seen: 0 matches"):
        missing.to_be_enabled()
    with pytest.raises(ExpectationError, match="not to be disabled.*last seen: 0 matches"):
        missing.to_be_disabled()
    with pytest.raises(ExpectationError, match="last seen: 0 matches"):
        missing.to_have_text("Other")
    # "No element" is still a valid state for visibility and count.
    missing.to_be_visible()
    missing.to_have_count(1)


def test_expect_retries_until_it_holds(screen, monkeypatch):
    dumps = iter(["<hierarchy/>", SCREEN.replace(">Settings<", ">Loading<"), SCREEN])
    monkeypatch.setattr(screen._u2, "dump_hierarchy", lambda: next(dumps))
    expect(screen.get(By.ID, "com.app:id/title"), timeout=5).to_have_text("Settings")


def test_expect_failure_shows_expectation_and_last_state(screen):
    with pytest.raises(ExpectationError) as info:
        expect(screen.get(By.ID, "com.app:id/title"), timeout=0).to_have_text("Other")
    message = str(info.value)
    assert "to be text 'Other'" in message and "last seen: text 'Settings'" in message
    with pytest.raises(ExpectationError, match="last seen: 0 matches"):
        expect(screen.get(By.TEXT, "Nope")).to_be_visible(timeout=0)
    with pytest.raises(ExpectationError, match="to be 1 match .*last seen: 2 matches"):
        expect(screen.get(By.ID, "com.app:id/row"), timeout=0).to_have_count(1)
    with pytest.raises(ExpectationError, match="text containing 'zzz'"):
        expect(screen.get(By.ID, "com.app:id/title"), timeout=0).to_contain_text("zzz")


def test_expectation_error_is_an_assertion_error(screen):
    with pytest.raises(AssertionError):
        expect(screen.get(By.TEXT, "Nope"), timeout=0).to_be_visible()


def test_expect_timeout_falls_back_to_the_device(screen):
    screen.default_timeout = 0
    with pytest.raises(ExpectationError, match=r"waited 0s"):
        expect(screen.get(By.TEXT, "Nope")).to_be_visible()
