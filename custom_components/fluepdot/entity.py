"""Gemeinsame Basisklasse aller Entitaeten dieser Integration."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_STATE_CHANGED
from .controller import FluepdotController


class FluepdotEntity(Entity):
    """Basis: Geraetezuordnung, Verfuegbarkeit und Aktualisierung."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: FluepdotController, key: str) -> None:
        self.controller = controller
        self._attr_unique_id = f"{controller.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller.entry.entry_id)},
            name="Flipdot",
            manufacturer="fluepdot",
            model=f"fluepboard {controller.width}x{controller.height}",
            configuration_url=controller.client.host,
        )

    @property
    def available(self) -> bool:
        return self.controller.available

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATE_CHANGED.format(self.controller.entry.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
