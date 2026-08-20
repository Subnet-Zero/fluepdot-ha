"""Diagnosedaten fuer den Download aus der Oberflaeche."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    controller = entry.runtime_data.controller
    return {
        "host": controller.client.host,
        "geometrie": {"breite": controller.width, "hoehe": controller.height},
        "einstellungen": asdict(controller.settings),
        "aktuell": {
            "beschreibung": controller.current.description,
            "quelle": controller.current.source,
            "prioritaet": controller.current.priority,
            "seite": controller.current.page_id,
        },
        "zaehler": asdict(controller.diagnostics),
        "ruhezeit_aktiv": controller.quiet_now,
        "fremdinhalt": controller.foreign_content,
        "seiten": [
            {
                "id": page.page_id,
                "name": page.name,
                "aktiv": page.enabled,
                "modus": page.mode,
                "font": page.font,
            }
            for page in controller.pages
        ],
        "seiten_fehler": controller.pages_error,
        "schriften_geraet": controller.device_fonts,
        "schriften_vermessen": {
            name: len(controller.fonts.get(name).glyphs)
            for name in controller.fonts.names
        },
        "framebuffer": controller.last_framebuffer.to_ascii(),
    }
