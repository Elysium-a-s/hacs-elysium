from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import DOMAIN


class ElysiumToggle(SwitchEntity):
    _attr_should_poll = False
    _attr_icon = "mdi:toggle-switch"

    def __init__(self, hass, record, store):
        self.hass = hass
        self._record = record
        self._store = store
        self._attr_unique_id = f"elysium_helper_{record['helper_id']}"
        self._attr_name = record["name"]
        self._attr_is_on = bool(record.get("is_on", False))
        self.entity_id = record.get("entity_id") or f"switch.elysium_{slugify(record['name'])}"

    async def async_turn_on(self, **kwargs):
        await self._set_state(True)

    async def async_turn_off(self, **kwargs):
        await self._set_state(False)

    async def _set_state(self, value):
        self._attr_is_on = value
        self._record["is_on"] = value
        await self._store.async_save(self.hass.data[DOMAIN]["helpers"])
        self.async_write_ha_state()


async def async_setup_entry(hass, entry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN]
    entities = []

    def add_helper(record):
        helper_id = str(record["helper_id"])
        existing = data["entities"].get(helper_id)
        if existing is not None:
            return existing
        entity = ElysiumToggle(hass, record, data["helper_store"])
        data["entities"][helper_id] = entity
        async_add_entities([entity])
        return entity

    data["add_toggle_helper"] = add_helper

    for record in data["helpers"].values():
        entities.append(ElysiumToggle(hass, record, data["helper_store"]))
    for entity in entities:
        data["entities"][str(entity._record["helper_id"])] = entity
    if entities:
        async_add_entities(entities)
