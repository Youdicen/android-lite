"""Resolve a spoken app name ("Gmail", "ajustes") to an installed package, without an LLM."""

from __future__ import annotations

import difflib
import re
import unicodedata

# Common apps whose package name does not contain their visible name. Several
# candidates per name cover different vendors (Pixel, Samsung, ...).
ALIASES: dict[str, list[str]] = {
    "gmail": ["com.google.android.gm"],
    "correo": ["com.google.android.gm"],
    "ajustes": ["com.android.settings"],
    "configuracion": ["com.android.settings"],
    "settings": ["com.android.settings"],
    "chrome": ["com.android.chrome"],
    "navegador": ["com.android.chrome", "com.sec.android.app.sbrowser"],
    "youtube": ["com.google.android.youtube"],
    "maps": ["com.google.android.apps.maps"],
    "mapas": ["com.google.android.apps.maps"],
    "camara": ["com.google.android.GoogleCamera", "com.sec.android.app.camera", "com.android.camera"],
    "camera": ["com.google.android.GoogleCamera", "com.sec.android.app.camera", "com.android.camera"],
    "fotos": ["com.google.android.apps.photos"],
    "photos": ["com.google.android.apps.photos"],
    "galeria": ["com.sec.android.gallery3d", "com.google.android.apps.photos"],
    "telefono": ["com.google.android.dialer", "com.samsung.android.dialer"],
    "phone": ["com.google.android.dialer", "com.samsung.android.dialer"],
    "mensajes": ["com.google.android.apps.messaging", "com.samsung.android.messaging"],
    "messages": ["com.google.android.apps.messaging", "com.samsung.android.messaging"],
    "contactos": ["com.google.android.contacts", "com.samsung.android.app.contacts"],
    "calendario": ["com.google.android.calendar"],
    "calendar": ["com.google.android.calendar"],
    "reloj": ["com.google.android.deskclock", "com.sec.android.app.clockpackage"],
    "alarma": ["com.google.android.deskclock", "com.sec.android.app.clockpackage"],
    "calculadora": ["com.google.android.calculator", "com.sec.android.app.popupcalculator"],
    "playstore": ["com.android.vending"],
    "tienda": ["com.android.vending"],
    "drive": ["com.google.android.apps.docs"],
    "archivos": ["com.google.android.apps.nbu.files", "com.google.android.documentsui"],
    "files": ["com.google.android.apps.nbu.files", "com.google.android.documentsui"],
    "google": ["com.google.android.googlequicksearchbox"],
    "meet": ["com.google.android.apps.tachyon", "com.google.android.apps.meetings"],
    "keep": ["com.google.android.keep"],
    "notas": ["com.google.android.keep", "com.samsung.android.app.notes"],
    "facebook": ["com.facebook.katana"],
    "messenger": ["com.facebook.orca"],
    "whatsapp": ["com.whatsapp"],
    "whatsappbusiness": ["com.whatsapp.w4b"],
    "tiktok": ["com.zhiliaoapp.musically"],
    "twitter": ["com.twitter.android"],
    "x": ["com.twitter.android"],
    "outlook": ["com.microsoft.office.outlook"],
    "teams": ["com.microsoft.teams"],
}


def normalize(name: str) -> str:
    """Lowercase, strip accents and everything that is not a letter or digit."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def resolve_app(name: str, packages: set[str]) -> tuple[str | None, list[str]]:
    """Return ``(package, [])`` when one installed app matches, else ``(None, suggestions)``."""
    name = name.strip()
    if name in packages:
        return name, []
    key = normalize(name)
    if not key:
        return None, []
    for pkg in ALIASES.get(key, []):
        if pkg in packages:
            return pkg, []

    # Visible name inside the package: "whatsapp" -> com.whatsapp, "spotify" -> com.spotify.music.
    hits = [p for p in packages if key in normalize(p)]
    if len(hits) == 1:
        return hits[0], []
    exact_segment = [p for p in hits if key in (normalize(seg) for seg in p.split("."))]
    if len(exact_segment) == 1:
        return exact_segment[0], []
    if hits:
        return None, sorted(hits, key=len)[:5]

    by_segment: dict[str, str] = {}
    for p in packages:
        for seg in p.split(".")[1:]:
            by_segment.setdefault(normalize(seg), p)
    close = difflib.get_close_matches(key, list(by_segment), n=5, cutoff=0.75)
    return None, list(dict.fromkeys(by_segment[c] for c in close))
