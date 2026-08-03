# This directory is the `Elysium-a-s/hacs-elysium` repository

HACS resolves an integration at the **repository root**: it expects
`custom_components/<domain>/manifest.json` and `hacs.json` there. Nothing lets
it descend into a subdirectory, so it cannot install from this monorepo — and
this monorepo should not become a HACS repository, because it is six FastAPI
services that have nothing to do with Home Assistant.

So the contents of `home-assistant/` are the new repository, one-to-one:

```
home-assistant/custom_components/elysium/   →   custom_components/elysium/
home-assistant/hacs.json                    →   hacs.json
home-assistant/README.md                    →   README.md
home-assistant/tests/                       →   tests/
home-assistant/pytest.ini                   →   pytest.ini
home-assistant/.github/workflows/           →   .github/workflows/
```

`.github/workflows/` in here is inert — GitHub only reads workflows from the
repository root — so it sits ready rather than running twice.

## Moving it

```bash
git subtree split --prefix=home-assistant -b hacs-elysium
git push git@github.com:Elysium-a-s/hacs-elysium.git hacs-elysium:main
```

`subtree split` keeps the history of these files rather than landing them as
one initial commit, which matters the first time someone asks why the pairing
code replaced the token field.

Afterwards, delete this directory here and leave a pointer, so there is one
copy rather than two that drift.

## Until then

`.github/workflows/ha-component.yml` in the monorepo runs the tests and the
manifest checks on every change under `home-assistant/`, so the component does
not go unchecked while it waits. What it cannot do is make HACS able to
install it. That needs the repository.
