"""Ruhezeiten als eigene Entitaeten - so laesst sich die Nachtruhe direkt
im Dashboard und aus Automationen heraus einstellen."""

from __future__ import annotations

from datetime import time as dt_time

from homeassistant.components.time import TimeEntity
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
            FluepdotQuietTime(controller, "quiet_start"),
            FluepdotQuietTime(controller, "quiet_end"),
        ]
    )


class FluepdotQuietTime(FluepdotEntity, TimeEntity):
    """Beginn oder Ende der Ruhezeit."""

    _attr_icon = "mdi:clock-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller, key: str) -> None:
        super().__init__(controller, key)
        self._key = key
        self._attr_translation_key = key

    @property
    def native_value(self) -> dt_time | None:
        raw = getattr(self.controller.settings, self._key, "00:00:00")
        try:
            parts = [int(part) for part in str(raw).split(":")]
            while len(parts) < 3:
                parts.append(0)
            return dt_time(parts[0] % 24, parts[1] % 60, parts[2] % 60)
        except ValueError:
            return None

    async def async_set_value(self, value: dt_time) -> None:
        await self.controller.async_update_settings(
            **{self._key: value.strftime("%H:%M:%S")}
        )
        await self.controller.async_refresh_display(force=True)
