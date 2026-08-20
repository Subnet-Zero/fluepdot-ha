"""Zahlenwerte der Flipdot-Anzeige."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import FluepdotEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    controller = entry.runtime_data.controller
    async_add_entities(
        [
            FluepdotRotationNumber(controller),
            FluepdotSetDelayNumber(controller),
        ]
    )


class FluepdotRotationNumber(FluepdotEntity, NumberEntity):
    """Anzeigedauer je Rotationsseite."""

    _attr_translation_key = "rotation_interval"
    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 10
    _attr_native_max_value = 3600
    _attr_native_step = 5
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller) -> None:
        super().__init__(controller, "rotation_interval")

    @property
    def native_value(self) -> float:
        return float(self.controller.settings.rotation_interval)

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.async_update_settings(rotation_interval=int(value))


class FluepdotSetDelayNumber(FluepdotEntity, NumberEntity):
    """Setzverzoegerung je Spalte - kuerzer ist schneller, aber riskanter."""

    _attr_translation_key = "set_delay"
    _attr_icon = "mdi:speedometer"
    _attr_native_min_value = 200
    _attr_native_max_value = 4000
    _attr_native_step = 50
    _attr_native_unit_of_measurement = "µs"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller) -> None:
        super().__init__(controller, "set_delay")

    @property
    def native_value(self) -> float:
        return float(self.controller.settings.set_delay_us)

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.async_update_settings(set_delay_us=int(value))
