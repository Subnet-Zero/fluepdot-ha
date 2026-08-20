"""Die Aktionen (Services) der Flipdot-Integration."""

from __future__ import annotations

import random
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    ALIGNMENTS,
    ALIGN_CENTER,
    ALIGN_LEFT,
    DOMAIN,
    EFFECTS,
    MODE_COMPOSE,
    MODE_DEVICE,
    PRIORITIES,
    PRIORITY_NORMAL,
    RENDER_MODES,
    SERVICE_CLEAR,
    SERVICE_CLEAR_PIXEL,
    SERVICE_DRAW,
    SERVICE_DRAW_BAR,
    SERVICE_EFFECT,
    SERVICE_EXTRACT_FONTS,
    SERVICE_MARQUEE,
    SERVICE_RELOAD_PAGES,
    SERVICE_SEND_LINES,
    SERVICE_SEND_TEXT,
    SERVICE_SET_PIXEL,
    SERVICE_SET_TIMINGS,
    SERVICE_SHOW_PAGE,
    SOURCE_SERVICE,
    VALIGNMENTS,
    VALIGN_MIDDLE,
)
from .controller import FluepdotController
from .framebuffer import ICONS, Framebuffer
from .render import Payload, lines_payload, raw_payload, text_payload

TARGET_SCHEMA = {
    vol.Optional("device_id"): cv.string,
}

SEND_TEXT_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        vol.Required("text"): cv.string,
        vol.Optional("font"): cv.string,
        vol.Optional("align", default=ALIGN_LEFT): vol.In(ALIGNMENTS),
        vol.Optional("valign", default=VALIGN_MIDDLE): vol.In(VALIGNMENTS),
        vol.Optional("mode", default=MODE_DEVICE): vol.In(RENDER_MODES),
        vol.Optional("x"): vol.Coerce(int),
        vol.Optional("y"): vol.Coerce(int),
        vol.Optional("clear", default=True): cv.boolean,
        vol.Optional("icon"): vol.In(sorted(ICONS)),
        vol.Optional("duration"): vol.Coerce(float),
        vol.Optional("priority", default=PRIORITY_NORMAL): vol.In(PRIORITIES),
    }
)

SEND_LINES_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        vol.Required("lines"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("font"): cv.string,
        vol.Optional("align", default=ALIGN_CENTER): vol.In(ALIGNMENTS),
        vol.Optional("valign", default=VALIGN_MIDDLE): vol.In(VALIGNMENTS),
        vol.Optional("icon"): vol.In(sorted(ICONS)),
        vol.Optional("duration"): vol.Coerce(float),
        vol.Optional("priority", default=PRIORITY_NORMAL): vol.In(PRIORITIES),
    }
)

MARQUEE_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        vol.Required("text"): cv.string,
        vol.Optional("font"): cv.string,
        vol.Optional("step", default=3): vol.All(vol.Coerce(int), vol.Range(1, 20)),
        vol.Optional("delay", default=0.35): vol.All(
            vol.Coerce(float), vol.Range(0.1, 5)
        ),
        vol.Optional("repeat", default=1): vol.All(vol.Coerce(int), vol.Range(1, 10)),
        vol.Optional("y"): vol.Coerce(int),
        vol.Optional("priority", default=PRIORITY_NORMAL): vol.In(PRIORITIES),
    }
)

DRAW_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        vol.Required("framebuffer"): cv.string,
        vol.Optional("duration"): vol.Coerce(float),
        vol.Optional("priority", default=PRIORITY_NORMAL): vol.In(PRIORITIES),
    }
)

DRAW_BAR_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        vol.Required("value"): vol.Coerce(float),
        vol.Optional("min", default=0): vol.Coerce(float),
        vol.Optional("max", default=100): vol.Coerce(float),
        vol.Optional("label"): cv.string,
        vol.Optional("font"): cv.string,
        vol.Optional("x", default=0): vol.Coerce(int),
        vol.Optional("y", default=10): vol.Coerce(int),
        vol.Optional("width"): vol.Coerce(int),
        vol.Optional("height", default=5): vol.Coerce(int),
        vol.Optional("duration"): vol.Coerce(float),
        vol.Optional("priority", default=PRIORITY_NORMAL): vol.In(PRIORITIES),
    }
)

PIXEL_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        vol.Required("x"): vol.Coerce(int),
        vol.Required("y"): vol.Coerce(int),
    }
)

EFFECT_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        vol.Required("effect"): vol.In(EFFECTS),
        vol.Optional("frames", default=12): vol.All(
            vol.Coerce(int), vol.Range(2, 60)
        ),
        vol.Optional("delay", default=0.25): vol.All(
            vol.Coerce(float), vol.Range(0.1, 5)
        ),
        vol.Optional("priority", default=PRIORITY_NORMAL): vol.In(PRIORITIES),
    }
)

