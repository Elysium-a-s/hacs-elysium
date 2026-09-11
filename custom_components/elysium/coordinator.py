"""Vykonávacia slučka komponentu (ELYSIUM-42, ELYSIUM-81)."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import ElysiumApi, ElysiumApiError, ElysiumAuthError
from .const import (
    CONF_POLL_INTERVAL_SECONDS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DOMAIN,
    MAX_POLL_INTERVAL_SECONDS,
    MIN_POLL_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)
FALLBACK_POLL_INTERVAL = timedelta(seconds=60)
READBACK_ATTEMPTS = 5
READBACK_DELAY_SECONDS = 0.25


def _expected_states(service_name: str | None) -> set[str]:
    service = (service_name or "").lower()
    if service in {"turn_off", "off"}:
        return {"off"}
    if service in {"lock", "lock_door"}:
        return {"locked"}
    if service in {"close", "close_cover"}:
        return {"closed"}
    return set()


class ElysiumExecutionCoordinator(DataUpdateCoordinator[dict[str, int]]):
    """Ťahá z backendu splatnú prácu, vykoná ju a nahlási výsledok."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: ElysiumApi,
        poll_interval: timedelta = FALLBACK_POLL_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Elysium execution",
            update_interval=poll_interval,
        )
        self._api = api
        self._remove_keepalive_listener = self.async_add_listener(
            self._handle_coordinator_update
        )

    def _handle_coordinator_update(self) -> None:
        """Keep the coordinator subscribed without publishing a HA entity."""

    def _is_active_coordinator(self) -> bool:
        return self.hass.data.get(DOMAIN, {}).get("coordinator") is self

    def _manual_poll_override(self) -> int:
        """Read the current Options Flow value; zero keeps server control."""
        entries = self.hass.config_entries.async_entries(DOMAIN)
        if not entries:
            return DEFAULT_POLL_INTERVAL_SECONDS
        raw = entries[0].options.get(
            CONF_POLL_INTERVAL_SECONDS, DEFAULT_POLL_INTERVAL_SECONDS
        )
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return DEFAULT_POLL_INTERVAL_SECONDS
        return value

    def _apply_next_poll(self, server_seconds: int | None) -> None:
        override = self._manual_poll_override()
        selected = override if override > 0 else server_seconds
        if selected is None:
            return
        selected = max(
            MIN_POLL_INTERVAL_SECONDS,
            min(MAX_POLL_INTERVAL_SECONDS, int(selected)),
        )
        interval = timedelta(seconds=selected)
        if self.update_interval != interval:
            _LOGGER.debug("Next Elysium poll in %s seconds", selected)
            self.update_interval = interval

    async def _async_update_data(self) -> dict[str, int]:
        if not self._is_active_coordinator():
            self._remove_keepalive_listener()
            return {"relocked": 0, "executed": 0}

        relocked = await self._process_due_sessions()
        executed = await self._process_pending_executions()
        return {"relocked": relocked, "executed": executed}

    async def _process_due_sessions(self) -> int:
        try:
            due, poll_after = await self._api.due_sessions()
            self._apply_next_poll(poll_after)
        except ElysiumAuthError:
            raise
        except ElysiumApiError as error:
            _LOGGER.warning("Could not fetch due reward sessions: %s", error)
            return 0

        closed = 0
        for item in due:
            session = item.get("session", {})
            session_id = session.get("session_id")
            command = item.get("command", {})
            if session_id is None:
                continue
            try:
                await self._call_service(command)
            except Exception as error:  # noqa: BLE001
                _LOGGER.error(
                    "Could not relock %s: %s", session.get("title", session_id), error
                )
                await self._report_safely(
                    self._api.report_session_closed,
                    session_id,
                    False,
                    str(error),
                    provider_confirmed=False,
                )
                continue

            confirmed, readback_error = await self._confirm_service_result(command)
            await self._report_safely(
                self._api.report_session_closed,
                session_id,
                True,
                readback_error,
                provider_confirmed=confirmed,
            )
            if confirmed:
                closed += 1

        return closed

    async def _process_pending_executions(self) -> int:
        try:
            pending = await self._api.pending_executions()
        except ElysiumAuthError:
            raise
        except ElysiumApiError as error:
            _LOGGER.warning("Could not fetch pending executions: %s", error)
            return 0

        done = 0
        for execution in pending:
            execution_id = execution.get("execution_id")
            if execution_id is None:
                continue
            try:
                await self._call_service(execution)
            except Exception as error:  # noqa: BLE001
                _LOGGER.error("Could not run execution %s: %s", execution_id, error)
                await self._report_safely(
                    self._api.report_execution, execution_id, False, str(error)
                )
                continue

            await self._report_safely(
                self._api.report_execution, execution_id, True, None
            )
            done += 1

        return done

    async def _call_service(self, command: dict[str, Any]) -> None:
        domain = command.get("service_domain")
        service = command.get("service_name")
        entity_id = command.get("entity_id")
        if not domain or not service:
            raise ValueError(f"Incomplete command: {command}")

        data = command.get("data")
        if data is None:
            data = command.get("action_data") or {}

        payload: dict[str, Any] = dict(data)
        if entity_id:
            payload["entity_id"] = entity_id

        await self.hass.services.async_call(domain, service, payload, blocking=True)

    async def _confirm_service_result(self, command: dict[str, Any]) -> tuple[bool, str | None]:
        entity_id = command.get("entity_id")
        expected = _expected_states(command.get("service_name"))
        if not entity_id:
            return False, "Reward command has no entity_id for Home Assistant readback"
        if not expected:
            return False, "Reward command has no known confirmed state for Home Assistant readback"

        last_state: str | None = None
        for attempt in range(READBACK_ATTEMPTS):
            state = self.hass.states.get(entity_id)
            if state is not None:
                last_state = str(state.state).lower()
                if last_state in expected:
                    return True, None
                if last_state in {"unavailable", "unknown"}:
                    return False, f"Home Assistant state is {last_state}"
            if attempt + 1 < READBACK_ATTEMPTS:
                await asyncio.sleep(READBACK_DELAY_SECONDS)

        if last_state is None:
            return False, f"Home Assistant did not return state for {entity_id}"
        return False, f"Home Assistant state remained {last_state!r}; expected {sorted(expected)}"

    async def _report_safely(
        self,
        report,
        item_id,
        succeeded,
        error_message,
        *,
        provider_confirmed: bool | None = None,
    ) -> None:
        try:
            if provider_confirmed is None:
                await report(item_id, succeeded, error_message)
            else:
                await report(
                    item_id,
                    succeeded,
                    error_message,
                    provider_confirmed=provider_confirmed,
                )
        except ElysiumApiError as error:
            _LOGGER.warning("Could not report result for %s: %s", item_id, error)
