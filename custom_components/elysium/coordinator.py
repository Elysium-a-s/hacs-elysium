"""Vykonávacia slučka komponentu (ELYSIUM-42).

Do ELYSIUM-42 vykonávala akcie mobilná appka — a to len keď bola otvorená.
Odmena odomknutá na dve hodiny sa nikdy nezamkla späť, ak používateľ appku
nezapol. Anti-cheat vrstva teda stála na dobrej vôli práve toho používateľa,
ktorý mal dôvod ju obísť.

Táto slučka beží v Home Assistante, čiže vnútri domácnosti. To je jediné
miesto, ktoré dosiahne na hub v oboch režimoch pripojenia: pri `remote` naň
vidí aj backend, pri `local` nie — vtedy má token na HA jedine telefón.
Zdôvodnenie je v docs/adr/0001-kto-vlastni-vykonavanie.md.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import ElysiumApi, ElysiumApiError, ElysiumAuthError

_LOGGER = logging.getLogger(__name__)

# Kompromis medzi presnosťou zamknutia a zaťažením backendu. Relock tak
# nastane do minúty po vypršaní — namiesto "možno nikdy", čo platilo dovtedy.
DEFAULT_POLL_INTERVAL = timedelta(seconds=60)


class ElysiumExecutionCoordinator(DataUpdateCoordinator[dict[str, int]]):
    """Ťahá z backendu splatnú prácu, vykoná ju a nahlási výsledok."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: ElysiumApi,
        poll_interval: timedelta = DEFAULT_POLL_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Elysium execution",
            update_interval=poll_interval,
        )
        self._api = api

    async def _async_update_data(self) -> dict[str, int]:
        relocked = await self._process_due_sessions()
        executed = await self._process_pending_executions()
        return {"relocked": relocked, "executed": executed}

    # ---- Reward relock ---------------------------------------------------

    async def _process_due_sessions(self) -> int:
        try:
            due = await self._api.due_sessions()
        except ElysiumAuthError:
            raise
        except ElysiumApiError as error:
            _LOGGER.warning("Could not fetch due reward sessions: %s", error)
            return 0

        closed = 0
        for item in due:
            session = item.get("session", {})
            session_id = session.get("session_id")
            if session_id is None:
                continue
            try:
                await self._call_service(item.get("command", {}))
            except Exception as error:  # noqa: BLE001 — reported, then next item
                # Jedno zariadenie, ktoré sa nepodarí zamknúť, nesmie zablokovať
                # ostatné. Backend si zlyhanie poznačí a session ostane splatná,
                # takže ďalší cyklus to skúsi znova.
                _LOGGER.error(
                    "Could not relock %s: %s", session.get("title", session_id), error
                )
                await self._report_safely(
                    self._api.report_session_closed, session_id, False, str(error)
                )
                continue

            await self._report_safely(self._api.report_session_closed, session_id, True, None)
            closed += 1

        return closed

    # ---- Čakajúce akcie --------------------------------------------------

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
            except Exception as error:  # noqa: BLE001 — reported, then next item
                _LOGGER.error("Could not run execution %s: %s", execution_id, error)
                await self._report_safely(
                    self._api.report_execution, execution_id, False, str(error)
                )
                continue

            await self._report_safely(self._api.report_execution, execution_id, True, None)
            done += 1

        return done

    # ---- Spoločné --------------------------------------------------------

    async def _call_service(self, command: dict[str, Any]) -> None:
        """Zavolá HA službu popísanú príkazom z backendu.

        Reward `DeviceCommand` aj `ActionExecutionResponse` nesú tie isté
        štyri polia, len s inými názvami pre dáta — preto ten fallback.
        """
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

    async def _report_safely(self, report, item_id, succeeded, error_message) -> None:
        """Nahlási výsledok, ale zlyhanie hlásenia nezhodí celý cyklus.

        Ak sa výsledok nedoručí, položka ostane splatná a ďalší cyklus ju
        spracuje znova. Zamknúť zariadenie dvakrát je neškodné; nechať ho
        odomknuté nie je.
        """
        try:
            await report(item_id, succeeded, error_message)
        except ElysiumApiError as error:
            _LOGGER.warning("Could not report result for %s: %s", item_id, error)
