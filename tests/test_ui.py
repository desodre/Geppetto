import pytest
from lxml import etree

from geppetto import Bounds, By, Children, Widget, WidgetNotFoundError, WindowDump

from .conftest import DUMP


@pytest.fixture
def dump() -> WindowDump:
    return WindowDump(DUMP)


class TestBounds:
    def test_geometry(self):
        b = Bounds("[100,200][500,300]")
        assert (b.center, b.width, b.height, b.area) == ((300.0, 250.0), 400, 100, 40000)
        assert b.contains(100, 300) and not b.contains(99, 250)

    @pytest.mark.parametrize("raw", ["100,200][500,300]", "[1,2][3]", "[5,5][1,1]", "[a,b][c,d]"])
    def test_invalid(self, raw):
        with pytest.raises(ValueError):
            Bounds(raw)

    def test_equality(self):
        assert Bounds("[0,0][1,1]") == Bounds("[0,0][1,1]")
        assert Bounds("[0,0][1,1]") != Bounds("[0,0][2,2]")


class TestWidget:
    def test_from_dict_reads_flags_and_bounds(self):
        w = Widget.from_dict({"text": "Ok", "clickable": "TRUE", "bounds": "[0,0][10,10]"})
        assert (w.text, w.clickable, w.enabled, w.bounds) == (
            "Ok",
            True,
            False,
            Bounds("[0,0][10,10]"),
        )

    def test_missing_bounds_is_none(self):
        assert Widget.from_dict({"text": "Ok"}).bounds is None

    def test_from_xml_node_keeps_the_node(self):
        node = etree.fromstring('<node text="A" bounds="[0,0][1,1]"/>')
        assert Widget.from_xml_node(node).node is node

    def test_equality_ignores_flags(self):
        a = Widget.from_dict({"text": "A", "bounds": "[0,0][1,1]", "focused": "true"})
        b = Widget.from_dict({"text": "A", "bounds": "[0,0][1,1]"})
        assert a == b


class TestWindowDump:
    def test_find_by_text_with_apostrophe_and_its_children(self, dump):
        deny = dump.find_widget(By.TEXT, "Don't allow")
        assert deny.id == "com.app:id/deny"
        assert deny.children == []

    def test_children_come_from_the_widget_node(self, dump):
        login = dump.find_widget(By.ID, "com.app:id/login")
        assert [c.class_name for c in login.children] == ["android.widget.TextView"]

    def test_find_by_xpath(self, dump):
        assert dump.find_widget(By.XPATH, "//node[@content-desc='Deny']").text == "Don't allow"

    def test_xpath_that_returns_no_element_is_not_found(self, dump):
        with pytest.raises(WidgetNotFoundError):
            dump.find_widget(By.XPATH, "count(//node)")

    def test_not_found(self, dump):
        with pytest.raises(WidgetNotFoundError):
            dump.find_widget(By.TEXT, "Nope")

    def test_by_widget_is_rejected(self, dump):
        with pytest.raises(ValueError, match="By.WIDGET"):
            dump.find_widget(By.WIDGET, "x")

    def test_set_children_for_a_widget_from_elsewhere(self, dump):
        outside = Widget(
            index="1", text="Login", id="com.app:id/login", class_name="android.widget.Button"
        )
        assert len(dump.set_children(outside)) == 1

    def test_invalid_xml(self):
        with pytest.raises(ValueError):
            _ = WindowDump("<hierarchy").root


def test_children_get_widget(dump):
    login = dump.find_widget(By.ID, "com.app:id/login")
    assert isinstance(login.children, Children)
    assert login.children.get_widget(By.CLASS, "android.widget.TextView").text == "Login"
    assert login.children.get_widget(By.TEXT, "Nope") is None
    with pytest.raises(ValueError):
        login.children.get_widget(By.XPATH, "//node")
