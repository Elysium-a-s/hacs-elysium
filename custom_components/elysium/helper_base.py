from homeassistant.helpers.entity import Entity
from homeassistant.util import slugify
from .const import DOMAIN

DOMAIN_BY_TYPE = {
    "toggle": "switch",
    "number": "number",
    "counter": "number",
    "select": "select",
    "text": "text",
    "button": "button",
    "timer": "sensor",
    "schedule": "sensor",
    "sensor": "sensor",
}

class ElysiumHelperMixin(Entity):
    _attr_should_poll = False

    def initialize(self, hass, record, store):
        self.hass = hass
        self._record = record
        self._store = store
        helper_type = record["helper_type"]
        self._attr_unique_id = f"elysium_helper_{record['helper_id']}"
        self._attr_name = record["name"]
        domain = DOMAIN_BY_TYPE[helper_type]
        self.entity_id = record.get("entity_id") or f"{domain}.elysium_{slugify(record['name'])}"

    async def persist(self):
        await self._store.async_save(self.hass.data[DOMAIN]["helpers"])

    def apply_record(self, record):
        self._record.update(record)
        self._attr_name = record["name"]
        self.write_record_state()
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        return {
            "elysium_helper_id": str(self._record["helper_id"]),
            "elysium_helper_type": self._record["helper_type"],
            "elysium_config": self._record.get("config", {}),
        }

    def write_record_state(self):
        pass


def setup_platform(hass, async_add_entities, helper_types, factory):
    data = hass.data[DOMAIN]

    def add_helper(record):
        helper_id = str(record["helper_id"])
        existing = data["entities"].get(helper_id)
        if existing is not None:
            return existing
        entity = factory(hass, record, data["helper_store"])
        data["entities"][helper_id] = entity
        async_add_entities([entity])
        return entity

    for helper_type in helper_types:
        data["add_helper"][helper_type] = add_helper

    entities = [
        factory(hass, record, data["helper_store"])
        for record in data["helpers"].values()
        if record.get("helper_type") in helper_types
    ]
    for entity in entities:
        data["entities"][str(entity._record["helper_id"])] = entity
    if entities:
        async_add_entities(entities)
