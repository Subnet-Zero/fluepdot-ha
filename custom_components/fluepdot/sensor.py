"""Sensoren der Flipdot-Anzeige."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import FluepdotEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    controller = entry.runtime_data.controller
    async_add_entities(
        [
            FluepdotContentSensor(controller),
            FluepdotPixelSensor(controller),
            FluepdotPageSensor(controller),
        ]
    )


class FluepdotContentSensor(FluepdotEntity, SensorEntity):
    """Was gerade auf der Anzeige steht."""

    _attr_translation_key = "content"
    _attr_icon = "mdi:message-text"

    def __init__(self, controller) -> None:
        super().__init__(controller, "content")

    @property
    def native_value(self) -> str:
        return self.controller.current.description[:255]

    @property
    def extra_state_attributes(self) -> dict:
        current = self.controller.current
        diagnostics = self.controller.diagnostics
        return {
            "quelle": current.source,
            "prioritaet": current.priority,
            "seite": current.page_id,
            "laeuft_ab": current.expires_at,
            "geschrieben": current.written_at,
            "ruhezeit_aktiv": self.controller.quiet_now,
            "ruhezeit_von": self.controller.settings.quiet_start,
            "ruhezeit_bis": self.controller.settings.quiet_end,
            "schreibvorgaenge": diagnostics.writes,
            "unterdrueckt_ruhezeit": diagnostics.suppressed_quiet,
            "unterdrueckt_prioritaet": diagnostics.suppressed_priority,
            "fehler": diagnostics.errors,
            "letzter_fehler": diagnostics.last_error,
        }


class FluepdotPixelSensor(FluepdotEntity, SensorEntity):
    """Anzahl gesetzter Punkte - taugt als Diagnose und Verschleissmass."""

    _attr_translation_key = "pixels_on"
    _attr_icon = "mdi:dots-grid"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "Punkte"

    def __init__(self, controller) -> None:
        super().__init__(controller, "pixels_on")

    @property
    def native_value(self) -> int:
        return self.controller.last_framebuffer.count_on()

    @property
    def extra_state_attributes(self) -> dict:
        total = self.controller.width * self.controller.height
        on = self.controller.last_framebuffer.count_on()
        return {
            "punkte_gesamt": total,
            "anteil_prozent": round(100 * on / total, 1) if total else 0,
        }


class FluepdotPageSensor(FluepdotEntity, SensorEntity):
    """Aktive Rotationsseite und Zustand der Seitendatei."""

    _attr_translation_key = "page"
    _attr_icon = "mdi:book-open-page-variant"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, controller) -> None:
        super().__init__(controller, "page")

    @property
    def native_value(self) -> str:
        return self.controller.current.page_id or "-"

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "seiten": [page.page_id for page in self.controller.pages],
            "aktiv": [page.page_id for page in self.controller.visible_pages],
            "fehler": self.controller.pages_error,
            "schriften_geraet": self.controller.device_fonts,
            "schriften_vermessen": [
                name
                for name in self.controller.fonts.names
                if name != "builtin5x7"
            ],
        }
