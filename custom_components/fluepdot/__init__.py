"""Home-Assistant-Integration fuer die Flipdot-Anzeige (fluepdot)."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .client import FluepdotClient, FluepdotError
from .const import (
    CONF_HOST,
    CONF_ROTATION_INTERVAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_ROTATION_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FONTS_STORAGE_KEY,
    FONTS_STORAGE_VERSION,
)
from .controller import FluepdotController
from .coordinator import FluepdotCoordinator
from .fonts import FontRegistry
from .pages import ensure_pages_file
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.NOTIFY,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
    Platform.TIME,
]


@dataclass
class FluepdotData:
    """Alles, was ein Eintrag zur Laufzeit braucht."""

    client: FluepdotClient
    controller: FluepdotController
    coordinator: FluepdotCoordinator


type FluepdotConfigEntry = ConfigEntry[FluepdotData]


async def async_setup_entry(hass: HomeAssistant, entry: FluepdotConfigEntry) -> bool:
    """Einen Eintrag einrichten."""
    session = async_get_clientsession(hass)
    client = FluepdotClient(session, entry.data[CONF_HOST])

    try:
        width, height = await client.probe()
    except FluepdotError as err:
        raise ConfigEntryNotReady(f"Flipdot nicht erreichbar: {err}") from err

    registry = FontRegistry()
    font_store: Store = Store(hass, FONTS_STORAGE_VERSION, FONTS_STORAGE_KEY)
    stored_fonts = await font_store.async_load()
    if stored_fonts:
        registry.load(stored_fonts)

    await hass.async_add_executor_job(
        ensure_pages_file, hass.config.path("fluepdot_pages.yaml")
    )

    controller = FluepdotController(hass, entry, client, registry, width, height)
    controller.settings.rotation_interval = entry.options.get(
        CONF_ROTATION_INTERVAL, DEFAULT_ROTATION_INTERVAL
    )
    await controller.async_start()

    coordinator = FluepdotCoordinator(
        hass,
        entry,
        client,
        controller,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = FluepdotData(client, controller, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_register_services(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Erst jetzt schreiben, damit die Entitaeten den Zustand mitbekommen.
    entry.async_create_background_task(
        hass, controller.async_refresh_display(force=True), "fluepdot_initial_render"
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FluepdotConfigEntry) -> bool:
    """Einen Eintrag entladen."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.controller.async_stop()
        if len(hass.config_entries.async_loaded_entries(DOMAIN)) <= 1:
            async_unregister_services(hass)
    return unloaded


async def _async_update_listener(
    hass: HomeAssistant, entry: FluepdotConfigEntry
) -> None:
    """Bei geaenderten Optionen neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)
