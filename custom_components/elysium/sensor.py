from homeassistant.components.sensor import SensorEntity
from .helper_base import ElysiumHelperMixin, setup_platform

class ElysiumSensor(ElysiumHelperMixin, SensorEntity):
    def __init__(self,hass,record,store):
        self.initialize(hass,record,store);self.write_record_state()
    def write_record_state(self):
        helper_type=self._record["helper_type"];config=self._record.get("config",{})
        defaults={"timer":config.get("duration_seconds",0),"schedule":config.get("schedule","inactive"),"sensor":config.get("initial","unknown")}
        self._attr_native_value=self._record.get("state",defaults[helper_type])
        self._attr_native_unit_of_measurement="s" if helper_type=="timer" else config.get("unit")
        self._attr_icon={"timer":"mdi:timer-outline","schedule":"mdi:calendar-clock","sensor":"mdi:gauge"}[helper_type]

async def async_setup_entry(hass,entry,async_add_entities):
    setup_platform(hass,async_add_entities,{"timer","schedule","sensor"},ElysiumSensor)
