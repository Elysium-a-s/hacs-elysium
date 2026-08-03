from homeassistant.components.button import ButtonEntity
from .helper_base import ElysiumHelperMixin, setup_platform

class ElysiumButton(ElysiumHelperMixin, ButtonEntity):
    _attr_icon="mdi:gesture-tap-button"
    def __init__(self,hass,record,store):
        self.initialize(hass,record,store)
    def write_record_state(self): pass
    async def async_press(self):
        self._record["press_count"]=int(self._record.get("press_count",0))+1
        await self.persist()
        self.hass.bus.async_fire("elysium_helper_pressed",{"helper_id":str(self._record["helper_id"]),"entity_id":self.entity_id})

async def async_setup_entry(hass,entry,async_add_entities):
    setup_platform(hass,async_add_entities,{"button"},ElysiumButton)
