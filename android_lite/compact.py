"""Turn an Android UI hierarchy (UIAutomator XML) into a short, index-addressable text list.

The goal is token economy: a model reads one line per actionable or informative
element instead of the ~20 raw attributes per node that UIAutomator exposes.

Line format (1-based index, flags glued to the index):
    ``12t Redactar``            tappable
    ``3e Para: "ana@x.com"``    editable text field (current value quoted)
    ``8t[x] Wi-Fi``             checkable, checked (``[ ]`` = unchecked)
    ``5t* Principal``           selected (tabs, chips)
    ``9 Batería 32 %``          plain text (informative, not tappable)
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import re
import xml.etree.ElementTree as ET

MAX_LABEL = 60
MAX_ITEMS = 80

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
# Windows that never help a task: the on-screen keyboard (typing goes through the
# clipboard, not keys) and accessibility overlays.
_SKIPPED_WINDOW_TYPES = {"input_method", "accessibility_overlay"}
_SYSTEM_PACKAGES = {"com.android.systemui"}
_EDITABLE_CLASSES = ("EditText", "AutoCompleteTextView", "SearchView")


@dataclass
class Item:
    """One line of the compact screen."""

    label: str
    bounds: tuple[int, int, int, int]
    package: str
    tappable: bool = False
    editable: bool = False
    checked: bool | None = None  # None: not checkable
    selected: bool = False
    value: str = ""  # current text of an editable field
    extra: list[str] = field(default_factory=list)  # texts of non-interactive children
    fallback: bool = False  # label made up from resource-id or position

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2

    @property
    def area(self) -> int:
        x1, y1, x2, y2 = self.bounds
        return max(0, x2 - x1) * max(0, y2 - y1)

    def flags(self) -> str:
        out = "e" if self.editable else ("t" if self.tappable else "")
        if self.checked is not None:
            out += "[x]" if self.checked else "[ ]"
        if self.selected:
            out += "*"
        return out

    def text(self) -> str:
        if self.editable:
            return f'{self.label}: "{self.value}"' if self.value else self.label
        return self.label


@dataclass
class Screen:
    """Compact view of the current screen."""

    package: str
    items: list[Item]
    scrollable: bool
    width: int
    height: int
    truncated: int = 0

    def render(self) -> str:
        head = f"[{self.package}] {len(self.items)} elementos"
        if self.scrollable:
            head += " · desplazable"
        lines = [head] + [f"{i}{it.flags()} {it.text()}" for i, it in enumerate(self.items, 1)]
        if self.truncated:
            lines.append(f"(+{self.truncated} más; desliza para verlos)")
        return "\n".join(lines)

    def find(self, label: str) -> int | None:
        """1-based index of the only item with this label, else None."""
        hits = [i for i, it in enumerate(self.items, 1) if it.label == label]
        return hits[0] if len(hits) == 1 else None


def _clean(s: str | None) -> str:
    """Collapse whitespace and the empty ', ,' runs Gmail-style descriptions contain."""
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(\s*,\s*)+", ", ", s)
    return s.strip(" ,")


def _truncate(s: str) -> str:
    return s if len(s) <= MAX_LABEL else s[: MAX_LABEL - 1] + "…"


def _bounds(node: ET.Element) -> tuple[int, int, int, int] | None:
    m = _BOUNDS_RE.search(node.get("bounds", ""))
    return tuple(int(v) for v in m.groups()) if m else None  # type: ignore[return-value]


def _is_true(node: ET.Element, attr: str) -> bool:
    return node.get(attr) == "true"


def _position(bounds: tuple[int, int, int, int], width: int, height: int) -> str:
    x, y = (bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2
    v = "arriba" if y < height / 3 else ("centro" if y < 2 * height / 3 else "abajo")
    h = "izq" if x < width / 3 else ("centro" if x < 2 * width / 3 else "der")
    return v if v == h == "centro" else f"{v}-{h}"


def _resource_name(node: ET.Element) -> str:
    rid = node.get("resource-id", "").split("/")[-1]
    return rid.replace("_", " ").strip()


def parse_screen(xml: str) -> Screen:
    """Parse UIAutomator XML into a compact :class:`Screen`."""
    root = ET.fromstring(xml)
    width = height = 0
    for node in root.iter("node"):
        b = _bounds(node)
        if b:
            width, height = max(width, b[2]), max(height, b[3])

    items: list[Item] = []
    scrollable_pkgs: set[str] = set()

    def walk(node: ET.Element, window_type: str, owner: Item | None) -> None:
        window_type = node.get("window-type") or window_type
        if window_type in _SKIPPED_WINDOW_TYPES or node.get("visible-to-user") == "false":
            return
        b = _bounds(node)
        on_screen = b is not None and b[2] > b[0] and b[3] > b[1] and b[2] > 0 and b[3] > 0
        pkg = node.get("package", "")
        cls = node.get("class", "")
        if on_screen and _is_true(node, "scrollable"):
            scrollable_pkgs.add(pkg)

        editable = cls.endswith(_EDITABLE_CLASSES)
        checkable = _is_true(node, "checkable")
        interactive = on_screen and (
            _is_true(node, "clickable") or _is_true(node, "long-clickable") or editable or checkable
        )
        text, desc = _clean(node.get("text")), _clean(node.get("content-desc"))

        if interactive:
            assert b is not None
            item = Item(
                label="",
                bounds=b,
                package=pkg,
                tappable=True,
                editable=editable,
                checked=_is_true(node, "checked") if checkable else None,
                selected=_is_true(node, "selected"),
            )
            if editable:
                hint = _clean(node.get("hint"))
                item.label = hint or desc or _resource_name(node)
                # Some fields report their hint as text while empty.
                item.value = "•••" if _is_true(node, "password") and text else ("" if text == hint else text)
            else:
                item.label = text or desc
            items.append(item)
            for child in node:
                walk(child, window_type, item)
            if not item.label or item.extra:
                parts = [item.label] if item.label else []
                parts += [e for e in item.extra if e not in item.label]
                item.label = " · ".join(parts)
            if not item.label:
                item.label = _resource_name(node) or f"icono {_position(b, width, height)}"
                item.fallback = True
            item.label = _truncate(item.label)
            return

        own = text or desc
        if own and on_screen:
            if owner is not None:
                if own not in owner.extra:
                    owner.extra.append(own)
            else:
                assert b is not None
                items.append(Item(label=_truncate(own), bounds=b, package=pkg))
        for child in node:
            walk(child, window_type, owner)

    for top in root:
        walk(top, "", None)

    # The foreground app is the package owning most items; drop the status and
    # navigation bars unless the system UI itself is in front (shade, lock screen).
    counts = Counter(it.package for it in items if it.package not in _SYSTEM_PACKAGES)
    package = counts.most_common(1)[0][0] if counts else (items[0].package if items else "")
    if package not in _SYSTEM_PACKAGES:
        items = [it for it in items if it.package not in _SYSTEM_PACKAGES]

    _name_toggles(items)
    items = _name_fields(items)
    items = _dedupe(items)
    items.sort(key=lambda it: (it.bounds[1] // 24, it.bounds[0]))
    truncated = max(0, len(items) - MAX_ITEMS)
    return Screen(
        package=package,
        items=items[:MAX_ITEMS],
        scrollable=package in scrollable_pkgs,
        width=width,
        height=height,
        truncated=truncated,
    )


def _contains(outer: tuple[int, int, int, int], inner: tuple[int, int, int, int]) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def _name_toggles(items: list[Item]) -> None:
    """An unnamed switch or checkbox takes the label of the row it sits in, so that
    ``switchWidget`` becomes ``Porcentaje de batería`` and _dedupe keeps one line."""
    for it in items:
        if it.checked is None or not it.fallback:
            continue
        rows = [
            o for o in items
            if o is not it and o.tappable and not o.fallback and _contains(o.bounds, it.bounds)
        ]
        if rows:
            it.label = min(rows, key=lambda o: o.area).label
            it.fallback = False


def _name_fields(items: list[Item]) -> list[Item]:
    """An unnamed text field takes the caption on its left in the same row (Gmail's
    "Para" next to the recipient field); the caption line is then dropped."""
    used: set[int] = set()
    for it in items:
        if not (it.editable and it.fallback):
            continue
        fy1, fy2 = it.bounds[1], it.bounds[3]
        captions = [
            o for o in items
            if not o.tappable
            and id(o) not in used
            and o.bounds[2] <= it.bounds[0] + 10
            and min(fy2, o.bounds[3]) - max(fy1, o.bounds[1]) >= 0.5 * min(fy2 - fy1, o.bounds[3] - o.bounds[1])
        ]
        if captions:
            caption = max(captions, key=lambda o: o.bounds[2])
            it.label, it.fallback = caption.label, False
            used.add(id(caption))
    return [it for it in items if id(it) not in used]


def _dedupe(items: list[Item]) -> list[Item]:
    """Drop an item whose label repeats on a nested element (keep the inner one: it is the
    real control, e.g. the switch inside a settings row, and carries its state)."""
    keep = []
    for it in items:
        shadowed = any(
            other is not it
            and other.label == it.label
            and _contains(it.bounds, other.bounds)
            and other.area < it.area
            for other in items
        )
        if not shadowed:
            keep.append(it)
    return keep
