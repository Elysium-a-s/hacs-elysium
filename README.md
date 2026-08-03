# Elysium — Home Assistant integration

Locks a reward back up when its time is out, whether or not the phone is
open. It is the second executor in the order recorded in
[`docs/adr/0001-kto-vlastni-vykonavanie.md`](https://github.com/Elysium-a-s/FastAPI-module/blob/main/docs/adr/0001-kto-vlastni-vykonavanie.md):
the one-shot automation goes first, this agent fixes what the automation
missed, and the backend sweep can only reach hubs that are visible from the
internet — which a LAN hub is not.

Without it installed, a `local` household has one mechanism instead of three.

## Install

**HACS → ⋮ → Custom repositories** → add `Elysium-a-s/hacs-elysium`,
category **Integration** → install **Elysium** → restart Home Assistant →
**Settings → Devices & Services → Add Integration → Elysium**.

It asks for a pairing code. Open Elysium on your phone, go to the central
unit, tap **Pair Home Assistant**, and type in the eight characters it shows.

The code lasts ten minutes and works once. If it expires, ask for another —
there is nothing to clean up first.

Nothing is copied into `config/` by hand, and the hub's credential is never
displayed: the code is exchanged for it behind the scenes.

## Compatibility

| Elysium | Home Assistant | Notes |
| --- | --- | --- |
| 0.6.x | 2024.10.0 and later | Pairing code replaces the pasted agent token |
| 0.5.x | 2024.10.0 and later | Agent token entered by hand |

The minimum is declared in `hacs.json`, so HACS will not offer a release to an
installation that cannot run it. The floor is 2024.10 because the config flow
uses `async_get_clientsession` and the options-flow shape settled there;
earlier versions are untested and not supported.

## Upgrading

HACS shows the update and installs it; restart Home Assistant afterwards.

Your pairing survives an upgrade — the config entry holds the agent token, and
upgrades do not touch it. Going from 0.5 to 0.6 needs no action: an entry set
up with a hand-entered token keeps working, because what changed is how the
token is *obtained*, not what it is.

## Re-pairing

**Settings → Devices & Services → Elysium → Configure**, then enter a new code
from the app. Leave the code field empty to change only the service URLs.

Asking the app for a new code invalidates the previous one, which is also how
you revoke a code you typed somewhere you should not have.

## Uninstalling

1. **Settings → Devices & Services → Elysium → ⋮ → Delete** — removes the
   config entry and the stored credential.
2. **HACS → Elysium → ⋮ → Remove** — removes the files.
3. Restart Home Assistant.

Relock automations Elysium created are named `Elysium Relock <id>` under
**Settings → Automations**. Live sessions clean up after themselves, but if
you uninstall mid-session nothing is left to do it — delete any that remain.

Removing the integration does not cancel rewards. The backend still closes
sessions whose time is up; for a LAN hub it just cannot confirm the device was
locked, and says so rather than claiming it was.

## Diagnostics

**Settings → Devices & Services → Elysium → ⋮ → Download diagnostics.**

Safe to attach to a bug report. The export deliberately lists what may appear
rather than what to hide, so the agent token is absent — not redacted, absent,
and not even a fragment of it. What you get is whether a token is configured,
which URLs are in use, and how many rules and helpers the component is
holding.

## Development

```bash
pip install aiohttp pytest pytest-aiohttp
python -m pytest tests/ -v
```

These tests deliberately run without a Home Assistant installation. Both
modules they cover — the pairing exchange and the diagnostics export — are the
parts where a mistake is either a security problem or a support problem, and
tying them to a harness that takes minutes to install is how they end up
unchecked. `pairing.py` is kept free of Home Assistant imports for exactly
this reason.

The rest of the component (coordinator, entity platforms) needs
`pytest-homeassistant-custom-component` and a matching Home Assistant version.

## Releasing

1. Bump `version` in `custom_components/elysium/manifest.json`.
2. Tag `ha-v<version>` — the tag and the manifest must agree, and CI fails the
   release if they do not.
3. The release workflow builds `elysium.zip`, checks that `manifest.json` sits
   at the archive root (HACS unpacks it straight into
   `custom_components/elysium/`, so a nested layout installs files nothing
   imports), and publishes it with a changelog.
