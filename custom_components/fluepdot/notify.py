"""Die Anzeige als regulaeres Benachrichtigungsziel."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ALIGN_CENTER, MODE_COMPOSE, PRIORITY_HIGH, SOURCE_NOTIFY
from .entity import FluepdotEntity
from .render import lines_payload


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([FluepdotNotify(entry.runtime_data.controller)])


class FluepdotNotify(FluepdotEntity, NotifyEntity):
    """notify.send_message schreibt direkt auf die Tafel."""

    _attr_translation_key = "notify"
    _attr_icon = "mdi:bullhorn"

    def __init__(self, controller) -> None:
        super().__init__(controller, "notify")

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        font = self.controller.fonts.get(self.controller.settings.default_font)
        text = f"{title}: {message}" if title else message
        lines = font.wrap(text, self.controller.width)
        payload = lines_payload(
            lines[:3],
            font=self.controller.settings.default_font,
            align=ALIGN_CENTER,
            description=text,
        )
        payload.mode = MODE_COMPOSE
        await self.controller.async_show(
            payload,
            priority=PRIORITY_HIGH,
            duration=120,
            source=SOURCE_NOTIFY,
        )
