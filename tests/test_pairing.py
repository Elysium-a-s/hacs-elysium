"""What the hub does with the code the user typed (ELYSIUM-108).

`pairing.py` is deliberately free of Home Assistant, so this runs against a
real aiohttp server rather than a mocked session — the thing being asserted is
how an HTTP response turns into either a token or a message the user can act
on, and a stubbed session would let that be wrong in exactly the ways that
matter.

The error mapping is the substance here. A user who typed a stale code and a
user whose Home Assistant has no internet both see a form that failed, and the
only thing telling them which problem they have is which message we chose.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from aiohttp import web

# Loaded by path, not imported as `custom_components.elysium.pairing`: the
# package's `__init__` pulls in Home Assistant, and the whole point of keeping
# this module separate is that it does not need it. Going through the package
# would quietly make that untrue again.
_spec = importlib.util.spec_from_file_location(
    "elysium_pairing",
    Path(__file__).resolve().parents[1] / "custom_components" / "elysium" / "pairing.py",
)
pairing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pairing)

PairingFailed = pairing.PairingFailed
async_redeem_pairing_code = pairing.async_redeem_pairing_code


@pytest.fixture()
def backend(aiohttp_client):
    """A stand-in integration-service whose answer each test chooses."""

    async def _serve(handler):
        app = web.Application()
        app.router.add_post("/api/integration/agent/pair", handler)
        client = await aiohttp_client(app)
        return client

    return _serve


async def test_a_valid_code_yields_the_token(backend):
    async def handler(request):
        body = await request.json()
        assert body == {"pairing_code": "ABCD2345"}
        return web.json_response(
            {"central_unit_id": "b1e1…", "agent_token": "the-real-token"}
        )

    client = await backend(handler)

    token = await async_redeem_pairing_code(client.session, str(client.make_url("")), "ABCD2345")

    assert token == "the-real-token"


async def test_the_code_is_sent_exactly_as_typed(backend):
    """Normalising is the backend's job, and only the backend's.

    If the component also trimmed and upper-cased, there would be two places
    deciding what a code means, and a change to one would silently disagree
    with the other.
    """
    seen = {}

    async def handler(request):
        seen.update(await request.json())
        return web.json_response({"agent_token": "t"})

    client = await backend(handler)

    await async_redeem_pairing_code(client.session, str(client.make_url("")), " abcd-2345 ")

    assert seen["pairing_code"] == " abcd-2345 "


async def test_a_rejected_code_asks_the_user_for_a_new_one(backend):
    """400 is the backend saying the code is unknown or expired.

    That is the one failure the user can actually fix, so it gets the message
    that tells them how.
    """
    async def handler(request):
        return web.json_response({"detail": "Unknown or expired pairing code"}, status=400)

    client = await backend(handler)

    with pytest.raises(PairingFailed) as failure:
        await async_redeem_pairing_code(client.session, str(client.make_url("")), "ZZZZZZZZ")

    assert failure.value.args[0] == "invalid_code"


async def test_a_broken_backend_is_not_blamed_on_the_code(backend):
    """A 500 means the user's code was probably fine.

    Telling them to fetch a new one would send them round a loop that cannot
    succeed, blaming the one thing that is not broken.
    """
    async def handler(request):
        return web.Response(status=500)

    client = await backend(handler)

    with pytest.raises(PairingFailed) as failure:
        await async_redeem_pairing_code(client.session, str(client.make_url("")), "ABCD2345")

    assert failure.value.args[0] == "cannot_connect"


async def test_a_success_with_no_token_is_treated_as_a_broken_backend(backend):
    """200 without a token is not a bad code either, and the component must
    not hand `None` to the coordinator as though pairing had worked."""
    async def handler(request):
        return web.json_response({"central_unit_id": "b1e1…"})

    client = await backend(handler)

    with pytest.raises(PairingFailed) as failure:
        await async_redeem_pairing_code(client.session, str(client.make_url("")), "ABCD2345")

    assert failure.value.args[0] == "cannot_connect"


async def test_an_unreachable_backend_says_so(backend):
    """The common case for a hub that has just been installed: no internet
    yet, or the URL was mistyped."""
    async def handler(request):
        return web.json_response({"agent_token": "t"})

    client = await backend(handler)

    with pytest.raises(PairingFailed) as failure:
        await async_redeem_pairing_code(
            client.session, "http://127.0.0.1:1/", "ABCD2345"
        )

    assert failure.value.args[0] == "cannot_connect"


async def test_a_trailing_slash_on_the_url_does_not_break_the_path(backend):
    """The field is typed by hand and the default is pasted from somewhere.
    A double slash would 404 and be reported as "cannot connect", which is
    true and useless."""
    async def handler(request):
        return web.json_response({"agent_token": "t"})

    client = await backend(handler)

    token = await async_redeem_pairing_code(
        client.session, str(client.make_url("")) + "///", "ABCD2345"
    )

    assert token == "t"


async def test_the_code_never_reaches_the_log(backend, caplog):
    """It is a credential while it lives. Home Assistant logs are pasted into
    forum posts and support threads more or less by default."""
    import logging

    caplog.set_level(logging.DEBUG)

    async def handler(request):
        return web.json_response({"agent_token": "t"})

    client = await backend(handler)

    with pytest.raises(PairingFailed):
        await async_redeem_pairing_code(client.session, "http://127.0.0.1:1/", "SECRET42")

    assert "SECRET42" not in caplog.text
