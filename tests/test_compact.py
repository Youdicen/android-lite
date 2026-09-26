from android_lite.apps import resolve_app
from android_lite.compact import parse_screen

XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node class="android.widget.FrameLayout" package="com.android.systemui" window-type="system" bounds="[0,0][1000,100]">
    <node text="12:30" class="android.widget.TextView" package="com.android.systemui" bounds="[10,10][100,90]" />
  </node>
  <node class="android.widget.FrameLayout" package="com.example.app" window-type="application" bounds="[0,0][1000,2000]">
    <node text="Ajustes" class="android.widget.TextView" package="com.example.app" bounds="[20,120][400,200]" />
    <node clickable="true" resource-id="com.example.app:id/search_button" class="android.widget.ImageButton" package="com.example.app" bounds="[900,120][980,200]" />
    <node clickable="true" class="android.widget.ImageButton" package="com.example.app" bounds="[800,120][880,200]" />
    <node clickable="true" class="android.widget.LinearLayout" package="com.example.app" bounds="[0,300][1000,450]">
      <node text="Batería" class="android.widget.TextView" package="com.example.app" bounds="[20,310][400,370]" />
      <node text="32 %" class="android.widget.TextView" package="com.example.app" bounds="[20,380][400,440]" />
    </node>
    <node clickable="true" content-desc="Wi-Fi" class="android.widget.LinearLayout" package="com.example.app" bounds="[0,500][1000,650]">
      <node checkable="true" checked="true" clickable="true" content-desc="Wi-Fi" class="android.widget.Switch" package="com.example.app" bounds="[850,520][980,630]" />
    </node>
    <node clickable="true" focusable="true" text="Buscar" hint="Buscar" class="android.widget.EditText" package="com.example.app" bounds="[20,700][980,800]" />
    <node clickable="true" text="ana@x.com" hint="Para" class="android.widget.EditText" package="com.example.app" bounds="[20,820][980,900]" />
    <node clickable="true" text="Oculto" visible-to-user="false" class="android.widget.Button" package="com.example.app" bounds="[20,950][300,1000]" />
    <node clickable="true" text="Cero" class="android.widget.Button" package="com.example.app" bounds="[20,1000][20,1000]" />
    <node scrollable="true" class="android.widget.ScrollView" package="com.example.app" bounds="[0,300][1000,1900]" />
  </node>
  <node class="android.widget.FrameLayout" package="com.google.android.inputmethod.latin" window-type="input_method" bounds="[0,1400][1000,2000]">
    <node clickable="true" content-desc="q" class="android.widget.Button" package="com.google.android.inputmethod.latin" bounds="[0,1400][100,1500]" />
  </node>
</hierarchy>"""


def test_compact_screen_lines():
    screen = parse_screen(XML)
    assert screen.package == "com.example.app"
    assert screen.scrollable
    assert screen.render().splitlines() == [
        "[com.example.app] 7 elementos · desplazable",
        "1 Ajustes",
        "2t icono arriba-der",
        "3t search button",
        "4t Batería · 32 %",
        "5t[x] Wi-Fi",
        "6e Buscar",
        '7e Para: "ana@x.com"',
    ]


def test_items_keep_tap_targets():
    screen = parse_screen(XML)
    assert screen.items[3].center == (500, 375)
    # The nested switch wins over its same-label row, so a tap flips the switch.
    assert screen.items[4].bounds == (850, 520, 980, 630)
    assert screen.find("Batería · 32 %") == 4


def test_unnamed_switch_takes_row_label():
    row = """<hierarchy><node package="com.android.settings" window-type="application" bounds="[0,0][1000,2000]">
      <node clickable="true" class="android.widget.LinearLayout" package="com.android.settings" bounds="[0,300][1000,450]">
        <node text="Porcentaje de batería" package="com.android.settings" bounds="[20,310][700,370]" />
      </node>
      <node checkable="true" checked="true" clickable="true" resource-id="android:id/switchWidget"
            class="android.widget.Switch" package="com.android.settings" bounds="[850,330][980,420]" />
    </node></hierarchy>"""
    screen = parse_screen(row)
    assert screen.render().splitlines()[1:] == ["1t[x] Porcentaje de batería"]
    assert screen.items[0].bounds == (850, 330, 980, 420)


def test_unnamed_field_takes_caption_on_its_left():
    compose = """<hierarchy><node package="com.google.android.gm" window-type="application" bounds="[0,0][1000,2000]">
      <node text="Para" package="com.google.android.gm" bounds="[20,400][120,480]" />
      <node clickable="true" class="android.widget.EditText" package="com.google.android.gm" bounds="[140,390][980,490]" />
      <node clickable="true" hint="Asunto" class="android.widget.EditText" package="com.google.android.gm" bounds="[20,520][980,600]" />
    </node></hierarchy>"""
    assert parse_screen(compose).render().splitlines()[1:] == ["1e Para", "2e Asunto"]


def test_status_bar_kept_when_system_ui_in_front():
    lock = """<hierarchy><node package="com.android.systemui" window-type="system" bounds="[0,0][1000,2000]">
      <node text="Desliza para desbloquear" package="com.android.systemui" bounds="[100,1800][900,1900]" />
    </node></hierarchy>"""
    screen = parse_screen(lock)
    assert screen.package == "com.android.systemui"
    assert [it.label for it in screen.items] == ["Desliza para desbloquear"]


def test_resolve_app():
    pkgs = {"com.google.android.gm", "com.android.settings", "com.whatsapp", "com.spotify.music",
            "com.facebook.katana", "com.facebook.orca"}
    assert resolve_app("Gmail", pkgs) == ("com.google.android.gm", [])
    assert resolve_app("Configuración", pkgs) == ("com.android.settings", [])
    assert resolve_app("WhatsApp", pkgs) == ("com.whatsapp", [])
    assert resolve_app("spotify", pkgs) == ("com.spotify.music", [])
    assert resolve_app("com.facebook.orca", pkgs) == ("com.facebook.orca", [])
    assert resolve_app("Telegram", pkgs) == (None, [])
