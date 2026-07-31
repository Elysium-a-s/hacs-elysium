import voluptuous as vol
from homeassistant import config_entries

from .const import (
    CONF_AGENT_TOKEN,
    CONF_BEHAVIOR_URL,
    CONF_INTEGRATION_URL,
    CONF_REWARD_URL,
    DEFAULT_BEHAVIOR_URL,
    DEFAULT_INTEGRATION_URL,
    DEFAULT_REWARD_URL,
    DOMAIN,
)

# Agent token vydá integration-service a do Home Assistanta ho vloží mobilná
# appka pri párovaní. Bez neho komponent funguje ako doteraz — prijíma
# pravidlá a helpery — ale nevykonáva relock ani čakajúce akcie, lebo si o ne
# nemá ako povedať.
SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_AGENT_TOKEN, default=""): str,
        vol.Optional(CONF_INTEGRATION_URL, default=DEFAULT_INTEGRATION_URL): str,
        vol.Optional(CONF_REWARD_URL, default=DEFAULT_REWARD_URL): str,
        vol.Optional(CONF_BEHAVIOR_URL, default=DEFAULT_BEHAVIOR_URL): str,
    }
)


class ElysiumConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Elysium", data=user_input)
        return self.async_show_form(step_id="user", data_schema=SCHEMA)

    @staticmethod
    def async_get_options_flow(config_entry):
        return ElysiumOptionsFlow(config_entry)


class ElysiumOptionsFlow(config_entries.OptionsFlow):
    """Umožní doplniť agent token bez odstránenia integrácie.

    Existujúce inštalácie boli nastavené ešte s prázdnym `data={}`, takže sa
    inak k vykonávaniu nedostanú.
    """

    def __init__(self, config_entry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self._entry.data, **self._entry.options}
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_AGENT_TOKEN, default=current.get(CONF_AGENT_TOKEN, "")
                ): str,
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
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
