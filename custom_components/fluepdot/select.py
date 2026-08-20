"""Auswahllisten der Flipdot-Anzeige."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ALIGNMENTS, DISPLAY_MODES
from .entity import FluepdotEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    controller = entry.runtime_data.controller
    async_add_entities(
        [
            FluepdotModeSelect(controller),
            FluepdotFontSelect(controller),
            FluepdotAlignSelect(controller),
        ]
    )


class FluepdotModeSelect(FluepdotEntity, SelectEntity):
    """Betriebsart der Anzeige."""

    _attr_translation_key = "mode"
    _attr_icon = "mdi:view-carousel"
    _attr_options = DISPLAY_MODES

    def __init__(self, controller) -> None:
        super().__init__(controller, "mode")

    @property
    def current_option(self) -> str:
        return self.controller.settings.display_mode

    async def async_select_option(self, option: str) -> None:
        await self.controller.async_update_settings(display_mode=option)


class FluepdotFontSelect(FluepdotEntity, SelectEntity):
    """Standardschrift."""

    _attr_translation_key = "font"
    _attr_icon = "mdi:format-font"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller) -> None:
        super().__init__(controller, "font")

    @property
    def options(self) -> list[str]:
        names = list(self.controller.device_fonts)
        for name in self.controller.fonts.names:
            if name not in names:
                names.append(name)
        return names or [self.controller.settings.default_font]

    @property
    def current_option(self) -> str | None:
        current = self.controller.settings.default_font
        return current if current in self.options else None

    async def async_select_option(self, option: str) -> None:
        await self.controller.async_update_settings(default_font=option)


class FluepdotAlignSelect(FluepdotEntity, SelectEntity):
    """Ausrichtung im compose-Modus."""

    _attr_translation_key = "align"
    _attr_icon = "mdi:format-align-center"
    _attr_options = ALIGNMENTS
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller) -> None:
        super().__init__(controller, "align")

    @property
    def current_option(self) -> str:
        return self.controller.settings.align

    async def async_select_option(self, option: str) -> None:
        await self.controller.async_update_settings(align=option)
