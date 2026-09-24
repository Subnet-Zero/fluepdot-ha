"""Framebuffer-Modell der Flipdot-Anzeige.

Das Geraet erwartet und liefert den Framebuffer als ASCII: 'X' = Punkt hell,
Leerzeichen = Punkt dunkel, jede Zeile mit '\\n' abgeschlossen. Diese Klasse
haelt denselben Inhalt als Bitmatrix, kann darauf zeichnen und ihn wieder
ausgeben - inklusive einer PNG-Vorschau ohne jede externe Abhaengigkeit.
"""

from __future__ import annotations

import struct
import zlib

from .const import (
    ALIGN_CENTER,
    ALIGN_RIGHT,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    VALIGN_BOTTOM,
    VALIGN_MIDDLE,
)
from .fonts import Font

PIXEL_ON = "X"
PIXEL_OFF = " "

# Kleine 7x7-Symbole, zeilenweise als Strings (X = gesetzt).
ICONS: dict[str, tuple[str, ...]] = {
    "sun": (
        "  X X  ",
        "X  X  X",
        "  XXX  ",
        "XXXXXXX",
        "  XXX  ",
        "X  X  X",
        "  X X  ",
    ),
    "cloud": (
        "       ",
        "  XXX  ",
        " X   XX",
        "XX     X",
        "X      X",
        "XXXXXXXX",
        "       ",
    ),
    "rain": (
        "  XXX  ",
        " X   X ",
        "XXXXXXX",
        "       ",
        " X X X ",
        "X X X  ",
        " X X X ",
    ),
    "snow": (
        "   X   ",
        " X X X ",
        "  XXX  ",
        "XXXXXXX",
        "  XXX  ",
        " X X X ",
        "   X   ",
    ),
    "bolt": (
        "   XX  ",
        "  XX   ",
        " XX    ",
        "XXXXX  ",
        "  XX   ",
        " XX    ",
        "XX     ",
    ),
    "house": (
        "   X   ",
        "  XXX  ",
        " XXXXX ",
        "XXXXXXX",
        " X   X ",
        " X X X ",
        " X X X ",
    ),
    "bin": (
        " XXXXX ",
        "XXXXXXX",
        " X   X ",
        " X X X ",
        " X X X ",
        " X X X ",
        " XXXXX ",
    ),
    "bell": (
        "   X   ",
        "  XXX  ",
        " XXXXX ",
        " XXXXX ",
        "XXXXXXX",
        "       ",
        "   X   ",
    ),
    "drop": (
        "   X   ",
        "   X   ",
        "  XXX  ",
        " XXXXX ",
        "XXXXXXX",
        "XXXXXXX",
        " XXXXX ",
    ),
    "check": (
        "      X",
        "     XX",
        "X   XX ",
        "XX XX  ",
        " XXX   ",
        "  X    ",
        "       ",
    ),
    "cross": (
        "X     X",
        "XX   XX",
        " XX XX ",
        "  XXX  ",
        " XX XX ",
        "XX   XX",
        "X     X",
    ),
    "arrow_up": (
        "   X   ",
        "  XXX  ",
        " XXXXX ",
        "XX X XX",
        "   X   ",
        "   X   ",
        "   X   ",
    ),
    "arrow_down": (
        "   X   ",
        "   X   ",
        "   X   ",
        "XX X XX",
        " XXXXX ",
        "  XXX  ",
        "   X   ",
    ),
    "person": (
        "  XXX  ",
        "  XXX  ",
        "       ",
        " XXXXX ",
        "XXXXXXX",
        "  X X  ",
        "  X X  ",
    ),
    "washer": (
        "XXXXXXX",
        "X X   X",
        "X  XXX ",
        "X X   X",
        "X X   X",
        "X  XXX ",
        "XXXXXXX",
    ),
}


