"""Schriftarten fuer die Flipdot-Anzeige.

Zwei Quellen:

* Ein mitgelieferter 5x7-Bitmapfont ("builtin5x7"). Damit funktioniert der
  compose-Modus sofort, ohne dass irgendetwas am Geraet gemessen werden muss.
* Vom Geraet ausgelesene Schriften (siehe extract.py). Die Firmware kann Text
  zwar selbst rendern, verraet aber keine Metriken - deshalb messen wir die
  Glyphen einmalig aus und legen sie als JSON ab.

Glyphen werden spaltenweise als Bitmasken gespeichert: Ein Eintrag pro
Pixelspalte, Bit 0 ist die oberste Zeile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

_LOGGER = logging.getLogger(__name__)

BUILTIN_FONT_NAME = "builtin5x7"


@dataclass(slots=True)
class Glyph:
    """Eine einzelne Glyphe."""

    cols: list[int]
    advance: int
    left: int = 0

    @property
    def width(self) -> int:
        return len(self.cols)


@dataclass(slots=True)
class Font:
    """Eine Schriftart mit Glyphen und Metriken."""

    name: str
    height: int
    glyphs: dict[str, Glyph] = field(default_factory=dict)
    source: str = "builtin"
    space_advance: int = 4

    def glyph(self, char: str) -> Glyph | None:
        """Glyphe holen, mit Ersatzstrategie fuer unbekannte Zeichen."""
        if char in self.glyphs:
            return self.glyphs[char]
        replacement = _FALLBACK_CHARS.get(char)
        if replacement:
            for candidate in replacement:
                if candidate in self.glyphs:
                    return self.glyphs[candidate]
        if char == " ":
            return Glyph([], self.space_advance)
        if "?" in self.glyphs:
            return self.glyphs["?"]
        return None

    def text_width(self, text: str) -> int:
        """Breite eines Textes in Pixeln (ohne nachlaufenden Vorschub)."""
        width = 0
        last_ink = 0
        for char in text:
            glyph = self.glyph(char)
            if glyph is None:
                continue
            if glyph.cols:
                last_ink = width + glyph.left + glyph.width
            width += glyph.advance
        # Der letzte Vorschub enthaelt die Zeichenluecke - fuer die Breite
        # zaehlt nur bis zum letzten gesetzten Pixel.
        return max(last_ink, 0)

    def wrap(self, text: str, max_width: int) -> list[str]:
        """Text auf mehrere Zeilen umbrechen (an Wortgrenzen, sonst hart)."""
        lines: list[str] = []
        for paragraph in text.split("\n"):
            words = paragraph.split(" ")
            current = ""
            for word in words:
                candidate = f"{current} {word}".strip()
                if not candidate:
                    continue
                if self.text_width(candidate) <= max_width or not current:
                    if self.text_width(candidate) > max_width and not current:
                        # Einzelwort zu breit -> hart trennen
                        chunk = ""
                        for char in word:
                            if self.text_width(chunk + char) > max_width and chunk:
                                lines.append(chunk)
                                chunk = char
                            else:
                                chunk += char
                        current = chunk
                        continue
                    current = candidate
                else:
                    lines.append(current)
                    current = word
            lines.append(current)
        return [line for line in lines] or [""]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "height": self.height,
            "source": self.source,
            "space_advance": self.space_advance,
            "glyphs": {
                char: {"c": glyph.cols, "a": glyph.advance, "l": glyph.left}
                for char, glyph in self.glyphs.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> Font:
        return cls(
            name=data["name"],
            height=int(data["height"]),
            source=data.get("source", "device"),
            space_advance=int(data.get("space_advance", 4)),
            glyphs={
                char: Glyph(
                    cols=list(entry["c"]),
                    advance=int(entry["a"]),
                    left=int(entry.get("l", 0)),
                )
                for char, entry in data.get("glyphs", {}).items()
            },
        )


# Zeichen, die notfalls durch ein anderes ersetzt werden duerfen.
_FALLBACK_CHARS: dict[str, str] = {
    "ä": "aä", "ö": "oö", "ü": "uü", "Ä": "AÄ", "Ö": "OÖ", "Ü": "UÜ",
    "ß": "ßs", "é": "e", "è": "e", "á": "a", "à": "a", "í": "i", "ó": "o",
    "ú": "u", "ñ": "n", "ç": "c", "°": "*", "€": "E", "µ": "u", "–": "-",
    "—": "-", "„": '"', "“": '"', "”": '"', "‚": "'", "‘": "'", "’": "'",
    "…": ".", "·": ".", "×": "x", "→": ">", "←": "<", "↑": "^", "↓": "v",
    " ": " ",
}


# --- Mitgelieferter 5x7-Font ----------------------------------------------
# Spaltenweise Bitmasken, Bit 0 = oberste Zeile. Klassischer 5x7-Zeichensatz.
_BUILTIN_5X7: dict[str, tuple[int, ...]] = {
    " ": (0x00, 0x00, 0x00),
    "!": (0x00, 0x5F, 0x00),
    '"': (0x07, 0x00, 0x07),
    "#": (0x14, 0x7F, 0x14, 0x7F, 0x14),
    "$": (0x24, 0x2A, 0x7F, 0x2A, 0x12),
    "%": (0x23, 0x13, 0x08, 0x64, 0x62),
    "&": (0x36, 0x49, 0x55, 0x22, 0x50),
    "'": (0x00, 0x07, 0x00),
    "(": (0x1C, 0x22, 0x41),
    ")": (0x41, 0x22, 0x1C),
    "*": (0x14, 0x08, 0x3E, 0x08, 0x14),
    "+": (0x08, 0x08, 0x3E, 0x08, 0x08),
    ",": (0x00, 0x50, 0x30),
    "-": (0x08, 0x08, 0x08, 0x08, 0x08),
    ".": (0x00, 0x60, 0x60),
    "/": (0x20, 0x10, 0x08, 0x04, 0x02),
    "0": (0x3E, 0x51, 0x49, 0x45, 0x3E),
    "1": (0x42, 0x7F, 0x40),
    "2": (0x42, 0x61, 0x51, 0x49, 0x46),
    "3": (0x21, 0x41, 0x45, 0x4B, 0x31),
    "4": (0x18, 0x14, 0x12, 0x7F, 0x10),
    "5": (0x27, 0x45, 0x45, 0x45, 0x39),
    "6": (0x3C, 0x4A, 0x49, 0x49, 0x30),
    "7": (0x01, 0x71, 0x09, 0x05, 0x03),
    "8": (0x36, 0x49, 0x49, 0x49, 0x36),
    "9": (0x06, 0x49, 0x49, 0x29, 0x1E),
    ":": (0x00, 0x36, 0x36),
    ";": (0x00, 0x56, 0x36),
    "<": (0x08, 0x14, 0x22, 0x41),
    "=": (0x14, 0x14, 0x14, 0x14, 0x14),
    ">": (0x41, 0x22, 0x14, 0x08),
    "?": (0x02, 0x01, 0x51, 0x09, 0x06),
    "@": (0x32, 0x49, 0x79, 0x41, 0x3E),
    "A": (0x7E, 0x11, 0x11, 0x11, 0x7E),
    "B": (0x7F, 0x49, 0x49, 0x49, 0x36),
    "C": (0x3E, 0x41, 0x41, 0x41, 0x22),
    "D": (0x7F, 0x41, 0x41, 0x22, 0x1C),
    "E": (0x7F, 0x49, 0x49, 0x49, 0x41),
    "F": (0x7F, 0x09, 0x09, 0x01, 0x01),
    "G": (0x3E, 0x41, 0x49, 0x49, 0x7A),
    "H": (0x7F, 0x08, 0x08, 0x08, 0x7F),
    "I": (0x41, 0x7F, 0x41),
    "J": (0x20, 0x40, 0x41, 0x3F, 0x01),
    "K": (0x7F, 0x08, 0x14, 0x22, 0x41),
    "L": (0x7F, 0x40, 0x40, 0x40, 0x40),
    "M": (0x7F, 0x02, 0x0C, 0x02, 0x7F),
    "N": (0x7F, 0x04, 0x08, 0x10, 0x7F),
    "O": (0x3E, 0x41, 0x41, 0x41, 0x3E),
    "P": (0x7F, 0x09, 0x09, 0x09, 0x06),
    "Q": (0x3E, 0x41, 0x51, 0x21, 0x5E),
    "R": (0x7F, 0x09, 0x19, 0x29, 0x46),
    "S": (0x46, 0x49, 0x49, 0x49, 0x31),
    "T": (0x01, 0x01, 0x7F, 0x01, 0x01),
    "U": (0x3F, 0x40, 0x40, 0x40, 0x3F),
    "V": (0x1F, 0x20, 0x40, 0x20, 0x1F),
    "W": (0x7F, 0x20, 0x18, 0x20, 0x7F),
    "X": (0x63, 0x14, 0x08, 0x14, 0x63),
    "Y": (0x03, 0x04, 0x78, 0x04, 0x03),
    "Z": (0x61, 0x51, 0x49, 0x45, 0x43),
    "[": (0x7F, 0x41, 0x41),
    "\\": (0x02, 0x04, 0x08, 0x10, 0x20),
    "]": (0x41, 0x41, 0x7F),
    "^": (0x04, 0x02, 0x01, 0x02, 0x04),
    "_": (0x40, 0x40, 0x40, 0x40, 0x40),
    "`": (0x01, 0x02, 0x04),
    "a": (0x20, 0x54, 0x54, 0x54, 0x78),
    "b": (0x7F, 0x48, 0x44, 0x44, 0x38),
    "c": (0x38, 0x44, 0x44, 0x44, 0x20),
    "d": (0x38, 0x44, 0x44, 0x48, 0x7F),
    "e": (0x38, 0x54, 0x54, 0x54, 0x18),
    "f": (0x08, 0x7E, 0x09, 0x01, 0x02),
    "g": (0x08, 0x14, 0x54, 0x54, 0x3C),
    "h": (0x7F, 0x08, 0x04, 0x04, 0x78),
    "i": (0x44, 0x7D, 0x40),
    "j": (0x20, 0x40, 0x44, 0x3D),
    "k": (0x7F, 0x10, 0x28, 0x44),
    "l": (0x41, 0x7F, 0x40),
    "m": (0x7C, 0x04, 0x18, 0x04, 0x78),
    "n": (0x7C, 0x08, 0x04, 0x04, 0x78),
    "o": (0x38, 0x44, 0x44, 0x44, 0x38),
    "p": (0x7C, 0x14, 0x14, 0x14, 0x08),
    "q": (0x08, 0x14, 0x14, 0x18, 0x7C),
    "r": (0x7C, 0x08, 0x04, 0x04, 0x08),
    "s": (0x48, 0x54, 0x54, 0x54, 0x20),
    "t": (0x04, 0x3F, 0x44, 0x40, 0x20),
    "u": (0x3C, 0x40, 0x40, 0x20, 0x7C),
    "v": (0x1C, 0x20, 0x40, 0x20, 0x1C),
    "w": (0x3C, 0x40, 0x30, 0x40, 0x3C),
    "x": (0x44, 0x28, 0x10, 0x28, 0x44),
    "y": (0x0C, 0x50, 0x50, 0x50, 0x3C),
    "z": (0x44, 0x64, 0x54, 0x4C, 0x44),
    "{": (0x08, 0x36, 0x41),
    "|": (0x00, 0x7F, 0x00),
    "}": (0x41, 0x36, 0x08),
    "~": (0x08, 0x08, 0x2A, 0x1C, 0x08),
    # Deutsche Sonderzeichen (Grundbuchstabe gestaucht, Punkte in Zeile 0)
    "Ä": (0x78, 0x15, 0x14, 0x15, 0x78),
    "Ö": (0x38, 0x45, 0x44, 0x45, 0x38),
    "Ü": (0x3C, 0x41, 0x40, 0x41, 0x3C),
    "ä": (0x20, 0x55, 0x54, 0x55, 0x78),
    "ö": (0x38, 0x45, 0x44, 0x45, 0x38),
    "ü": (0x3C, 0x41, 0x40, 0x41, 0x7C),
    "ß": (0x7E, 0x01, 0x49, 0x55, 0x22),
    "°": (0x06, 0x09, 0x09, 0x06),
    "€": (0x14, 0x3E, 0x55, 0x41, 0x22),
    "µ": (0x7C, 0x20, 0x20, 0x10, 0x7C),
    "→": (0x08, 0x08, 0x2A, 0x1C, 0x08),
    "←": (0x08, 0x1C, 0x2A, 0x08, 0x08),
    "↑": (0x04, 0x02, 0x7F, 0x02, 0x04),
    "↓": (0x10, 0x20, 0x7F, 0x20, 0x10),
    "•": (0x18, 0x3C, 0x3C, 0x18),
}


def builtin_font() -> Font:
    """Den mitgelieferten 5x7-Font aufbauen."""
    glyphs: dict[str, Glyph] = {}
    for char, cols in _BUILTIN_5X7.items():
        glyphs[char] = Glyph(cols=list(cols), advance=len(cols) + 1)
    glyphs[" "] = Glyph(cols=[], advance=4)
    return Font(
        name=BUILTIN_FONT_NAME,
        height=7,
        glyphs=glyphs,
        source="builtin",
        space_advance=4,
    )


class FontRegistry:
    """Haelt alle bekannten Schriften (mitgeliefert + vom Geraet gemessen)."""

    def __init__(self) -> None:
        self._fonts: dict[str, Font] = {BUILTIN_FONT_NAME: builtin_font()}
        self.device_fonts: list[str] = []

    @property
    def names(self) -> list[str]:
        return sorted(self._fonts)

    def get(self, name: str | None) -> Font:
        """Font holen; unbekannte Namen fallen auf den Builtin zurueck."""
        if name and name in self._fonts:
            return self._fonts[name]
        if name:
            _LOGGER.debug(
                "Font %s nicht als Bitmap vorhanden, nutze %s",
                name,
                BUILTIN_FONT_NAME,
            )
        return self._fonts[BUILTIN_FONT_NAME]

    def has(self, name: str) -> bool:
        return name in self._fonts

    def add(self, font: Font) -> None:
        self._fonts[font.name] = font

    def load(self, data: dict) -> None:
        """Gemessene Schriften aus dem Speicher uebernehmen."""
        for name, entry in (data or {}).get("fonts", {}).items():
            try:
                self._fonts[name] = Font.from_dict(entry)
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Font %s im Speicher ist unbrauchbar", name)

    def dump(self) -> dict:
        return {
            "fonts": {
                name: font.to_dict()
                for name, font in self._fonts.items()
                if font.source != "builtin"
            }
        }
