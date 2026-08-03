"""The diagnostics export must not carry the credential (ELYSIUM-108).

Diagnostics exist to be handed to somebody else — attached to an issue, pasted
into a forum thread, dropped into a support chat. This file is written on the
assumption the export ends up somewhere public, so the assertion that matters
is not "is the token redacted" but "does the token appear anywhere in the
output at all, under any key, at any depth".

`diagnostics.py` imports Home Assistant only for type annotations, so the two
names it needs are stubbed and the real module is loaded and called. Testing a
re-implementation would prove something about the copy.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "elysium"
MODULE = COMPONENT / "diagnostics.py"

TOKEN = "unmistakable-agent-token-value-42"


def _load_diagnostics():
    """Load the real module with Home Assistant's two symbols stubbed out.

    Both are used purely as annotations. Standing in for them costs nothing
    and keeps this runnable without the HA harness — which is the difference
    between this being checked on every push and not at all.
    """
    for name, attrs in {
        "homeassistant": {},
        "homeassistant.config_entries": {"ConfigEntry": object},
        "homeassistant.core": {"HomeAssistant": object},
    }.items():
        module = sys.modules.setdefault(name, types.ModuleType(name))
        for attr, value in attrs.items():
            setattr(module, attr, value)

    const_spec = importlib.util.spec_from_file_location(
        "elysium_const", COMPONENT / "const.py"
    )
    const = importlib.util.module_from_spec(const_spec)
    const_spec.loader.exec_module(const)
    sys.modules["elysium_const"] = const

    source = MODULE.read_text().replace("from .const import", "from elysium_const import")
    module = types.ModuleType("elysium_diagnostics")
    exec(compile(source, str(MODULE), "exec"), module.__dict__)
    return module


diagnostics = _load_diagnostics()


class FakeEntry:
    def __init__(self, data, options=None):
        self.data = data
        self.options = options or {}
        self.version = 3
        self.source = "user"
        self.state = "loaded"


class FakeHass:
    def __init__(self, runtime):
        self.data = {"elysium": runtime}


async def export(merged: dict, runtime: dict | None = None) -> dict:
    return await diagnostics.async_get_config_entry_diagnostics(
        FakeHass(runtime or {}), FakeEntry(merged)
    )


def flatten(value, found=None):
    """Every key and scalar in the structure, however deeply nested."""
    found = [] if found is None else found
    if isinstance(value, dict):
        for key, item in value.items():
            found.append(str(key))
            flatten(item, found)
    elif isinstance(value, (list, tuple)):
        for item in value:
            flatten(item, found)
    else:
        found.append(str(value))
    return found


class TestTheTokenNeverLeaves:
    async def test_it_appears_nowhere_in_the_output(self):
        """The assertion this file exists for.

        Deliberately not "the value under `agent_token` is redacted": the
        token must not reach the export by any route, including a key nobody
        thought about when they added it.
        """
        output = await export(
            {
                "agent_token": TOKEN,
                "integration_base_url": "https://integration.example",
                "reward_base_url": "https://reward.example",
                "behavior_base_url": "https://behavior.example",
            }
        )

        assert TOKEN not in json.dumps(output)
        assert TOKEN not in flatten(output)

    async def test_an_unexpected_key_is_dropped_rather_than_included(self):
        """The export lists what may appear, not what must be hidden.

        A future key holding a second credential is the realistic way this
        leaks, and it leaks silently. Allow-listing is what makes that
        impossible rather than merely unlikely.
        """
        output = await export(
            {
                "agent_token": TOKEN,
                "integration_base_url": "https://integration.example",
                "some_future_secret": "another-credential-nobody-updated-this-for",
            }
        )

        assert "another-credential-nobody-updated-this-for" not in json.dumps(output)
        assert "some_future_secret" not in json.dumps(output)

    async def test_it_still_says_whether_a_token_is_configured(self):
        """Redacting everything would make the export useless. "Is this hub
        paired?" is the first question anyone reading it has."""
        paired = await export({"agent_token": TOKEN})
        unpaired = await export({})

        assert paired["agent_token"]["configured"] is True
        assert paired["agent_token"]["length"] == len(TOKEN)
        assert unpaired["agent_token"]["configured"] is False
        assert unpaired["agent_token"]["length"] == 0

    async def test_the_urls_are_kept(self):
        """Not secret — they are hard-coded defaults — and they are the first
        thing to check when a hub reaches nothing."""
        output = await export({"integration_base_url": "https://staging.example"})

        assert output["config"]["integration_base_url"] == "https://staging.example"

    async def test_it_reports_what_the_component_is_holding(self):
        """Zero rules on a paired hub is a different fault from an unpaired
        hub, and nothing else in the export distinguishes them."""
        output = await export({"agent_token": TOKEN}, {"rules": [1, 2], "helpers": [1]})

        assert output["stored"] == {"rules": 2, "helpers": 1}

    async def test_it_survives_a_component_that_never_started(self):
        """Diagnostics are downloaded precisely when something is wrong, so
        the one case it must not raise in is the broken one."""
        output = await export({}, {"rules": None, "helpers": None})

        assert output["stored"] == {"rules": 0, "helpers": 0}


class TestTheSourceStaysHonest:
    def test_the_module_allow_lists_rather_than_redacts(self):
        """Guards the module's shape, not just its current output.

        Rewritten to blank out known secrets instead of listing what may
        appear, every test above would still pass while the real export
        started leaking the next key someone added.
        """
        tree = ast.parse(MODULE.read_text())
        names = {
            node.targets[0].id
            for node in tree.body
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        }

        assert "SAFE_KEYS" in names, "the export must name what is allowed out"
        assert not (names & {"REDACT", "SENSITIVE_KEYS", "TO_REDACT"}), (
            "listing what to hide means every new key leaks until someone "
            "remembers to add it"
        )
