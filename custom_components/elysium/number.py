from decimal import Decimal
from homeassistant.components.number import NumberEntity
from .helper_base import ElysiumHelperMixin, setup_platform

class ElysiumNumber(ElysiumHelperMixin, NumberEntity):
    def __init__(self,hass,record,store):
        self.initialize(hass,record,store);self.write_record_state()
    def write_record_state(self):
        c=self._record.get("config",{})
        self._attr_native_min_value=float(c.get("min",0))
        self._attr_native_max_value=float(c.get("max",100000))
        self._attr_native_step=float(c.get("step",1))
        self._attr_native_value=float(self._record.get("state",c.get("initial",0)))
        self._attr_icon="mdi:counter" if self._record["helper_type"]=="counter" else "mdi:numeric"
    async def async_set_native_value(self,value:float):
        self._record["state"]=float(value);self.write_record_state();await self.persist();self.async_write_ha_state()

async def async_setup_entry(hass,entry,async_add_entities):
    setup_platform(hass,async_add_entities,{"number","counter"},ElysiumNumber)
