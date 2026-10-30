"""Turn the actions done in the inspector into a runnable Python script."""

from __future__ import annotations

from dataclasses import dataclass, field

from .selectors import Selector

#: Android key codes the inspector's buttons send.
KEYS = {"back": 4, "home": 3, "enter": 66, "app_switch": 187}


@dataclass
class Recorder:
    """Accumulates steps; :meth:`script` renders them as a standalone program."""

    serial: str
    steps: list[str] = field(default_factory=list)

    def click(self, selector: Selector) -> str:
        aviso = "  # fragile: position-based selector" if selector.fragile else ""
        return self._add(f"device.click({selector.code()}){aviso}")

    def type_text(self, text: str) -> str:
        return self._add(f"device.input_text({text!r})")

    def key(self, name: str) -> str:
        if name not in KEYS:
            raise ValueError(f"unknown key {name!r}; use one of {', '.join(KEYS)}")
        return self._add(f"device.key_event({KEYS[name]})  # {name}")

    def open_app(self, package: str) -> str:
        return self._add(f"device.open_app({package!r})")

    def _add(self, line: str) -> str:
        self.steps.append(line)
        return line

    def clear(self) -> None:
        self.steps.clear()

    def script(self) -> str:
        corpo = "\n".join(f"    {passo}" for passo in self.steps) or "    pass"
        return (
            '"""Recorded with `geppetto inspect`."""\n\n'
            "from geppetto import By, Device\n\n\n"
            "def main() -> None:\n"
            f"    device = Device({self.serial!r})\n"
            f"{corpo}\n\n\n"
            'if __name__ == "__main__":\n'
            "    main()\n"
        )
