---
name: ha-integration-debug
description: Investigate Home Assistant component pairing, polling, expiry or relock failures.
---

# Ha integration debug

## Inspect
1. Capture component/HA version, failed action and redacted diagnostics.
2. Read the affected section of [README](../../../README.md), including compatibility when relevant.
3. Trace the config flow or coordinator to the specific backend endpoint and entity action.
4. For executor ownership, follow the backend ADR linked in README.

## Fix and verify
5. Preserve existing config entries and credential storage during upgrades/re-pairing.
6. Keep diagnostic exports on an allowlist; never include token fragments.
7. For timed access, test initial lock, access, expiry/relock and restart recovery as affected.
8. Run `python -m pytest tests/ -v` with the dependencies in the [test workflow](../../../.github/workflows/test.yml).
9. Pairing/diagnostics helper tests do not prove coordinator or entity lifecycle behavior.
10. Use a matching Home Assistant harness or device for lifecycle changes; state unavailable evidence.

## Release boundary
- Follow README and `.github/workflows/release.yml` only for an authorized release.
- Verify manifest version, tag and supported Home Assistant version agree.
- Publishing a tag distributes an update; do not use release automation as a test.
