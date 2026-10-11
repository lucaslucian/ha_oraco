"""Config flow and polling interval options."""
from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import HoracoClient, parse_info
from .const import DOMAIN, DEFAULT_PORT, DEFAULT_USER


class OracoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                client = HoracoClient(async_get_clientsession(self.hass), user_input[CONF_HOST],
                                      user_input[CONF_PORT], user_input[CONF_USERNAME],
                                      user_input[CONF_PASSWORD])
                _, ports = parse_info(await client.get("/info.cgi"))
                if not ports:
                    raise ValueError("No compatible port table")
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"Horaco {user_input[CONF_HOST]}", data=user_input)
        schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Optional(CONF_PORT, default=80): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Optional(CONF_USERNAME, default=DEFAULT_USER): str,
            vol.Required(CONF_PASSWORD): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        return OracoOptionsFlow()


class OracoOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Optional("fast_interval", default=self.config_entry.options.get("fast_interval", 30)):
                vol.All(vol.Coerce(int), vol.Range(min=15, max=300))
        }))
