import json
from homeassistant.core import HomeAssistant, ServiceCall, Event
from homeassistant.helpers.storage import Store
from homeassistant.helpers import config_validation as cv
import voluptuous as vol
from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION

async def async_setup_entry(hass: HomeAssistant, entry):
    store=Store(hass,STORAGE_VERSION,STORAGE_KEY)
    rules=await store.async_load() or {}
    hass.data.setdefault(DOMAIN,{})["rules"]=rules
    hass.data[DOMAIN]["store"]=store

    async def upsert(call:ServiceCall):
        rule=json.loads(call.data["rule_json"])
        rule_id=str(rule["automation_rule_id"])
        rules[rule_id]=rule
        await store.async_save(rules)

    async def remove(call:ServiceCall):
        rules.pop(str(call.data["rule_id"]),None)
        await store.async_save(rules)

    async def set_helper(call:ServiceCall):
        entity_id=str(call.data["entity_id"])
        if not entity_id.startswith("elysium."):
            entity_id=f"elysium.{entity_id.split('.')[-1]}"
        hass.states.async_set(entity_id,call.data["state"],{"friendly_name":entity_id.split(".")[-1].replace("_"," ").title()})

    async def state_changed(event:Event):
        new=event.data.get("new_state")
        if new is None:return
        for rule in list(rules.values()):
            if not rule.get("is_active",True) or rule.get("target_entity_id")!=new.entity_id:continue
            attribute=rule.get("target_attribute","state")
            actual=new.state if attribute=="state" else new.attributes.get(attribute)
            if str(actual)!=str(rule.get("target_value")):continue
            condition=rule.get("condition_type","always")
            if condition=="helper_state":
                helper=rule.get("condition",{})
                state=hass.states.get(helper.get("entity_id",""))
                if state is None or str(state.state)!=str(helper.get("value")):continue
            await hass.services.async_call(
                rule["action_domain"],rule["action_service"],
                {"entity_id":rule["action_entity_id"],**rule.get("action_data",{})},
                blocking=False,
            )

    hass.services.async_register(DOMAIN,"upsert_rule",upsert,schema=vol.Schema({vol.Required("rule_json"):cv.string}))
    hass.services.async_register(DOMAIN,"remove_rule",remove,schema=vol.Schema({vol.Required("rule_id"):cv.string}))
    hass.services.async_register(DOMAIN,"set_helper",set_helper,schema=vol.Schema({vol.Required("entity_id"):cv.string,vol.Required("state"):cv.string}))
    entry.async_on_unload(hass.bus.async_listen("state_changed",state_changed))
    return True

async def async_unload_entry(hass:HomeAssistant,entry):
    for service in ("upsert_rule","remove_rule","set_helper"):
        hass.services.async_remove(DOMAIN,service)
    hass.data.pop(DOMAIN,None)
    return True
