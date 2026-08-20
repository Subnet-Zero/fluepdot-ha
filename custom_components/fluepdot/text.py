"""Freitextfeld: was hier steht, steht auf der Anzeige."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DISPLAY_MODE_MANUAL, PRIORITY_NORMAL, SOURCE_TEXT_ENTITY
from .entity import FluepdotEntity
from .render import text_payload


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([FluepdotMessageText(entry.runtime_data.controller)])


class FluepdotMessageText(FluepdotEntity, TextEntity):
    """Nachricht, die direkt auf die Anzeige geschrieben wird."""

    _attr_translation_key = "message"
    _attr_icon = "mdi:form-textbox"
    _attr_mode = TextMode.TEXT
    _attr_native_max = 255

    def __init__(self, controller) -> None:
        super().__init__(controller, "message")

    @property
    def native_value(self) -> str:
        return self.controller.settings.last_text

    async def async_set_value(self, value: str) -> None:
        await self.controller.async_update_settings(
            last_text=value, display_mode=DISPLAY_MODE_MANUAL
        )
        payload = text_payload(
            value,
            font=self.controller.settings.default_font,
            align=self.controller.settings.align,
        )
        await self.controller.async_show(
            payload, priority=PRIORITY_NORMAL, source=SOURCE_TEXT_ENTITY
        )
