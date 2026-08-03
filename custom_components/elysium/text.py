from homeassistant.components.text import TextEntity, TextMode
from .helper_base import ElysiumHelperMixin, setup_platform

class ElysiumText(ElysiumHelperMixin, TextEntity):
    _attr_mode=TextMode.TEXT
    def __init__(self,hass,record,store):
        self.initialize(hass,record,store);self.write_record_state()
    def write_record_state(self):
        c=self._record.get("config",{})
        self._attr_native_min=int(c.get("min_length",0));self._attr_native_max=int(c.get("max_length",255))
        self._attr_native_value=str(self._record.get("state",c.get("initial","")))
        self._attr_icon="mdi:form-textbox"
    async def async_set_value(self,value):
        self._record["state"]=value;self.write_record_state();await self.persist();self.async_write_ha_state()

async def async_setup_entry(hass,entry,async_add_entities):
    setup_platform(hass,async_add_entities,{"text"},ElysiumText)
