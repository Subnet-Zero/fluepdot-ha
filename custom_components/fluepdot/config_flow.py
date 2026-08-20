"""Einrichtungsdialog der Flipdot-Integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .client import FluepdotClient, FluepdotError
from .const import (
    CONF_HOST,
    CONF_ROTATION_INTERVAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_ROTATION_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

DEFAULT_HOST = "10.50.0.164"


class FluepdotConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtung ueber die Oberflaeche."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            session = async_get_clientsession(self.hass)
            client = FluepdotClient(session, host)
            try:
                width, height = await client.probe()
            except FluepdotError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(client.host)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Flipdot ({width}x{height})",
                    data={CONF_HOST: host},
                    options={
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        CONF_ROTATION_INTERVAL: DEFAULT_ROTATION_INTERVAL,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=DEFAULT_HOST): str}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> FluepdotOptionsFlow:
        return FluepdotOptionsFlow()


class FluepdotOptionsFlow(OptionsFlow):
    """Einstellungen nach der Einrichtung."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=10, max=600, step=5, mode=NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Optional(
                        CONF_ROTATION_INTERVAL,
                        default=options.get(
                            CONF_ROTATION_INTERVAL, DEFAULT_ROTATION_INTERVAL
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=10, max=3600, step=5, mode=NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                }
            ),
        )