SHOW_PAGE_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        vol.Required("page_id"): cv.string,
        vol.Optional("duration"): vol.Coerce(float),
        vol.Optional("priority", default=PRIORITY_NORMAL): vol.In(PRIORITIES),
    }
)

EXTRACT_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        vol.Optional("fonts"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("charset"): cv.string,
    }
)

TIMINGS_SCHEMA = vol.Schema(
    {
        **TARGET_SCHEMA,
        vol.Optional("pre", default=0): vol.All(vol.Coerce(int), vol.Range(0, 60000)),
        vol.Optional("clear", default=1600): vol.All(
            vol.Coerce(int), vol.Range(50, 60000)
        ),
        vol.Optional("set", default=1600): vol.All(
            vol.Coerce(int), vol.Range(50, 60000)
        ),
    }
)

SIMPLE_SCHEMA = vol.Schema(TARGET_SCHEMA)


def _controllers(hass: HomeAssistant, call: ServiceCall) -> list[FluepdotController]:
    """Zielgeraete bestimmen; ohne Angabe gelten alle Eintraege."""
    controllers: list[FluepdotController] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        controller = getattr(entry, "runtime_data", None)
        if controller is not None:
            controllers.append(controller.controller)

    device_id = call.data.get("device_id")
    if not device_id:
        if not controllers:
            raise HomeAssistantError("Keine Flipdot-Anzeige eingerichtet")
        return controllers

    registry = dr.async_get(hass)
    device = registry.async_get(device_id)
    if device is None:
        raise HomeAssistantError(f"Unbekanntes Geraet: {device_id}")
    wanted = {entry_id for entry_id in device.config_entries}
    filtered = [c for c in controllers if c.entry.entry_id in wanted]
    if not filtered:
        raise HomeAssistantError("Geraet gehoert nicht zur Flipdot-Integration")
    return filtered


def _with_icon(payload: Payload, icon: str | None) -> Payload:
    if icon:
        payload.mode = MODE_COMPOSE
        payload.ops.append(lambda buffer: buffer.draw_icon(icon, 0, 4))
    return payload


async def _handle_send_text(hass: HomeAssistant, call: ServiceCall) -> None:
    for controller in _controllers(hass, call):
        payload = text_payload(
            call.data["text"],
            font=call.data.get("font") or controller.settings.default_font,
            align=call.data.get("align", ALIGN_LEFT),
            valign=call.data.get("valign", VALIGN_MIDDLE),
            mode=call.data.get("mode", MODE_DEVICE),
            x=call.data.get("x"),
            y=call.data.get("y"),
        )
        payload.clear = call.data.get("clear", True)
        _with_icon(payload, call.data.get("icon"))
        await controller.async_show(
            payload,
            priority=call.data.get("priority", PRIORITY_NORMAL),
            duration=call.data.get("duration"),
            source=SOURCE_SERVICE,
        )


async def _handle_send_lines(hass: HomeAssistant, call: ServiceCall) -> None:
    for controller in _controllers(hass, call):
        payload = lines_payload(
            list(call.data["lines"]),
            font=call.data.get("font"),
            align=call.data.get("align", ALIGN_CENTER),
            valign=call.data.get("valign", VALIGN_MIDDLE),
            description=" / ".join(call.data["lines"]),
        )
        _with_icon(payload, call.data.get("icon"))
        await controller.async_show(
            payload,
            priority=call.data.get("priority", PRIORITY_NORMAL),
            duration=call.data.get("duration"),
            source=SOURCE_SERVICE,
        )


