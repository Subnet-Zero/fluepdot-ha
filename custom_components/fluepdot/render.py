"""Beschreibung dessen, was auf der Anzeige stehen soll.

Ein Payload ist eine reine Datenbeschreibung. Erst der Controller entscheidet,
ob daraus ein kompletter Framebuffer wird (compose) oder ob das Geraet den Text
selbst rendert (device) - Letzteres bildet exakt das bisherige Verhalten ab.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .const import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    MODE_COMPOSE,
    MODE_DEVICE,
    VALIGN_MIDDLE,
)
from .fonts import BUILTIN_FONT_NAME, FontRegistry
from .framebuffer import Framebuffer

# Eine Zeichenanweisung bekommt den Framebuffer und malt hinein.
DrawOp = Callable[[Framebuffer], None]


@dataclass(slots=True)
class Payload:
    """Was angezeigt werden soll."""

    kind: str = "text"
    text: str = ""
    lines: list[str] = field(default_factory=list)
    font: str | None = None
    align: str = ALIGN_LEFT
    valign: str = VALIGN_MIDDLE
    mode: str = MODE_DEVICE
    x: int | None = None
    y: int | None = None
    clear: bool = True
    raw: str | None = None
    ops: list[DrawOp] = field(default_factory=list)
    invert: bool = False
    description: str = ""

    def summary(self) -> str:
        """Kurzbeschreibung fuer sensor.flipdot_inhalt."""
        if self.description:
            return self.description
        if self.kind == "raw":
            return "Rohbild"
        if self.lines:
            return " / ".join(line for line in self.lines if line)
        return self.text or "leer"

    def compose(
        self,
        registry: FontRegistry,
        width: int,
        height: int,
    ) -> Framebuffer:
        """Payload in einen fertigen Framebuffer umsetzen."""
        buffer = Framebuffer(width, height)

        if self.kind == "raw" and self.raw is not None:
            buffer = Framebuffer.from_ascii(self.raw, width, height)
        else:
            font = registry.get(self.font)
            lines = list(self.lines)
            if not lines and self.text:
                available = width if self.x is None else width - self.x
                lines = font.wrap(self.text, max(8, available))
            if len(lines) > 1:
                # Passt der Block nicht in die Hoehe, auf die kleine
                # mitgelieferte Schrift ausweichen statt unten abzuschneiden.
                needed = len(lines) * (font.height + 1) - 1
                if needed > height:
                    fallback = registry.get(BUILTIN_FONT_NAME)
                    if fallback.height < font.height:
                        font = fallback
                        if not self.lines and self.text:
                            lines = font.wrap(self.text, max(8, width))
            if lines:
                if self.x is not None and self.y is not None:
                    cursor_y = self.y
                    for line in lines:
                        buffer.draw_text(font, line, self.x, cursor_y)
                        cursor_y += font.height + 1
                else:
                    buffer.draw_lines(font, lines, self.align, self.valign)

        for operation in self.ops:
            operation(buffer)

        if self.invert:
            buffer.invert()
        return buffer

    def device_call(self, default_font: str) -> tuple[str, str, int | None, int | None]:
        """Argumente fuer POST /framebuffer/text."""
        text = self.text or " ".join(self.lines)
        return text, self.font or default_font, self.x, self.y

    def wants_compose(self) -> bool:
        """Manche Payloads koennen nur komponiert werden.

        Die Anzeige selbst kennt beim Text-Rendern keine Ausrichtung - sie
        zeichnet immer von x/y nach rechts. "align" (z. B. zentriert) wirkt
        also nur, wenn Home Assistant das Bild selbst baut. Ein explizit
        gewaehltes align != links schaltet deshalb automatisch auf compose um,
        sonst waere die Ausrichtungs-Auswahl wirkungslos.
        """
        return (
            self.mode == MODE_COMPOSE
            or self.kind == "raw"
            or bool(self.ops)
            or bool(self.lines)
            or self.invert
            or self.align != ALIGN_LEFT
        )


def text_payload(
    text: str,
    font: str | None = None,
    align: str = ALIGN_LEFT,
    valign: str = VALIGN_MIDDLE,
    mode: str = MODE_DEVICE,
    x: int | None = None,
    y: int | None = None,
    description: str = "",
) -> Payload:
    return Payload(
        kind="text",
        text=text,
        font=font,
        align=align,
        valign=valign,
        mode=mode,
        x=x,
        y=y,
        description=description or text,
    )


def lines_payload(
    lines: list[str],
    font: str | None = None,
    align: str = ALIGN_CENTER,
    valign: str = VALIGN_MIDDLE,
    description: str = "",
) -> Payload:
    return Payload(
        kind="lines",
        lines=[line for line in lines if line is not None],
        font=font,
        align=align,
        valign=valign,
        mode=MODE_COMPOSE,
        description=description,
    )


def raw_payload(ascii_data: str, description: str = "Rohbild") -> Payload:
    return Payload(
        kind="raw", raw=ascii_data, mode=MODE_COMPOSE, description=description
    )


def blank_payload() -> Payload:
    return Payload(kind="raw", raw="", mode=MODE_COMPOSE, description="leer")
