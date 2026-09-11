"""Tenký klient Elysium backendu pre Home Assistant komponent."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
TOKEN_REFRESH_MARGIN_SECONDS = 60
POLL_AFTER_HEADER = "X-Elysium-Poll-After"


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
        body, _ = await self._request_with_headers(method, url, payload)
        return body

    async def _request_with_headers(
        self, method: str, url: str, payload: dict[str, Any] | None = None
    ) -> tuple[Any, dict[str, str]]:
        token = await self._access()
        request_id = str(uuid.uuid4())
        try:
            async with self._session.request(
                method,
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Request-ID": request_id,
                },
                json=payload,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status == 401:
                    self._access_token = None
                    raise ElysiumAuthError(f"{url} rejected the access token")
                if response.status >= 400:
                    raise ElysiumApiError(f"{url} returned {response.status}")
                headers = dict(response.headers)
                if response.status == 204 or not response.content_length:
                    return None, headers
                return await response.json(), headers
        except aiohttp.ClientError as error:
            raise ElysiumApiError(f"Could not reach {url}: {error}") from error

    async def due_sessions(self) -> tuple[list[dict[str, Any]], int | None]:
        """Return due work and the backend-selected next poll delay."""
        payload, headers = await self._request_with_headers(
            "GET", f"{self._reward}/api/rewards/sessions/due"
        )
        raw_interval = headers.get(POLL_AFTER_HEADER)
        try:
            poll_after = int(raw_interval) if raw_interval is not None else None
        except ValueError:
            _LOGGER.warning("Ignoring invalid %s header: %s", POLL_AFTER_HEADER, raw_interval)
            poll_after = None
        return payload or [], poll_after

    async def report_session_closed(
        self,
        session_id: str,
        succeeded: bool,
        error_message: str | None = None,
        provider_confirmed: bool = False,
    ) -> None:
        """Report command outcome and whether HA state readback confirmed it."""
        await self._request(
            "POST",
            f"{self._reward}/api/rewards/sessions/{session_id}/completion-result",
            {
                "succeeded": succeeded,
                "error_message": error_message,
                "provider_confirmed": provider_confirmed,
            },
        )

    async def pending_executions(self) -> list[dict[str, Any]]:
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