class Framebuffer:
    """Eine Bitmatrix in Displaygroesse."""

    __slots__ = ("width", "height", "_rows")

    def __init__(self, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT) -> None:
        self.width = width
        self.height = height
        self._rows: list[bytearray] = [bytearray(width) for _ in range(height)]

    # -- Grundlegendes -----------------------------------------------------
    def clear(self, value: int = 0) -> None:
        fill = 1 if value else 0
        for row in self._rows:
            for x in range(self.width):
                row[x] = fill

    def get(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._rows[y][x]
        return 0

    def set(self, x: int, y: int, value: int = 1) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self._rows[y][x] = 1 if value else 0

    def copy(self) -> Framebuffer:
        clone = Framebuffer(self.width, self.height)
        clone._rows = [bytearray(row) for row in self._rows]
        return clone

    def count_on(self) -> int:
        return sum(sum(row) for row in self._rows)

    def is_empty(self) -> bool:
        return self.count_on() == 0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Framebuffer):
            return NotImplemented
        return (
            self.width == other.width
            and self.height == other.height
            and self._rows == other._rows
        )

    # -- ASCII-Format des Geraets -----------------------------------------
    def to_ascii(self) -> str:
        return "".join(
            "".join(PIXEL_ON if value else PIXEL_OFF for value in row) + "\n"
            for row in self._rows
        )

    @classmethod
    def from_rows(cls, rows: list[bytearray]) -> Framebuffer:
        """Direkt aus Zeilen mit 0/1 bauen (schnell, fuer Animationen)."""
        buffer = cls(len(rows[0]) if rows else DEFAULT_WIDTH, len(rows) or DEFAULT_HEIGHT)
        if rows:
            buffer._rows = rows
        return buffer

    @classmethod
    def from_ascii(
        cls,
        data: str,
        width: int | None = None,
        height: int | None = None,
    ) -> Framebuffer:
        lines = data.split("\n")
        # Ein abschliessendes '\n' erzeugt ein leeres letztes Element.
        if lines and lines[-1] == "":
            lines.pop()
        if height is not None:
            lines = lines[:height]
        detected_height = height or len(lines) or DEFAULT_HEIGHT
        detected_width = width or (max((len(line) for line in lines), default=0)
                                   or DEFAULT_WIDTH)
        buffer = cls(detected_width, detected_height)
        for y, line in enumerate(lines):
            if y >= buffer.height:
                break
            for x, char in enumerate(line):
                if x >= buffer.width:
                    break
                buffer._rows[y][x] = 1 if char == PIXEL_ON else 0
        return buffer

    # -- Zeichnen ----------------------------------------------------------
    def hline(self, x: int, y: int, length: int, value: int = 1) -> None:
        for offset in range(max(0, length)):
            self.set(x + offset, y, value)

    def vline(self, x: int, y: int, length: int, value: int = 1) -> None:
        for offset in range(max(0, length)):
            self.set(x, y + offset, value)

    def rect(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        value: int = 1,
        fill: bool = False,
    ) -> None:
        if width <= 0 or height <= 0:
            return
        if fill:
            for row in range(height):
                self.hline(x, y + row, width, value)
            return
        self.hline(x, y, width, value)
        self.hline(x, y + height - 1, width, value)
        self.vline(x, y, height, value)
        self.vline(x + width - 1, y, height, value)

    def invert(self) -> None:
        for row in self._rows:
            for x in range(self.width):
                row[x] = 0 if row[x] else 1

    def blit(self, other: Framebuffer, x: int = 0, y: int = 0, merge: bool = True) -> None:
        for row_index in range(other.height):
            for col_index in range(other.width):
                value = other.get(col_index, row_index)
                if merge and not value:
                    continue
                self.set(x + col_index, y + row_index, value)

    def draw_icon(self, name: str, x: int, y: int, value: int = 1) -> int:
        """Ein Symbol zeichnen. Liefert die Breite zurueck."""
        icon = ICONS.get(name)
        if not icon:
            return 0
        width = 0
        for row_index, line in enumerate(icon):
            width = max(width, len(line))
            for col_index, char in enumerate(line):
                if char == PIXEL_ON:
                    self.set(x + col_index, y + row_index, value)
        return width

    def draw_bar(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        fraction: float,
        border: bool = True,
    ) -> None:
        """Fortschrittsbalken zeichnen. fraction liegt zwischen 0 und 1."""
        fraction = min(1.0, max(0.0, fraction))
        if border:
            self.rect(x, y, width, height)
            inner_x, inner_y = x + 1, y + 1
            inner_w, inner_h = width - 2, height - 2
        else:
            inner_x, inner_y = x, y
            inner_w, inner_h = width, height
        if inner_w <= 0 or inner_h <= 0:
            return
        filled = int(round(inner_w * fraction))
        if filled:
            self.rect(inner_x, inner_y, filled, inner_h, fill=True)

    def draw_text(
        self,
        font: Font,
        text: str,
        x: int = 0,
        y: int = 0,
        value: int = 1,
    ) -> int:
        """Text zeichnen. Liefert die x-Position hinter dem Text."""
        cursor = x
        for char in text:
            glyph = font.glyph(char)
            if glyph is None:
                continue
            for col_index, column in enumerate(glyph.cols):
                target_x = cursor + glyph.left + col_index
                if target_x < 0 or target_x >= self.width:
                    continue
                for bit in range(font.height + 1):
                    if column & (1 << bit):
                        self.set(target_x, y + bit, value)
            cursor += glyph.advance
        return cursor

    def draw_text_aligned(
        self,
        font: Font,
        text: str,
        y: int = 0,
        align: str = "left",
        x_offset: int = 0,
        value: int = 1,
    ) -> None:
        width = font.text_width(text)
        if align == ALIGN_CENTER:
            x = (self.width - width) // 2
        elif align == ALIGN_RIGHT:
            x = self.width - width
        else:
            x = 0
        self.draw_text(font, text, x + x_offset, y, value)

    def draw_lines(
        self,
        font: Font,
        lines: list[str],
        align: str = "left",
        valign: str = "middle",
        spacing: int = 1,
    ) -> None:
        """Mehrere Zeilen mittig/oben/unten ausrichten und zeichnen."""
        lines = [line for line in lines if line is not None]
        if not lines:
            return
        line_height = font.height + spacing
        block_height = len(lines) * line_height - spacing
        if valign == VALIGN_MIDDLE:
            top = max(0, (self.height - block_height) // 2)
        elif valign == VALIGN_BOTTOM:
            top = max(0, self.height - block_height)
        else:
            top = 0
        for index, line in enumerate(lines):
            self.draw_text_aligned(font, line, top + index * line_height, align)

    def shift(self, dx: int = 0, dy: int = 0) -> Framebuffer:
        """Verschobene Kopie erzeugen (fuer Lauftext und Wischeffekte)."""
        result = Framebuffer(self.width, self.height)
        for y in range(self.height):
            for x in range(self.width):
                if self.get(x - dx, y - dy):
                    result.set(x, y, 1)
        return result

    # -- PNG-Vorschau ------------------------------------------------------
    def to_png(self, scale: int = 6) -> bytes:
        """Framegbuffer als PNG rendern - ohne Pillow, nur zlib.

        Farbindizes: 0 = Hintergrund, 1 = dunkler Punkt, 2 = heller Punkt.
        """
        scale = max(2, min(12, scale))
        radius = (scale - 1) / 2.0
        centre = (scale - 1) / 2.0
        limit = (radius - 0.15) ** 2
        mask = [
            [
                ((col - centre) ** 2 + (row - centre) ** 2) <= limit
                for col in range(scale)
            ]
            for row in range(scale)
        ]

        out_width = self.width * scale
        out_height = self.height * scale
        raw = bytearray()
        for y in range(self.height):
            row_source = self._rows[y]
            for sub_y in range(scale):
                raw.append(0)  # Filtertyp "None"
                mask_row = mask[sub_y]
                line = bytearray(out_width)
                for x in range(self.width):
                    colour = 2 if row_source[x] else 1
                    base = x * scale
                    for sub_x in range(scale):
                        if mask_row[sub_x]:
                            line[base + sub_x] = colour
                raw.extend(line)

        palette = bytes((18, 18, 20, 44, 44, 48, 250, 214, 90))
        return _png(out_width, out_height, bytes(raw), palette)


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _png(width: int, height: int, raw: bytes, palette: bytes) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"PLTE", palette)
        + _chunk(b"IDAT", zlib.compress(raw, 6))
        + _chunk(b"IEND", b"")
    )
