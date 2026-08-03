from homeassistant.components.switch import SwitchEntity
from .helper_base import ElysiumHelperMixin, setup_platform

class ElysiumToggle(ElysiumHelperMixin, SwitchEntity):
    _attr_icon = "mdi:toggle-switch"

    def __init__(self, hass, record, store):
        self.initialize(hass, record, store)
        self.write_record_state()

    def write_record_state(self):
        self._attr_is_on = bool(self._record.get("state", False))

    async def async_turn_on(self, **kwargs):
        self._record["state"] = True
        self.write_record_state()
        await self.persist()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self._record["state"] = False
        self.write_record_state()
        await self.persist()
        self.async_write_ha_state()

async def async_setup_entry(hass, entry, async_add_entities):
    setup_platform(hass, async_add_entities, {"toggle"}, ElysiumToggle)
