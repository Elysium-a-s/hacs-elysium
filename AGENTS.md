# hacs-elysium — agent instructions

The distributed Home Assistant Elysium custom component.

## Working method
- Search filenames/symbols first; read targeted ranges.
- Trace the active path and source of truth.
- Keep changes scoped; no unrelated refactors or speculative abstractions.
- Preserve local work; stage explicit paths and review the diff.
- Reuse existing patterns; inspect both sides of changed contracts.
- Load matching skills and linked docs only when needed.
- Avoid bulk reads and rereading unchanged context.
- Report outcome, executed checks and blockers concisely.

## Validation and delivery
- Run narrow, meaningful checks using existing commands.
- Broaden checks for affected boundaries/failures; reuse valid results.
- Instructions-only edits: validate links, skill metadata and whitespace.
- Separate review, tests, build, deployment and real-device evidence.
- Use a scoped branch/PR per repo; preserve the exact Jira key.
- Assigned Jira implementation: In Progress before work; In Review after PR.
- Jira Done requires merge and required release evidence.
- Keep credentials, signing material and private data out of logs/commits.

## Repository rules
- Preserve existing pairing/config entries and local expiry/relock behavior.
- Diagnostics must exclude credentials; do not treat helper tests as Home Assistant lifecycle proof.
- Check backend producer/consumer contracts when changing polling or pairing.

## On-demand references
- Pairing, compatibility and release process: [README](README.md).
- Lifecycle failures: `.agents/skills/ha-integration-debug/`.
- Tests and packaging: `.github/workflows/test.yml` and `.github/workflows/release.yml`.
- Read the backend execution ADR linked from README only for executor ownership changes.
