"""Zielanzeige im Stil einer Bus- oder Strassenbahn-Anzeige.

Links die Liniennummer in einem Kasten, rechts daneben das Ziel und darunter
kleiner das Zwischenziel ("ueber ..."). Das Modul ist bewusst frei von
Home-Assistant-Importen - so laesst sich das Layout mit scripts/preview_sign.py
ohne laufende Installation nachrechnen.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import BOX_FILLED, BOX_NONE, BOX_OUTLINE, DEFAULT_VIA_PREFIX
from .fonts import (
    BUILTIN_FONT_NAME,
    BUILTIN_SMALL_FONT_NAME,
    Font,
    FontRegistry,
)
from .framebuffer import Framebuffer

# Luft zwischen Kastenrand und Liniennummer.
BOX_PADDING = 3
# Luft zwischen Kasten und Text.
BOX_GAP = 3
# Abstand zwischen Ziel- und Ueber-Zeile.
LINE_GAP = 1
# Womit ein zu langes Ziel abgeschnitten wird.
TRUNCATION_MARK = "."
# Mehr als ein Drittel der Tafel darf der Kasten nicht beanspruchen - sonst
# weicht die Liniennummer auf die kleine Schrift aus.
BOX_MAX_SHARE = 3
# Obergrenze fuer Scroll-Animationen, wie bei fluepdot.marquee.
MAX_FRAMES = 400


@dataclass(slots=True)
class SignSpec:
    """Was auf der Zielanzeige stehen soll."""

    line_number: str = ""
    destination: str = ""
    via: str = ""
    via_prefix: str = DEFAULT_VIA_PREFIX
    box: str = BOX_OUTLINE
    font: str | None = None

    def via_text(self) -> str:
        """Die zweite Zeile inklusive Praefix."""
        if not self.via:
            return ""
        if not self.via_prefix:
            return self.via
        return f"{self.via_prefix} {self.via}"

    def summary(self) -> str:
        """Kurzbeschreibung fuer sensor.flipdot_inhalt."""
        head = " ".join(part for part in (self.line_number, self.destination) if part)
        via = self.via_text()
        if head and via:
            return f"{head} / {via}"
        return head or via or "Zielanzeige"


def _fit(text: str, font: Font, small: Font, available: int) -> tuple[str, Font]:
    """Text in die verfuegbare Breite bringen.

    Erst so lassen, dann auf die kleine Schrift ausweichen, zuletzt hinten
    abschneiden. Nur fuer den statischen Fall - beim Scrollen darf der Text
    breiter sein als die Tafel.
    """
    if font.text_width(text) <= available:
        return text, font
    if font is not small and small.text_width(text) <= available:
        return text, small
    if font is not small:
        font = small
    cut = text
    while cut and font.text_width(cut + TRUNCATION_MARK) > available:
        cut = cut[:-1]
    return cut.rstrip() + TRUNCATION_MARK, font


def _fonts(spec: SignSpec, registry: FontRegistry, height: int) -> tuple[Font, Font]:
    """Schrift fuer Ziel und Ueber-Zeile bestimmen."""
    small = registry.get(BUILTIN_SMALL_FONT_NAME)
    big = registry.get(spec.font or BUILTIN_FONT_NAME)
    if spec.via and big.height + LINE_GAP + small.height + 1 > height:
        # Zwei Zeilen passen mit dieser Schrift nicht - zurueck auf die
        # mitgelieferte 5x7, sonst wuerde die Ueber-Zeile unten abgeschnitten.
        big = registry.get(BUILTIN_FONT_NAME)
    return big, small


def draw_box(buffer: Framebuffer, spec: SignSpec, registry: FontRegistry) -> int:
    """Liniennummer samt Kasten zeichnen.

    Liefert die linke Kante des Textbereichs zurueck.
    """
    number = spec.line_number.strip()
    if not number:
        return 0

    big = registry.get(BUILTIN_FONT_NAME)
    small = registry.get(BUILTIN_SMALL_FONT_NAME)
    font = big
    if big.text_width(number) + 2 * BOX_PADDING > buffer.width // BOX_MAX_SHARE:
        font = small
    number_width = font.text_width(number)
    number_y = max(0, (buffer.height - font.height) // 2)

    if spec.box == BOX_NONE:
        buffer.draw_text(font, number, 0, number_y)
        return number_width + BOX_GAP

    box_width = number_width + 2 * BOX_PADDING
    if spec.box == BOX_FILLED:
        # Gefuellter Kasten, Ziffern ausgestanzt: value=0 loescht Punkte.
        buffer.rect(0, 0, box_width, buffer.height, fill=True)
        buffer.draw_text(font, number, BOX_PADDING, number_y, value=0)
    else:
        buffer.rect(0, 0, box_width, buffer.height)
        buffer.draw_text(font, number, BOX_PADDING, number_y)
    return box_width + BOX_GAP


def render_sign(
    spec: SignSpec,
    registry: FontRegistry,
    width: int,
    height: int,
) -> Framebuffer:
    """Die komplette Zielanzeige als Framebuffer bauen."""
    buffer = Framebuffer(width, height)
    text_x = draw_box(buffer, spec, registry)
    available = max(0, width - text_x)
    if not available:
        return buffer

    big, small = _fonts(spec, registry, height)
    via_text = spec.via_text()

    if via_text:
        via, via_font = _fit(via_text, small, small, available)
        via_y = height - via_font.height - 1
        text, font = _fit(spec.destination, big, small, available)
        # Das Ziel mittig in den Platz ueber der Ueber-Zeile setzen. Bei der
        # ueblichen Paarung 5x7 ueber 3x5 kommt genau y=1 heraus; weicht das
        # Ziel auf die kleine Schrift aus, klafft so keine Luecke.
        buffer.draw_text(font, text, text_x, max(0, (via_y - font.height) // 2))
        buffer.draw_text(via_font, via, text_x, via_y)
    else:
        text, font = _fit(spec.destination, big, small, available)
        buffer.draw_text(font, text, text_x, max(0, (height - font.height) // 2))
    return buffer


def _text_canvas(
    spec: SignSpec,
    registry: FontRegistry,
    height: int,
    available: int,
) -> tuple[Framebuffer, int]:
    """Ziel und Ueber-Zeile ungekuerzt auf eine breite Flaeche zeichnen.

    Der Inhalt beginnt erst nach einer Leerflaeche von `available` Punkten,
    damit er beim Scrollen von rechts hereinlaeuft.
    """
    big, small = _fonts(spec, registry, height)
    via_text = spec.via_text()
    content = max(
        big.text_width(spec.destination),
        small.text_width(via_text) if via_text else 0,
    )
    canvas = Framebuffer(content + 2 * available, height)
    if via_text:
        via_y = height - small.height - 1
        canvas.draw_text(
            big, spec.destination, available, max(0, (via_y - big.height) // 2)
        )
        canvas.draw_text(small, via_text, available, via_y)
    else:
        canvas.draw_text(
            big, spec.destination, available, max(0, (height - big.height) // 2)
        )
    return canvas, content


def sign_frames(
    spec: SignSpec,
    registry: FontRegistry,
    width: int,
    height: int,
    step: int = 3,
    repeat: int = 1,
) -> list[Framebuffer]:
    """Frames fuer die scrollende Zielanzeige.

    Kasten und Liniennummer stehen still, nur der Textbereich laeuft durch -
    so wie in einem echten Fahrzeug.
    """
    static = Framebuffer(width, height)
    text_x = draw_box(static, spec, registry)
    available = max(0, width - text_x)
    if not available:
        return [static]

    canvas, content = _text_canvas(spec, registry, height, available)
    frames: list[Framebuffer] = []
    for _ in range(max(1, repeat)):
        for offset in range(0, content + available, max(1, step)):
            frame = static.copy()
            for row in range(height):
                for column in range(available):
                    if canvas.get(column + offset, row):
                        frame.set(text_x + column, row, 1)
            frames.append(frame)
            if len(frames) >= MAX_FRAMES:
                return frames
    return frames or [static]
