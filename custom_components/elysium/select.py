from homeassistant.components.select import SelectEntity
from .helper_base import ElysiumHelperMixin, setup_platform

class ElysiumSelect(ElysiumHelperMixin, SelectEntity):
    def __init__(self, hass, record, store):
        self.initialize(hass, record, store)
        self.write_record_state()

    def write_record_state(self):
        raw = self._record.get("config", {}).get("options", ["Option 1"])
        if isinstance(raw, str):
            options = [item.strip() for item in raw.split(",") if item.strip()]
        else:
            options = [str(item) for item in raw]
        self._attr_options = options or ["Option 1"]
        current = str(self._record.get("state") or self._attr_options[0])
        self._attr_current_option = current if current in self._attr_options else self._attr_options[0]
        self._attr_icon = "mdi:form-dropdown"

    async def async_select_option(self, option):
        if option not in self._attr_options:
            raise ValueError("Unknown option")
        self._record["state"] = option
        self.write_record_state()
        await self.persist()
        self.async_write_ha_state()

async def async_setup_entry(hass, entry, async_add_entities):
    setup_platform(hass, async_add_entities, {"select"}, ElysiumSelect)
