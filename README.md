# android-lite

**English** | [Español](README.es.md)

A lightweight **MCP** server that lets an AI agent (Hermes, Claude Code, Cursor…) drive an **Android phone from the screen structure alone**. It uses no screenshots, no vision and no LLM inside.

It is built on top of [google/artemis](https://github.com/google/artemis).

## Why

Agents that look at screenshots burn a lot of tokens. These numbers were measured on a Pixel 7 Pro sending an email in Gmail:

| Approach | Tokens per screen | Whole email |
|---|---|---|
| ARTEMIS agent (Gemini: screenshot + UI tree + history) | 8,000–15,000 per step | ~128,000 |
| `artemis mcp --type adb` (raw JSON UI tree) | ~5,400 | — |
| **android-lite** | **~100–250** | **~800** |

At this size, a modest local model (for example Qwen 27B on Ollama) can operate the phone with no cloud cost at all.

## What the model sees

```
[com.android.settings] 11 elementos · desplazable
3 38%
5t Uso de batería · Ver uso desde la última carga completa
6t Ahorro de batería · Desactivado
9t[x] Porcentaje de batería
2e Buscar en Configuración: "batería"
```

Labels come from the phone's own language; this phone runs in Spanish.

- `t`: tappable
- `e`: text field, with its current value in quotes
- `[x]` / `[ ]`: checkbox or switch state
- `*`: selected
- no flag: plain text

The number at the start of each line is what you pass to the tools.

**How the list is built:**
- Child texts are merged into the button that contains them, e.g. "Batería · 32 %".
- A switch with no label of its own takes the label of its row.
- A text field with no label takes the caption on its left, such as Gmail's "To" field.
- The keyboard, the status bar, invisible nodes and duplicates are dropped.

## Tools

Tool names and messages are in Spanish. Each tool is listed with its English meaning.

| Tool | Meaning | What it does |
|---|---|---|
| `ver_pantalla(esperar=0)` | view screen | Returns the compact list for the current screen. |
| `tocar(n, largo=False)` | tap | Taps element `n`. Set `largo=True` for a long press. |
| `escribir(n, texto, borrar=True, enviar=False)` | type | Types into field `n` through the clipboard, so accents and emoji work. `borrar` replaces the existing content; `enviar` presses Enter afterwards. |
| `deslizar(direccion)` | swipe | Scrolls `abajo` (down), `arriba` (up), `izquierda` (left) or `derecha` (right). |
| `atras()` | back | Presses the Back button. |
| `tecla(nombre)` | key | Presses `inicio` (home), `enter`, `borrar` (delete) or `recientes` (recent apps). |
| `abrir_app(nombre)` | open app | Opens an app by name ("Gmail", "Settings", "WhatsApp") or by package, with no LLM involved. |

**Behavior shared by the tools:**
- Every action **returns the new screen**, so the agent needs one call per step.
- Before tapping or typing, the tool re-reads the screen and finds the element by its label. If the element is gone, it does nothing and returns the current screen.
- If the phone is locked, `ver_pantalla` says so.

## Requirements

- An Android phone with USB or wireless debugging enabled, and a working `adb`.
- [google/artemis](https://github.com/google/artemis) cloned and installed with `uv sync`.
  - android-lite reuses its device controller and its accessibility helper, which dumps the UI tree in about 20 ms.
  - Install the helper on the phone with `uv run artemis helper install`.

## Usage

```bash
git clone https://github.com/Youdicen/android-lite.git
export ARTEMIS=/path/to/artemis

# MCP server over stdio
PYTHONPATH=$PWD/android-lite:$ARTEMIS $ARTEMIS/.venv/bin/python -m android_lite
```

**Hermes Agent:**

```bash
hermes mcp add android --command $ARTEMIS/.venv/bin/python \
  --env PYTHONPATH=$PWD/android-lite:$ARTEMIS --args -m android_lite
```

**Claude Code / Claude Desktop / Cursor** (`mcpServers`):

```json
"android": {
  "command": "/path/to/artemis/.venv/bin/python",
  "args": ["-m", "android_lite"],
  "env": { "PYTHONPATH": "/path/to/android-lite:/path/to/artemis" }
}
```

When several devices are connected, USB is preferred. To pin a specific one, set `ANDROID_LITE_SERIAL=<serial>`.

## Tests

```bash
$ARTEMIS/.venv/bin/python -m pytest
```

The `compact` and `apps` tests need neither a phone nor ARTEMIS.

## Limitations

- Icons without an accessibility label show up as `icono arriba-der` ("icon top-right") or by their resource-id.
- Games and Flutter or Canvas apps expose an empty accessibility tree. For those, use an agent with vision, such as ARTEMIS itself.
- Android only.

## License

Apache-2.0, the same as ARTEMIS.
