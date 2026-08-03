"""Download diagnostics pre Elysium (ELYSIUM-108).

Diagnostiku sťahuje používateľ a posiela ju ďalej — do issue, na fórum, do
chatu. Preto sa tu nič neredaktuje dodatočne: vymenované je len to, čo sa má
objaviť, a všetko ostatné z config entry sa zahodí. Opačné poradie (vymenovať,
čo skryť) znamená, že každý nový kľúč v entry unikne, kým si naň niekto
nespomenie.

Užitočné je práve to, čo pomôže rozhodnúť, či je hub spárovaný a či dosiahne
na backend — nie hodnota credentialu.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_AGENT_TOKEN,
    CONF_BEHAVIOR_URL,
    CONF_INTEGRATION_URL,
    CONF_REWARD_URL,
    DOMAIN,
)

# Adresy áno, credentialy nie. Adresa je to prvé, čo treba pri „hub nič
# nerobí" overiť, a nie je to tajomstvo — je predvyplnená v kóde.
SAFE_KEYS = (CONF_INTEGRATION_URL, CONF_REWARD_URL, CONF_BEHAVIOR_URL)


def _describe_credential(value: Any) -> dict[str, Any]:
    """Či token je, a či vyzerá na token — nič viac.

    Dĺžka a prítomnosť odpovedia na otázku „je jednotka spárovaná?", pre ktorú
    diagnostika existuje. Prefix ani posledné znaky tu nie sú zámerne: pri
    krátkom credentiale je „pár znakov" prekvapivo veľká časť z neho.
    """
    return {"configured": bool(value), "length": len(value) if value else 0}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    merged = {**entry.data, **entry.options}
    runtime = hass.data.get(DOMAIN, {})

    return {
        "config": {key: merged.get(key) for key in SAFE_KEYS},
        "agent_token": _describe_credential(merged.get(CONF_AGENT_TOKEN)),
        "entry": {
            "version": entry.version,
            "source": entry.source,
            "state": str(entry.state),
        },
        # Koľko pravidiel a helperov komponent drží. Prázdno pri spárovanej
        # jednotke je iná porucha než nespárovaná jednotka, a z ničoho iného
        # sa to nedá rozoznať.
        "stored": {
            "rules": len(runtime.get("rules", []) or []),
            "helpers": len(runtime.get("helpers", []) or []),
        },
    }
