"""Schriften vom Geraet ausmessen.

Die Firmware kann Text rendern, verraet aber keine Metriken. Deshalb lassen
wir sie jedes Zeichen einmal zeichnen, lesen den Framebuffer zurueck und
gewinnen daraus Glyphen-Bitmaps und Vorschubbreiten. Danach kann Home
Assistant dieselben Schriften selbst setzen - zentriert, mehrzeilig, gemischt
mit Symbolen.

Der Vorgang klappert hoerbar und dauert einige Minuten. Er wird deshalb nie
automatisch ausgeloest, sondern nur ueber die Aktion fluepdot.extract_fonts.
"""

from __future__ import annotations

import logging

from homeassistant.components import persistent_notification
from homeassistant.helpers.storage import Store

from .client import FluepdotError
from .const import FONTS_STORAGE_KEY, FONTS_STORAGE_VERSION
from .fonts import Font, Glyph

_LOGGER = logging.getLogger(__name__)

DEFAULT_CHARSET = (
    " !\"#%&'()+,-./0123456789:;<=>?"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "ÄÖÜäöüß°"
)

DEFAULT_FONTS = ["DejaVuSans12bw_bwfont", "fixed_5x8", "fixed_7x14"]


def _columns(raw: str, width: int, height: int) -> list[int]:
    """ASCII-Framebuffer in Spalten-Bitmasken umwandeln."""
    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    columns = [0] * width
    for y, line in enumerate(lines[:height]):
        for x, char in enumerate(line[:width]):
            if char == "X":
                columns[x] |= 1 << y
    return columns


def _bbox(columns: list[int]) -> tuple[int, int] | None:
    """Erste und letzte Spalte mit Inhalt."""
    first = next((x for x, value in enumerate(columns) if value), None)
    if first is None:
        return None
    last = max(x for x, value in enumerate(columns) if value)
    return first, last


async def async_extract_fonts(
    controller,
    fonts: list[str] | None = None,
    charset: str | None = None,
) -> dict[str, int]:
    """Alle gewuenschten Schriften ausmessen und speichern."""
    hass = controller.hass
    width = controller.width
    height = controller.height
    wanted = fonts or DEFAULT_FONTS
    chars = charset or DEFAULT_CHARSET

    available = set(controller.device_fonts)
    todo = [name for name in wanted if name in available]
    skipped = [name for name in wanted if name not in available]
    if skipped:
        _LOGGER.warning("Unbekannte Schriften uebersprungen: %s", ", ".join(skipped))
    if not todo:
        raise FluepdotError("Keine der angeforderten Schriften ist installiert")

    previous_mode = 0
    try:
        previous_mode = await controller.client.get_rendering_mode()
        # Differenzielles Zeichnen: nur geaenderte Punkte klappen.
        await controller.client.set_rendering_mode(1)
    except FluepdotError as err:
        _LOGGER.debug("Rendering-Modus nicht umstellbar: %s", err)

    result: dict[str, int] = {}
    try:
        for font_name in todo:
            font = await _extract_single(controller, font_name, chars, width, height)
            controller.fonts.add(font)
            result[font_name] = len(font.glyphs)
            _LOGGER.info(
                "Schrift %s ausgemessen: %d Zeichen, Hoehe %d",
                font_name,
                len(font.glyphs),
                font.height,
            )
    finally:
        try:
            await controller.client.set_rendering_mode(previous_mode)
        except FluepdotError:
            pass
        store: Store = Store(hass, FONTS_STORAGE_VERSION, FONTS_STORAGE_KEY)
        await store.async_save(controller.fonts.dump())
        await controller.async_refresh_display(force=True)
        controller.notify_listeners()

    persistent_notification.async_create(
        hass,
        "Ausgemessen: "
        + ", ".join(f"{name} ({count} Zeichen)" for name, count in result.items())
        + ".\nDiese Schriften stehen jetzt auch im compose-Modus zur Verfuegung.",
        title="Flipdot: Schriften vermessen",
        notification_id="fluepdot_extract_fonts",
    )
    return result


async def _extract_single(
    controller,
    font_name: str,
    chars: str,
    width: int,
    height: int,
) -> Font:
    """Eine einzelne Schrift ausmessen."""
    client = controller.client
    glyphs: dict[str, Glyph] = {}
    max_row = 0
    space_advance = 4

    for char in chars:
        if char in glyphs:
            continue
        try:
            single = await _render_and_read(client, char, font_name, width, height)
            double = await _render_and_read(client, char + char, font_name, width, height)
        except FluepdotError as err:
            _LOGGER.warning("Zeichen %r konnte nicht gemessen werden: %s", char, err)
            continue

        box_single = _bbox(single)
        box_double = _bbox(double)

        if box_single is None:
            # Leerzeichen und aehnliche Zeichen haben keine Pixel. Ihre Breite
            # ergibt sich aus dem Abstand zweier Nachbarzeichen.
            if char == " ":
                space_advance = await _measure_space(client, font_name, width, height)
                glyphs[char] = Glyph(cols=[], advance=space_advance)
            continue

        first, last = box_single
        cols = single[first : last + 1]

        if box_double is not None:
            advance = box_double[1] - last
        else:
            advance = last - first + 2
        if advance <= 0:
            advance = last - first + 2

        glyphs[char] = Glyph(cols=cols, advance=advance, left=first)

        for value in cols:
            if value:
                max_row = max(max_row, value.bit_length())

    if " " not in glyphs:
        glyphs[" "] = Glyph(cols=[], advance=space_advance)

    return Font(
        name=font_name,
        height=max(1, max_row),
        glyphs=glyphs,
        source="device",
        space_advance=space_advance,
    )


async def _render_and_read(
    client, text: str, font_name: str, width: int, height: int
) -> list[int]:
    """Text an Position 0/0 rendern und den Framebuffer zurueckholen."""
    await client.clear(width, height)
    await client.post_text(text, font_name, 0, 0)
    raw = await client.get_framebuffer()
    return _columns(raw, width, height)


async def _measure_space(client, font_name: str, width: int, height: int) -> int:
    """Breite des Leerzeichens ueber zwei Referenzzeichen bestimmen."""
    try:
        tight = _bbox(await _render_and_read(client, "II", font_name, width, height))
        loose = _bbox(await _render_and_read(client, "I I", font_name, width, height))
    except FluepdotError:
        return 4
    if tight is None or loose is None:
        return 4
    return max(1, loose[1] - tight[1])