async def _handle_marquee(hass: HomeAssistant, call: ServiceCall) -> None:
    for controller in _controllers(hass, call):
        font = controller.fonts.get(call.data.get("font"))
        text = call.data["text"]
        step = call.data.get("step", 3)
        repeat = call.data.get("repeat", 1)
        width = controller.width
        text_width = font.text_width(text)
        y = call.data.get("y")
        if y is None:
            y = max(0, (controller.height - font.height) // 2)

        canvas = Framebuffer(text_width + 2 * width, controller.height)
        canvas.draw_text(font, text, width, y)

        frames: list[Framebuffer] = []
        for _ in range(repeat):
            for offset in range(0, text_width + width, step):
                frame = Framebuffer(width, controller.height)
                for row in range(controller.height):
                    for col in range(width):
                        if canvas.get(col + offset, row):
                            frame.set(col, row, 1)
                frames.append(frame)
                if len(frames) >= 400:
                    break
        await controller.async_animate(
            frames,
            call.data.get("delay", 0.35),
            f"Lauftext: {text}",
            call.data.get("priority", PRIORITY_NORMAL),
        )


async def _handle_draw(hass: HomeAssistant, call: ServiceCall) -> None:
    for controller in _controllers(hass, call):
        await controller.async_show(
            raw_payload(call.data["framebuffer"]),
            priority=call.data.get("priority", PRIORITY_NORMAL),
            duration=call.data.get("duration"),
            source=SOURCE_SERVICE,
        )


async def _handle_draw_bar(hass: HomeAssistant, call: ServiceCall) -> None:
    for controller in _controllers(hass, call):
        minimum = call.data.get("min", 0)
        maximum = call.data.get("max", 100)
        span = maximum - minimum
        fraction = 0.0 if span <= 0 else (call.data["value"] - minimum) / span
        bar_x = call.data.get("x", 0)
        bar_y = call.data.get("y", 10)
        bar_w = call.data.get("width") or (controller.width - 2 * bar_x)
        bar_h = call.data.get("height", 5)
        label = call.data.get("label")

        payload = Payload(kind="lines", mode=MODE_COMPOSE, description=label or "Balken")
        if label:
            payload.lines = [label]
            payload.font = call.data.get("font")
            payload.align = ALIGN_CENTER
            payload.valign = "top"
        payload.ops.append(
            lambda buffer: buffer.draw_bar(bar_x, bar_y, bar_w, bar_h, fraction)
        )
        await controller.async_show(
            payload,
            priority=call.data.get("priority", PRIORITY_NORMAL),
            duration=call.data.get("duration"),
            source=SOURCE_SERVICE,
        )


async def _set_pixel(hass: HomeAssistant, call: ServiceCall, value: int) -> None:
    """Einen Punkt ueber den Framebuffer setzen oder loeschen.

    Der Endpunkt POST/DELETE /pixel der Firmware quittiert zwar mit HTTP 200
    und GET /pixel meldet den neuen Wert, die Tafel selbst zeichnet ihn aber
    nicht - am 2026-08-20 am Geraet nachgemessen. Deshalb wird der aktuelle
    Framebuffer veraendert und komplett zurueckgeschrieben; das geht durch die
    normale Warteschlange und beachtet damit auch Ruhezeit und Prioritaet.
    """
    for controller in _controllers(hass, call):
        buffer = controller.last_framebuffer.copy()
        x, y = call.data["x"], call.data["y"]
        buffer.set(x, y, value)
        await controller.async_show(
            raw_payload(
                buffer.to_ascii(),
                f"Punkt {x}/{y} {'gesetzt' if value else 'geloescht'}",
            ),
            priority=PRIORITY_NORMAL,
            source=SOURCE_SERVICE,
        )


async def _handle_set_pixel(hass: HomeAssistant, call: ServiceCall) -> None:
    await _set_pixel(hass, call, 1)


async def _handle_clear_pixel(hass: HomeAssistant, call: ServiceCall) -> None:
    await _set_pixel(hass, call, 0)


async def _handle_clear(hass: HomeAssistant, call: ServiceCall) -> None:
    for controller in _controllers(hass, call):
        await controller.async_clear()


def _effect_frames(
    effect: str, base: Framebuffer, width: int, height: int, count: int
) -> list[Framebuffer]:
    frames: list[Framebuffer] = []
    if effect == "wipe":
        for index in range(count):
            frame = Framebuffer(width, height)
            edge = int(width * (index + 1) / count)
            frame.rect(0, 0, edge, height, fill=True)
            frames.append(frame)
        frames.append(Framebuffer(width, height))
    elif effect == "invert":
        inverted = base.copy()
        inverted.invert()
        frames.append(inverted)
    elif effect == "blink":
        inverted = base.copy()
        inverted.invert()
        for index in range(count):
            frames.append(inverted if index % 2 == 0 else base.copy())
    elif effect == "dissolve":
        frame = base.copy()
        coords = [(x, y) for y in range(height) for x in range(width)]
        random.shuffle(coords)
        chunk = max(1, len(coords) // count)
        for index in range(count):
            frame = frame.copy()
            for x, y in coords[index * chunk : (index + 1) * chunk]:
                frame.set(x, y, 0)
            frames.append(frame)
    elif effect == "matrix":
        columns = [random.randint(-height, 0) for _ in range(width)]
        for _ in range(count):
            frame = Framebuffer(width, height)
            for x in range(width):
                head = columns[x]
                for tail in range(4):
                    frame.set(x, head - tail, 1)
                columns[x] = (head + 1) % (height + 6)
            frames.append(frame)
        frames.append(Framebuffer(width, height))
    elif effect == "snow":
        for _ in range(count):
            frame = Framebuffer(width, height)
            for _ in range(width * height // 6):
                frame.set(random.randrange(width), random.randrange(height), 1)
            frames.append(frame)
        frames.append(Framebuffer(width, height))
    return frames


async def _handle_effect(hass: HomeAssistant, call: ServiceCall) -> None:
    for controller in _controllers(hass, call):
        frames = _effect_frames(
            call.data["effect"],
            controller.last_framebuffer,
            controller.width,
            controller.height,
            call.data.get("frames", 12),
        )
        await controller.async_animate(
            frames,
            call.data.get("delay", 0.25),
            f"Effekt: {call.data['effect']}",
            call.data.get("priority", PRIORITY_NORMAL),
        )


async def _handle_show_page(hass: HomeAssistant, call: ServiceCall) -> None:
    for controller in _controllers(hass, call):
        page = controller.page_by_id(call.data["page_id"])
        if page is None:
            raise HomeAssistantError(f"Unbekannte Seite: {call.data['page_id']}")
        payload = page.build(hass)
        if payload is None:
            raise HomeAssistantError(
                f"Seite {page.page_id} liefert derzeit keinen Inhalt"
            )
        await controller.async_show(
            payload,
            priority=call.data.get("priority", PRIORITY_NORMAL),
            duration=call.data.get("duration"),
            source=SOURCE_SERVICE,
            page_id=page.page_id,
        )


async def _handle_reload_pages(hass: HomeAssistant, call: ServiceCall) -> None:
    for controller in _controllers(hass, call):
        await controller.async_reload_pages()
        await controller.async_refresh_display(force=True)


async def _handle_extract_fonts(hass: HomeAssistant, call: ServiceCall) -> None:
    from .extract import async_extract_fonts

    for controller in _controllers(hass, call):
        await async_extract_fonts(
            controller,
            call.data.get("fonts"),
            call.data.get("charset"),
        )


async def _handle_set_timings(hass: HomeAssistant, call: ServiceCall) -> None:
    for controller in _controllers(hass, call):
        pre = max(0, call.data.get("pre", 0) // 50)
        clear = max(1, call.data.get("clear", 1600) // 50)
        set_ = max(1, call.data.get("set", 1600) // 50)
        await controller.client.set_timings([(pre, clear, set_)] * controller.width)
        await controller.async_update_settings(set_delay_us=call.data.get("set", 1600))


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Alle Aktionen registrieren (einmal je HA-Start)."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_TEXT):
        return

    definitions: list[tuple[str, Any, Any]] = [
        (SERVICE_SEND_TEXT, _handle_send_text, SEND_TEXT_SCHEMA),
        (SERVICE_SEND_LINES, _handle_send_lines, SEND_LINES_SCHEMA),
        (SERVICE_MARQUEE, _handle_marquee, MARQUEE_SCHEMA),
        (SERVICE_DRAW, _handle_draw, DRAW_SCHEMA),
        (SERVICE_DRAW_BAR, _handle_draw_bar, DRAW_BAR_SCHEMA),
        (SERVICE_SET_PIXEL, _handle_set_pixel, PIXEL_SCHEMA),
        (SERVICE_CLEAR_PIXEL, _handle_clear_pixel, PIXEL_SCHEMA),
        (SERVICE_CLEAR, _handle_clear, SIMPLE_SCHEMA),
        (SERVICE_EFFECT, _handle_effect, EFFECT_SCHEMA),
        (SERVICE_SHOW_PAGE, _handle_show_page, SHOW_PAGE_SCHEMA),
        (SERVICE_RELOAD_PAGES, _handle_reload_pages, SIMPLE_SCHEMA),
        (SERVICE_EXTRACT_FONTS, _handle_extract_fonts, EXTRACT_SCHEMA),
        (SERVICE_SET_TIMINGS, _handle_set_timings, TIMINGS_SCHEMA),
    ]

    for name, handler, schema in definitions:

        def _make(func):
            async def _service(call: ServiceCall) -> None:
                await func(hass, call)

            return _service

        hass.services.async_register(DOMAIN, name, _make(handler), schema=schema)


@callback
def async_unregister_services(hass: HomeAssistant) -> None:
    for name in (
        SERVICE_SEND_TEXT,
        SERVICE_SEND_LINES,
        SERVICE_MARQUEE,
        SERVICE_DRAW,
        SERVICE_DRAW_BAR,
        SERVICE_SET_PIXEL,
        SERVICE_CLEAR_PIXEL,
        SERVICE_CLEAR,
        SERVICE_EFFECT,
        SERVICE_SHOW_PAGE,
        SERVICE_RELOAD_PAGES,
        SERVICE_EXTRACT_FONTS,
        SERVICE_SET_TIMINGS,
    ):
        hass.services.async_remove(DOMAIN, name)
