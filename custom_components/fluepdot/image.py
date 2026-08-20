"""Live-Vorschau der Anzeige als Bild.

Das PNG entsteht ohne externe Bibliothek direkt aus dem Framebuffer - mit
runden Punkten, damit die Vorschau aussieht wie die echte Tafel.
"""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import FluepdotEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([FluepdotPreviewImage(hass, entry.runtime_data.controller)])


class FluepdotPreviewImage(FluepdotEntity, ImageEntity):
    """Zeigt, was gerade auf der Tafel steht."""

    _attr_translation_key = "preview"
    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, controller) -> None:
        FluepdotEntity.__init__(self, controller, "preview")
        ImageEntity.__init__(self, hass)
        self._cached: bytes | None = None
        self._signature: str | None = None
        self._attr_image_last_updated = dt_util.utcnow()

    @callback
    def _handle_update(self) -> None:
        self._refresh_cache()
        super()._handle_update()

    def _refresh_cache(self) -> None:
        signature = self.controller.last_framebuffer.to_ascii()
        if signature == self._signature:
            return
        self._signature = signature
        self._cached = self.controller.last_framebuffer.to_png(6)
        self._attr_image_last_updated = dt_util.utcnow()

    async def async_image(self) -> bytes | None:
        self._refresh_cache()
        return self._cached

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._refresh_cache()
        self.async_write_ha_state()
