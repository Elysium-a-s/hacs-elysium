"""Tenký klient Elysium backendu pre Home Assistant komponent.

Komponent sa backendu preukazuje **agent tokenom** centrálnej jednotky, ktorý
doňho pri párovaní vložila mobilná appka. Ten sa vymieňa za krátkodobý access
token — bežný Elysium JWT — vďaka čomu komponent volá presne tie isté
endpointy ako appka a reward-service ani behavior-engine o ňom nemusia vedieť.

Viac v docs/adr/0001-kto-vlastni-vykonavanie.md.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

# Access token platí 15 minút. Obnovujeme ho o minútu skôr, aby nevypršal
# uprostred cyklu, v ktorom sa už zamyká zariadenie.
TOKEN_REFRESH_MARGIN_SECONDS = 60


class ElysiumApiError(Exception):
    """Backend odpovedal chybou alebo je nedostupný."""


class ElysiumAuthError(ElysiumApiError):
    """Agent token backend neprijal — jednotku treba spárovať nanovo."""


class ElysiumApi:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        integration_base_url: str,
        reward_base_url: str,
        behavior_base_url: str,
        agent_token: str,
    ) -> None:
        self._session = session
        self._integration = integration_base_url.rstrip("/")
        self._reward = reward_base_url.rstrip("/")
        self._behavior = behavior_base_url.rstrip("/")
        self._agent_token = agent_token
        self._access_token: str | None = None
        self._access_expires_at: float = 0.0

    # ---- Autentifikácia --------------------------------------------------

    async def _access(self) -> str:
        if self._access_token and time.monotonic() < self._access_expires_at:
            return self._access_token

        url = f"{self._integration}/api/integration/agent/token"
        try:
            async with self._session.post(
                url,
                headers={"Authorization": f"Bearer {self._agent_token}"},
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status == 401:
                    raise ElysiumAuthError(
                        "Elysium rejected this hub's agent token — re-pair the "
                        "central unit from the mobile app."
                    )
                if response.status >= 400:
                    raise ElysiumApiError(f"{url} returned {response.status}")
                payload = await response.json()
        except aiohttp.ClientError as error:
            raise ElysiumApiError(f"Could not reach {url}: {error}") from error

        self._access_token = payload["access_token"]
        self._access_expires_at = (
            time.monotonic()
            + max(0, int(payload.get("expires_in", 900)) - TOKEN_REFRESH_MARGIN_SECONDS)
        )
        return self._access_token

    async def _request(
        self, method: str, url: str, payload: dict[str, Any] | None = None
    ) -> Any:
        token = await self._access()
        try:
            async with self._session.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status == 401:
                    # Access token mohol vypršať skôr, než sme čakali. Zahodíme
                    # ho, aby si ho ďalší cyklus vypýtal nanovo; opakovať volanie
                    # tu by pri odvolanom agent tokene znamenalo nekonečnú slučku.
                    self._access_token = None
                    raise ElysiumAuthError(f"{url} rejected the access token")
                if response.status >= 400:
                    raise ElysiumApiError(f"{url} returned {response.status}")
                if response.status == 204 or not response.content_length:
                    return None
                return await response.json()
        except aiohttp.ClientError as error:
            raise ElysiumApiError(f"Could not reach {url}: {error}") from error

    # ---- Práca, ktorú má komponent vykonať -------------------------------

    async def due_sessions(self) -> list[dict[str, Any]]:
        """Reward sessions, ktorým vypršal čas a majú sa zamknúť späť."""
        return await self._request("GET", f"{self._reward}/api/rewards/sessions/due") or []

    async def report_session_closed(
        self, session_id: str, succeeded: bool, error_message: str | None = None
    ) -> None:
        await self._request(
            "POST",
            f"{self._reward}/api/rewards/sessions/{session_id}/completion-result",
            {"succeeded": succeeded, "error_message": error_message},
        )

    async def pending_executions(self) -> list[dict[str, Any]]:
        """Akcie, ktoré behavior-engine vytvoril a nikto ich zatiaľ nevykonal."""
        payload = await self._request(
            "GET", f"{self._behavior}/api/behavior/action-executions/pending"
        )
        return (payload or {}).get("items", [])

    async def report_execution(
        self, execution_id: str, succeeded: bool, error_message: str | None = None
    ) -> None:
        await self._request(
            "POST",
            f"{self._behavior}/api/behavior/action-executions/{execution_id}/result",
            {"succeeded": succeeded, "error_message": error_message},
        )
