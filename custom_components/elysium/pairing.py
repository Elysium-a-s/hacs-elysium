"""Výmena párovacieho kódu za agent token (ELYSIUM-108).

Zámerne mimo `config_flow.py`: na tomto volaní nie je nič, čo by patrilo Home
Assistantu. Je to jeden HTTP request a mapovanie odpovede na dôvod, ktorý sa
dá ukázať používateľovi — a práve to sú veci, ktoré chceme mať otestované bez
toho, aby sme na to potrebovali celý HA harness.
"""

from __future__ import annotations

import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class PairingFailed(Exception):
    """Párovanie neprešlo. `args[0]` je kľúč chybovej hlášky pre formulár."""


async def async_redeem_pairing_code(
    session: aiohttp.ClientSession, integration_base_url: str, code: str
) -> str:
    """Vymení kód za agent token jednotky.

    Vracia token, alebo vyhodí `PairingFailed` s dôvodom pre formulár. Dôvod
    nikdy nerozlišuje „kód neexistuje" od „kód vypršal" — backend to zámerne
    nerozlišuje tiež, aby sa z odpovede nedalo vyčítať, ktorý tip trafil
    existujúcu domácnosť.
    """
    url = f"{integration_base_url.rstrip('/')}/api/integration/agent/pair"
    try:
        async with session.post(
            url, json={"pairing_code": code}, timeout=REQUEST_TIMEOUT
        ) as response:
            if response.status == 400:
                raise PairingFailed("invalid_code")
            if response.status >= 400:
                raise PairingFailed("cannot_connect")
            payload = await response.json()
    except aiohttp.ClientError as error:
        # Do logu ide adresa a dôvod, nie kód. Kód je credential — krátky a o
        # desať minút bezcenný, ale kým platí, je to celý prístup k domácnosti.
        _LOGGER.debug("Pairing request to %s failed: %s", url, error)
        raise PairingFailed("cannot_connect") from error

    token = payload.get("agent_token")
    if not token:
        # 200 bez tokenu je rozbitý backend, nie zlý kód. Povedať používateľovi
        # „skús iný kód" by ho poslalo opravovať niečo, čo nie je pokazené.
        raise PairingFailed("cannot_connect")
    return token
