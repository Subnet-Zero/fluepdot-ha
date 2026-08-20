"""Schalter der Flipdot-Anzeige."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
            FluepdotPowerSwitch(controller),
            FluepdotQuietSwitch(controller),
            FluepdotDifferentialSwitch(controller),
        ]
    )


class FluepdotPowerSwitch(FluepdotEntity, SwitchEntity):
    """Anzeige an oder aus (aus = leerer Framebuffer, keine Schreibvorgaenge)."""

    _attr_translation_key = "display"
    _attr_icon = "mdi:dots-square"

    def __init__(self, controller) -> None:
        super().__init__(controller, "display")

    @property
    def is_on(self) -> bool:
        return self.controller.settings.display_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.controller.async_update_settings(display_on=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.controller.async_update_settings(display_on=False)


class FluepdotQuietSwitch(FluepdotEntity, SwitchEntity):
    """Ruhezeit aktivieren."""

    _attr_translation_key = "quiet"
    _attr_icon = "mdi:sleep"

    def __init__(self, controller) -> None:
        super().__init__(controller, "quiet")

    @property
    def is_on(self) -> bool:
        return self.controller.settings.quiet_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.controller.async_update_settings(quiet_enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.controller.async_update_settings(quiet_enabled=False)
        await self.controller.async_refresh_display(force=True)


class FluepdotDifferentialSwitch(FluepdotEntity, SwitchEntity):
    """Differenzielles Zeichnen: nur geaenderte Punkte klappen."""

    _attr_translation_key = "differential"
    _attr_icon = "mdi:animation"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller) -> None:
        super().__init__(controller, "differential")

    @property
    def is_on(self) -> bool:
        return self.controller.settings.differential

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.controller.async_update_settings(differential=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.controller.async_update_settings(differential=False)
