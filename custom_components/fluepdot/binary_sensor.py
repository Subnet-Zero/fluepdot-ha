"""Binaersensoren der Flipdot-Anzeige."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
            FluepdotOnlineSensor(controller),
            FluepdotForeignSensor(controller),
            FluepdotQuietSensor(controller),
        ]
    )


class FluepdotOnlineSensor(FluepdotEntity, BinarySensorEntity):
    """Ist die Anzeige erreichbar?"""

    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, controller) -> None:
        super().__init__(controller, "online")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.controller.available


class FluepdotForeignSensor(FluepdotEntity, BinarySensorEntity):
    """Hat jemand ausserhalb von Home Assistant geschrieben?"""

    _attr_translation_key = "foreign_content"
    _attr_icon = "mdi:account-question"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, controller) -> None:
        super().__init__(controller, "foreign_content")

    @property
    def is_on(self) -> bool:
        return self.controller.foreign_content

    @property
    def extra_state_attributes(self) -> dict:
        return {"erkennungen": self.controller.diagnostics.foreign_detections}


class FluepdotQuietSensor(FluepdotEntity, BinarySensorEntity):
    """Laeuft gerade die Ruhezeit?"""

    _attr_translation_key = "quiet_active"
    _attr_icon = "mdi:sleep"

    def __init__(self, controller) -> None:
        super().__init__(controller, "quiet_active")

    @property
    def is_on(self) -> bool:
        return self.controller.quiet_now

    @property
    def extra_state_attributes(self) -> dict:
        settings = self.controller.settings
        return {
            "von": settings.quiet_start,
            "bis": settings.quiet_end,
            "aktiviert": settings.quiet_enabled,
            "unterdrueckt": self.controller.diagnostics.suppressed_quiet,
        }
