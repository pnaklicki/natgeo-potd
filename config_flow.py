"""Config flow: a single confirmation step to add the integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class NatGeoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for National Geographic Photo of the Day."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Show the introduction and create the entry on confirmation."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title="National Geographic Photo of the Day", data={}
            )

        return self.async_show_form(step_id="user")
