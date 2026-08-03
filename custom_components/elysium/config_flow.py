"""Párovanie jednotky kódom z appky (ELYSIUM-108).

Predtým tu bolo pole na agent token — 43 náhodných znakov, ktoré mal
používateľ prepísať z telefónu do prehliadača. To je presne ten ručný krok,
ktorý mal zaniknúť, a bol aj poslednou vecou medzi „nainštaluj z HACS" a
funkčným hubom.

Teraz sa zadáva osemznakový kód a token si komponent vyzdvihne sám. Na
obrazovke sa token neobjaví a nikto ho neopisuje.

Samotná výmena je v `pairing.py` — nie je na nej nič, čo by patrilo Home
Assistantu, a tam sa dá otestovať bez celého HA harnessu.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_AGENT_TOKEN,
    CONF_BEHAVIOR_URL,
    CONF_INTEGRATION_URL,
    CONF_PAIRING_CODE,
    CONF_REWARD_URL,
    DEFAULT_BEHAVIOR_URL,
    DEFAULT_INTEGRATION_URL,
    DEFAULT_REWARD_URL,
    DOMAIN,
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
    # 3: `agent_token` sa už nezadáva ručne, získava sa výmenou za kód.
    # Existujúce entry ostávajú platné — token v nich je stále token, takže
    # migrácia nemá čo prepisovať.
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

        # Kód sa neukladá. Je jednorazový, takže uložiť by sa dal už len ako
        # nepoužiteľný reťazec, ktorý však stále vyzerá ako credential.
        data = {k: v for k, v in user_input.items() if k != CONF_PAIRING_CODE}
        data[CONF_AGENT_TOKEN] = token
        return self.async_create_entry(title="Elysium", data=data)

    @staticmethod
    def async_get_options_flow(config_entry):
        return ElysiumOptionsFlow(config_entry)


class ElysiumOptionsFlow(config_entries.OptionsFlow):
    """Prepárovanie a zmena adries bez odstránenia integrácie.

    Kód je nepovinný: kto sem prišiel len prehodiť službu na staging, nemá
    dôvod pýtať si nový kód z appky. Prázdne pole teda znamená „token nechaj
    tak", nie „zmaž ho".
    """

    def __init__(self, config_entry) -> None:
        self._entry = config_entry

    def _schema(self, current: dict):
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
            # Bez tohto by uloženie formulára s prázdnym kódom vymazalo token,
            # ktorý tam už bol: options prekrývajú data, takže chýbajúci kľúč
            # tu nie je „nechaj tak", ale „nastav na nič".
            options[CONF_AGENT_TOKEN] = current[CONF_AGENT_TOKEN]

        return self.async_create_entry(title="", data=options)
