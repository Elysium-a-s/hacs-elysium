import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

# CI intentionally does not install Home Assistant. Load the two modules under
# test without executing custom_components.elysium.__init__, which imports the
# full HA runtime. coordinator.py only needs these symbols to define its class.
_COMPONENT_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "elysium"

elysium_package = types.ModuleType("custom_components.elysium")
elysium_package.__path__ = [str(_COMPONENT_DIR)]
sys.modules["custom_components.elysium"] = elysium_package

homeassistant = types.ModuleType("homeassistant")
homeassistant.__path__ = []
core = types.ModuleType("homeassistant.core")
core.HomeAssistant = object
helpers = types.ModuleType("homeassistant.helpers")
helpers.__path__ = []
update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")


class _DataUpdateCoordinator:
    @classmethod
    def __class_getitem__(cls, _item):
        return cls


update_coordinator.DataUpdateCoordinator = _DataUpdateCoordinator
sys.modules["homeassistant"] = homeassistant
sys.modules["homeassistant.core"] = core
sys.modules["homeassistant.helpers"] = helpers
sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator

from custom_components.elysium.api import ElysiumApi, ElysiumApiError
from custom_components.elysium import coordinator as coordinator_module
from custom_components.elysium.coordinator import ElysiumExecutionCoordinator, _expected_states


class _States:
    def __init__(self, values):
        self._values = list(values)

    def get(self, entity_id):
        value = self._values.pop(0) if len(self._values) > 1 else self._values[0]
        if value is None:
            return None
        return SimpleNamespace(state=value)


def _coordinator_with_states(values):
    coordinator = object.__new__(ElysiumExecutionCoordinator)
    coordinator.hass = SimpleNamespace(states=_States(values))
    return coordinator


@pytest.mark.asyncio
async def test_completed_execution_is_journaled_before_backend_ack():
    api = SimpleNamespace(
        pending_executions=AsyncMock(return_value=[{
            "execution_id": "execution-1", "service_domain": "switch",
            "service_name": "turn_on", "entity_id": "switch.tv",
        }]),
        report_execution=AsyncMock(side_effect=ElysiumApiError("offline")),
    )
    store = SimpleNamespace(async_save=AsyncMock())
    coordinator = object.__new__(ElysiumExecutionCoordinator)
    coordinator._api = api
    coordinator._execution_journal = {}
    coordinator._execution_journal_store = store
    coordinator._call_service = AsyncMock()

    assert await coordinator._process_pending_executions() == 1
    coordinator._call_service.assert_awaited_once()
    store.async_save.assert_awaited_once()
    assert "execution-1" in coordinator._execution_journal

    api.report_execution.side_effect = None
    await coordinator._process_pending_executions()
    coordinator._call_service.assert_awaited_once()
    api.report_execution.assert_awaited_with("execution-1", True, None)


def test_expected_reward_states_match_backend_contract():
    assert _expected_states("turn_off") == {"off"}
    assert _expected_states("lock") == {"locked"}
    assert _expected_states("close_cover") == {"closed"}
    assert _expected_states("toggle") == set()


@pytest.mark.asyncio
async def test_readback_confirms_matching_state(monkeypatch):
    coordinator = _coordinator_with_states(["on", "off"])

    async def no_delay(_):
        return None

    monkeypatch.setattr(coordinator_module.asyncio, "sleep", no_delay)
    confirmed, error = await coordinator._confirm_service_result(
        {"entity_id": "switch.tv", "service_name": "turn_off"}
    )

    assert confirmed is True
    assert error is None


@pytest.mark.asyncio
async def test_readback_rejects_state_mismatch(monkeypatch):
    coordinator = _coordinator_with_states(["on"])

    async def no_delay(_):
        return None

    monkeypatch.setattr(coordinator_module.asyncio, "sleep", no_delay)
    confirmed, error = await coordinator._confirm_service_result(
        {"entity_id": "switch.tv", "service_name": "turn_off"}
    )

    assert confirmed is False
    assert "expected" in error


@pytest.mark.asyncio
async def test_readback_rejects_unavailable():
    coordinator = _coordinator_with_states(["unavailable"])

    confirmed, error = await coordinator._confirm_service_result(
        {"entity_id": "switch.tv", "service_name": "turn_off"}
    )

    assert confirmed is False
    assert "unavailable" in error


@pytest.mark.asyncio
async def test_reward_result_payload_includes_provider_confirmation():
    api = object.__new__(ElysiumApi)
    api._reward = "https://reward.test"
    api._request = AsyncMock(return_value=None)

    await api.report_session_closed(
        "session-1", True, None, provider_confirmed=True
    )

    api._request.assert_awaited_once_with(
        "POST",
        "https://reward.test/api/rewards/sessions/session-1/completion-result",
        {
            "succeeded": True,
            "error_message": None,
            "provider_confirmed": True,
        },
    )
