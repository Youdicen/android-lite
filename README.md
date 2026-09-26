# android-lite

Servidor **MCP** ligero para que un agente de IA (Hermes, Claude Code, Cursor…) controle un teléfono **Android solo con la estructura de la pantalla**. No usa capturas, ni visión, ni ningún LLM dentro.

*Lightweight MCP server to drive Android from the UI tree only (no screenshots, no vision), built on top of [google/artemis](https://github.com/google/artemis).*

## Por qué

Los agentes que miran capturas de pantalla gastan muchos tokens. Medido en un Pixel 7 Pro enviando un correo en Gmail:

| Enfoque | Tokens por pantalla | Correo completo |
|---|---|---|
| Agente ARTEMIS (Gemini, captura + árbol + historial) | 8.000–15.000 por paso | ~128.000 |
| `artemis mcp --type adb` (árbol en JSON crudo) | ~5.400 | — |
| **android-lite** | **~100–250** | **~800** |

Con tan pocos tokens por pantalla, un modelo local modesto (por ejemplo Qwen 27B en Ollama) maneja el teléfono sin coste de nube.

## Cómo se ve la pantalla

```
[com.android.settings] 11 elementos · desplazable
3 38%
5t Uso de batería · Ver uso desde la última carga completa
6t Ahorro de batería · Desactivado
9t[x] Porcentaje de batería
2e Buscar en Configuración: "batería"
```

`t` = tocable, `e` = campo de texto (valor entre comillas), `[x]`/`[ ]` = casilla, `*` = seleccionado, sin marca = solo texto. El número se usa con las herramientas.

**Cómo se arma la lista:**
- El texto de los elementos hijos se une al botón que los contiene, por ejemplo "Batería · 32 %".
- Un interruptor sin nombre toma el nombre de su fila, y un campo sin nombre toma la etiqueta que tiene a su izquierda (el "Para" de Gmail).
- Se quitan el teclado, la barra de estado, los elementos invisibles y los duplicados.

## Herramientas

| Herramienta | Qué hace |
|---|---|
| `ver_pantalla(esperar=0)` | Devuelve la lista compacta de la pantalla actual. |
| `tocar(n, largo=False)` | Toca el elemento `n`. |
| `escribir(n, texto, borrar=True, enviar=False)` | Escribe en el campo `n` por portapapeles, así que admite acentos y emojis. |
| `deslizar(direccion)` | Desplaza hacia `abajo`, `arriba`, `izquierda` o `derecha`. |
| `atras()` | Pulsa el botón Atrás. |
| `tecla(nombre)` | Pulsa `inicio`, `enter`, `borrar` o `recientes`. |
| `abrir_app(nombre)` | Abre una app por su nombre ("Gmail", "Ajustes", "WhatsApp") o por su paquete, sin usar un LLM. |

**Qué más hacen:**
- Cada acción **devuelve la pantalla nueva**, así que basta una llamada por paso.
- Antes de tocar o escribir, vuelve a leer la pantalla y localiza el elemento por su etiqueta. Si ya no está, no actúa.
- Si el teléfono está bloqueado, `ver_pantalla` lo indica.

## Requisitos

- Un teléfono Android con depuración USB o inalámbrica activada y `adb` funcionando.
- [google/artemis](https://github.com/google/artemis) clonado e instalado (`uv sync`). android-lite reutiliza su controlador de dispositivo y su servicio de accesibilidad, que lee el árbol en ~20 ms.
  - El servicio se instala en el teléfono con `uv run artemis helper install`.

## Uso

```bash
git clone https://github.com/Youdicen/android-lite.git
export ARTEMIS=/ruta/a/artemis

# Servidor MCP por stdio
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
  "command": "/ruta/a/artemis/.venv/bin/python",
  "args": ["-m", "android_lite"],
  "env": { "PYTHONPATH": "/ruta/a/android-lite:/ruta/a/artemis" }
}
```

Si hay varios dispositivos conectados, se prefiere el USB. Para fijar uno concreto, usa `ANDROID_LITE_SERIAL=<serial>`.

## Tests

```bash
$ARTEMIS/.venv/bin/python -m pytest
```

Los tests de `compact` y `apps` no necesitan ni teléfono ni ARTEMIS.

## Límites

- Los iconos sin etiqueta aparecen como `icono arriba-der` o con su resource-id.
- En juegos o en apps Flutter o Canvas el árbol de accesibilidad viene vacío; ahí hace falta un agente con visión, como el propio ARTEMIS.
- Solo Android.

## Licencia

Apache-2.0, igual que ARTEMIS.
