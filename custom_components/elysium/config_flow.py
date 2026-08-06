"""Párovanie jednotky kódom z appky (ELYSIUM-108)."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_AGENT_TOKEN,
    CONF_BEHAVIOR_URL,
    CONF_INTEGRATION_URL,
    CONF_PAIRING_CODE,
    CONF_POLL_INTERVAL_SECONDS,
    CONF_REWARD_URL,
    DEFAULT_BEHAVIOR_URL,
    DEFAULT_INTEGRATION_URL,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_REWARD_URL,
    DOMAIN,
    MAX_POLL_INTERVAL_SECONDS,
    MIN_POLL_INTERVAL_SECONDS,
)
from .pairing import PairingFailed, async_redeem_pairing_code

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PAIRING_CODE): str,
        vol.Optional(CONF_INTEGRATION_URL, default=DEFAULT_INTEGRATION_URL): str,
        vol.Optional(CONF_REWARD_URL, default=DEFAULT_REWARD_URL): str,
        vol.Optional(CONF_BEHAVIOR_URL, default=DEFAULT_BEHAVIOR_URL): str,
    }
)


class ElysiumConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 3

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=SCHEMA)

        session = async_get_clientsession(self.hass)
        try:
            token = await async_redeem_pairing_code(
                session,
                user_input[CONF_INTEGRATION_URL],
                user_input[CONF_PAIRING_CODE],
            )
        except PairingFailed as error:
            return self.async_show_form(
                step_id="user", data_schema=SCHEMA, errors={"base": error.args[0]}
            )

        data = {k: v for k, v in user_input.items() if k != CONF_PAIRING_CODE}
        data[CONF_AGENT_TOKEN] = token
        return self.async_create_entry(title="Elysium", data=data)

    @staticmethod
    def async_get_options_flow(config_entry):
        return ElysiumOptionsFlow(config_entry)


class ElysiumOptionsFlow(config_entries.OptionsFlow):
    """Prepárovanie, adresy a vedomý override poll intervalu."""

    def __init__(self, config_entry) -> None:
        self._entry = config_entry

    def _schema(self, current: dict):
        poll_value = int(
            current.get(CONF_POLL_INTERVAL_SECONDS, DEFAULT_POLL_INTERVAL_SECONDS)
        )
        return vol.Schema(
            {
                vol.Optional(CONF_PAIRING_CODE, default=""): str,
                vol.Optional(
                    CONF_INTEGRATION_URL,
                    default=current.get(CONF_INTEGRATION_URL, DEFAULT_INTEGRATION_URL),
                ): str,
                vol.Optional(
                    CONF_REWARD_URL,
                    default=current.get(CONF_REWARD_URL, DEFAULT_REWARD_URL),
                ): str,
                vol.Optional(
                    CONF_BEHAVIOR_URL,
                    default=current.get(CONF_BEHAVIOR_URL, DEFAULT_BEHAVIOR_URL),
                ): str,
                vol.Optional(
                    CONF_POLL_INTERVAL_SECONDS,
                    default=poll_value,
                ): vol.Any(
                    vol.Equal(DEFAULT_POLL_INTERVAL_SECONDS),
                    vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_POLL_INTERVAL_SECONDS,
                            max=MAX_POLL_INTERVAL_SECONDS,
                        ),
                    ),
                ),
            }
        )

    async def async_step_init(self, user_input=None):
        current = {**self._entry.data, **self._entry.options}
        schema = self._schema(current)
        if user_input is None:
            return self.async_show_form(step_id="init", data_schema=schema)

        options = {k: v for k, v in user_input.items() if k != CONF_PAIRING_CODE}
        code = user_input.get(CONF_PAIRING_CODE, "").strip()
        if code:
            session = async_get_clientsession(self.hass)
            try:
                options[CONF_AGENT_TOKEN] = await async_redeem_pairing_code(
                    session, user_input[CONF_INTEGRATION_URL], code
                )
            except PairingFailed as error:
                return self.async_show_form(
                    step_id="init", data_schema=schema, errors={"base": error.args[0]}
                )
        elif current.get(CONF_AGENT_TOKEN):
            options[CONF_AGENT_TOKEN] = current[CONF_AGENT_TOKEN]

        return self.async_create_entry(title="", data=options)
