"""Pick the most stable selector for a node of a UI dump.

Order of preference, each one only if it matches **exactly one** node in the dump:

1. ``resource-id``            → ``By.ID``
2. ``content-desc``           → ``By.CONTENT_DESC``
3. ``text``                   → ``By.TEXT``
4. ``resource-id`` + ``text`` → XPath (lists where every row shares the id)
5. a container by the unique text/content-desc of a descendant → XPath (the usual Android row:
   a clickable LinearLayout with no attributes of its own and the label in a child TextView)
6. relative to the closest ancestor with a unique ``resource-id`` → XPath
7. position among nodes of the same class → indexed XPath (last resort, flagged ``fragile``)

``By.ID``/``TEXT``/``CONTENT_DESC`` match the first node with that value, so a non-unique value
would silently point at another element: uniqueness is what makes a selector safe to record.
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from ..models.by import By


@dataclass(frozen=True)
class Selector:
    by: By
    value: str
    #: Indexed XPath: breaks when the screen gains or loses similar elements.
    fragile: bool = False

    def code(self, device: str = "device") -> str:
        """Python expression that finds the widget with Geppetto's API."""
        return f"{device}.await_widget(By.{self.by.name}, {self.value!r})"


def xpath_literal(value: str) -> str:
    """Quote *value* for XPath 1.0 (which has no escape character)."""
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    partes = value.split("'")
    return "concat(" + ', "\'", '.join(f"'{p}'" for p in partes) + ")"


def _count(root: etree._Element, xpath: str) -> int:
    result = root.xpath(f"count({xpath})")
    return int(result) if isinstance(result, float) else 0


def _attr_xpath(attrs: dict[str, str]) -> str:
    condicoes = " and ".join(f"@{k}={xpath_literal(v)}" for k, v in attrs.items())
    return f"//node[{condicoes}]"


def recommend(root: etree._Element, node: etree._Element) -> Selector:
    """The most stable selector that finds *node* (and only it) in the dump *root*."""
    rid = node.get("resource-id", "")
    desc = node.get("content-desc", "")
    text = node.get("text", "")

    for by, attr, value in (
        (By.ID, "resource-id", rid),
        (By.CONTENT_DESC, "content-desc", desc),
        (By.TEXT, "text", text),
    ):
        if value and _count(root, _attr_xpath({attr: value})) == 1:
            return Selector(by, value)

    if rid and text:
        xpath = _attr_xpath({"resource-id": rid, "text": text})
        if _count(root, xpath) == 1:
            return Selector(By.XPATH, xpath)

    por_descendente = _by_descendant(root, node)
    if por_descendente is not None:
        return por_descendente

    proprio = _own_xpath(node)
    for ancestral in node.iterancestors("node"):
        arid = ancestral.get("resource-id", "")
        if arid and _count(root, _attr_xpath({"resource-id": arid})) == 1:
            xpath = _attr_xpath({"resource-id": arid}) + proprio
            if _count(root, xpath) == 1:
                return Selector(By.XPATH, xpath)

    classe = node.get("class", "")
    iguais = root.xpath(_attr_xpath({"class": classe}) if classe else "//node")
    posicao = next(i for i, n in enumerate(iguais, start=1) if n is node)
    base = _attr_xpath({"class": classe}) if classe else "//node"
    return Selector(By.XPATH, f"({base})[{posicao}]", fragile=True)


def _own_xpath(node: etree._Element) -> str:
    """``//node[...]`` with the node's distinguishing attributes (used under an ancestor)."""
    for attrs in (
        {"resource-id": node.get("resource-id", ""), "text": node.get("text", "")},
        {"content-desc": node.get("content-desc", "")},
        {"class": node.get("class", "")},
    ):
        attrs = {k: v for k, v in attrs.items() if v}
        if attrs:
            return _attr_xpath(attrs)
    return "//node"


def _by_descendant(root: etree._Element, node: etree._Element) -> Selector | None:
    """``//node[<own class/clickable> and .//node[@text=...]]`` matching only *node*."""
    proprio = {"class": node.get("class", "")}
    if node.get("clickable") == "true":
        proprio["clickable"] = "true"
    condicoes = " and ".join(f"@{k}={xpath_literal(v)}" for k, v in proprio.items() if v)
    for filho in node.iterdescendants("node"):
        for attr in ("text", "content-desc"):
            valor = filho.get(attr, "")
            if not valor:
                continue
            interno = f".//node[@{attr}={xpath_literal(valor)}]"
            xpath = f"//node[{condicoes} and {interno}]" if condicoes else f"//node[{interno}]"
            if _count(root, xpath) == 1:
                return Selector(By.XPATH, xpath)
    return None
