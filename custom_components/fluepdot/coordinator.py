"""Regelmaessiger Abruf des Framebuffers.

Der Poll hat zwei Aufgaben: die Vorschau aktuell halten und erkennen, ob
jemand anderes (etwa die Weboberflaeche flipdot-web) auf die Anzeige
geschrieben hat.
"""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import FluepdotClient, FluepdotError
from .const import DOMAIN
from .controller import FluepdotController

_LOGGER = logging.getLogger(__name__)


class FluepdotCoordinator(DataUpdateCoordinator[str | None]):
    """Holt den Framebuffer im Intervall."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: FluepdotClient,
        controller: FluepdotController,
        interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=max(10, interval)),
            config_entry=entry,
        )
        self.client = client
        self.controller = controller

    async def _async_update_data(self) -> str | None:
        try:
            raw = await self.client.get_framebuffer()
        except FluepdotError as err:
            self.controller.handle_poll(None, str(err))
            return self.data
        self.controller.handle_poll(raw, None)
        return raw
