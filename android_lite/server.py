"""Lightweight Android control over MCP: structure only, no screenshots, no LLM inside.

It reuses the ARTEMIS device controller (accessibility helper for a ~20 ms UI dump,
clipboard-based typing that handles accents) but exposes a handful of tools whose
answers are the compact screen from :mod:`android_lite.compact`. Every action
returns the new screen, so a model needs one call per step.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import sys

from mcp.server.fastmcp import FastMCP

from android_lite.apps import resolve_app
from android_lite.compact import Screen, parse_screen

logger = logging.getLogger("android_lite")

mcp = FastMCP("android_lite")

_KEYS = {
    "inicio": "home",
    "home": "home",
    "enter": "enter",
    "intro": "enter",
    "borrar": "delete",
    "delete": "delete",
    "recientes": "app_switch",
    "atras": "back",
    "back": "back",
}


def _quiet():
    """ARTEMIS modules may print to stdout, which is the MCP channel: send it to stderr."""
    return contextlib.redirect_stdout(sys.stderr)


def _pick_serial() -> str | None:
    """Explicit serial from the environment, else prefer a USB transport over Wi-Fi."""
    serial = os.environ.get("ANDROID_LITE_SERIAL") or os.environ.get("ADB_DEVICE_SERIAL")
    if serial:
        return serial
    from adbutils import adb

    serials = [d.serial for d in adb.device_list()]
    usb = [s for s in serials if ":" not in s and "._adb-tls" not in s]
    return (usb or serials or [None])[0]


class Phone:
    """Device session: lazy controller, last compact screen, cached package list."""

    def __init__(self) -> None:
        self._controller = None
        self._packages: set[str] | None = None
        self.last: Screen | None = None

    @property
    def controller(self):
        if self._controller is None:
            with _quiet():
                from artemis.mcp.adb_server import _get_controller

                self._controller = _get_controller(_pick_serial())
        return self._controller

    async def read(self) -> Screen:
        ui = self.controller.ctx.ui_adb_client
        with _quiet():
            xml = await asyncio.to_thread(ui.get_hierarchy)
        return parse_screen(xml)

    async def after_action(self, before: str | None, first_wait: float = 0.6) -> Screen:
        """Read the screen once the UI settles; re-read once if nothing changed yet."""
        await asyncio.sleep(first_wait)
        screen = await self.read()
        if before is not None and screen.render() == before:
            await asyncio.sleep(0.8)
            screen = await self.read()
        return screen

    def report(self, message: str, screen: Screen, before: str | None) -> str:
        self.last = screen
        rendered = screen.render()
        if before is not None and rendered == before:
            return f"{message}. La pantalla no cambió."
        return f"{message}.\n{rendered}"

    async def locked_hint(self, screen: Screen) -> str:
        """A lock screen or an empty dump is not something a model can fix."""
        if screen.items and screen.package != "com.android.systemui":
            return ""
        device = self.controller.ctx.adb_client.device(self.controller.ctx.device.device_id)
        out = await asyncio.to_thread(device.shell, "dumpsys window | grep -m1 isKeyguardShowing")
        if "isKeyguardShowing=true" in out:
            return "El teléfono está bloqueado: pide al usuario que lo desbloquee.\n"
        return ""

    async def target(self, n: int) -> tuple[Screen, int] | str:
        """Re-read the screen and locate item ``n`` of the last list, even if it moved."""
        current = await self.read()
        if self.last is None:
            self.last = current
            return "Primero mira la pantalla; esta es la actual:\n" + current.render()
        if not 1 <= n <= len(self.last.items):
            return f"No hay elemento {n}. Pantalla actual:\n" + current.render()
        wanted = self.last.items[n - 1]
        if n <= len(current.items) and current.items[n - 1].label == wanted.label:
            return current, n
        moved = current.find(wanted.label)
        if moved is not None:
            return current, moved
        self.last = current
        return f"El elemento {n} ({wanted.label}) ya no está en pantalla. Pantalla actual:\n" + current.render()

    async def packages(self) -> set[str]:
        if self._packages is None:
            device = self.controller.ctx.adb_client.device(self.controller.ctx.device.device_id)
            out = await asyncio.to_thread(
                device.shell,
                "cmd package query-activities --brief -a android.intent.action.MAIN "
                "-c android.intent.category.LAUNCHER",
            )
            pkgs = set(re.findall(r"^\s*([A-Za-z0-9_.]+)/", out, re.MULTILINE))
            if not pkgs:
                out = await asyncio.to_thread(device.shell, "pm list packages")
                pkgs = set(re.findall(r"package:(\S+)", out))
            self._packages = pkgs
        return self._packages


phone = Phone()


@mcp.tool()
async def ver_pantalla(esperar: float = 0) -> str:
    """Pantalla actual como lista compacta. Cada línea: `N<flags> etiqueta`
    (t=tocable, e=campo de texto, [x]/[ ]=casilla marcada/sin marcar, *=seleccionado,
    sin flag=solo texto). Usa N con tocar/escribir. esperar: segundos antes de leer."""
    if esperar > 0:
        await asyncio.sleep(min(esperar, 10))
    screen = await phone.read()
    phone.last = screen
    return await phone.locked_hint(screen) + screen.render()


@mcp.tool()
async def tocar(n: int, largo: bool = False) -> str:
    """Toca el elemento N de la última lista (largo=True: pulsación larga). Devuelve la pantalla nueva."""
    found = await phone.target(n)
    if isinstance(found, str):
        return found
    screen, idx = found
    item = screen.items[idx - 1]
    before = screen.render()
    x, y = item.center
    with _quiet():
        result = await phone.controller.tap_at(x=x, y=y, long_press=largo)
    if getattr(result, "error", None):
        return f"Error al tocar {item.label}: {result.error}"
    return phone.report(f"Tocado {idx} ({item.label})", await phone.after_action(before), before)


@mcp.tool()
async def escribir(n: int, texto: str, borrar: bool = True, enviar: bool = False) -> str:
    """Escribe texto en el campo N (borrar=True reemplaza el contenido; enviar=True pulsa Enter). Devuelve la pantalla nueva."""
    found = await phone.target(n)
    if isinstance(found, str):
        return found
    screen, idx = found
    item = screen.items[idx - 1]
    before = screen.render()
    x, y = item.center
    with _quiet():
        from artemis.mcp.actuators.adb import ensure_focus_at_coords

        err = await ensure_focus_at_coords(phone.controller, x, y)
        if err:
            return f"No pude enfocar {item.label}: {err}"
        if borrar:
            await phone.controller.erase_text()
        else:
            await phone.controller.press_key("123")  # KEYCODE_MOVE_END: append
        ok = await phone.controller.type_text(texto, clear_existing=False)
        if ok and enviar:
            await phone.controller.press_key("enter")
    if not ok:
        return f"No pude escribir en {item.label}"
    return phone.report(f"Escrito en {idx} ({item.label})", await phone.after_action(before), before)


@mcp.tool()
async def deslizar(direccion: str) -> str:
    """Desplaza para ver más contenido: 'abajo', 'arriba', 'izquierda' o 'derecha'."""
    screen = phone.last or await phone.read()
    w, h = screen.width or 1080, screen.height or 2400
    moves = {
        "abajo": (w // 2, int(h * 0.7), w // 2, int(h * 0.3)),
        "arriba": (w // 2, int(h * 0.3), w // 2, int(h * 0.7)),
        "derecha": (int(w * 0.85), h // 2, int(w * 0.15), h // 2),
        "izquierda": (int(w * 0.15), h // 2, int(w * 0.85), h // 2),
    }
    key = direccion.strip().lower()
    if key not in moves:
        return "Dirección no válida: usa abajo, arriba, izquierda o derecha."
    before = (await phone.read()).render()
    with _quiet():
        err = await phone.controller.swipe_coords(*moves[key], duration=350)
    if err:
        return f"Error al deslizar: {err}"
    return phone.report(f"Deslizado hacia {key}", await phone.after_action(before, 0.5), before)


@mcp.tool()
async def atras() -> str:
    """Botón Atrás. Devuelve la pantalla nueva."""
    before = (await phone.read()).render()
    with _quiet():
        await phone.controller.go_back()
    return phone.report("Atrás", await phone.after_action(before), before)


@mcp.tool()
async def tecla(nombre: str) -> str:
    """Pulsa una tecla: 'inicio', 'enter', 'borrar' o 'recientes'. Devuelve la pantalla nueva."""
    key = _KEYS.get(nombre.strip().lower())
    if key is None:
        return "Tecla no válida: usa inicio, enter, borrar o recientes."
    before = (await phone.read()).render()
    with _quiet():
        await phone.controller.press_key(key)
    return phone.report(f"Tecla {nombre}", await phone.after_action(before), before)


@mcp.tool()
async def abrir_app(nombre: str) -> str:
    """Abre una app por su nombre ('Gmail', 'Ajustes', 'WhatsApp') o paquete. Devuelve la pantalla."""
    package, suggestions = resolve_app(nombre, await phone.packages())
    if package is None:
        if suggestions:
            return f"No sé cuál es '{nombre}'. Candidatos: " + ", ".join(suggestions)
        return f"No encontré la app '{nombre}' instalada."
    with _quiet():
        from artemis.utils.app_launch_utils import launch_app_with_retries

        ok, err = await launch_app_with_retries(phone.controller.ctx, package)
    if not ok:
        return f"No pude abrir {package}: {err}"
    screen = await phone.after_action(None, 1.0)
    if screen.package != package:
        screen = await phone.after_action(None, 1.5)
    return phone.report(f"Abierta {package}", screen, None)


def main() -> None:
    with _quiet():
        from artemis.mcp.adb_server import configure_stdio_mode

        configure_stdio_mode()
    mcp.run()
