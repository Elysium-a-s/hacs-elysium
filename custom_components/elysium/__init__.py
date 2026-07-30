import json
from homeassistant.core import HomeAssistant, ServiceCall, Event
from homeassistant.helpers.storage import Store
from homeassistant.helpers import config_validation as cv
from homeassistant.util import slugify
import voluptuous as vol
from .const import DOMAIN, RULES_STORAGE_KEY, HELPERS_STORAGE_KEY, STORAGE_VERSION

PLATFORMS = ["switch"]

async def async_setup_entry(hass: HomeAssistant, entry):
    rule_store = Store(hass, STORAGE_VERSION, RULES_STORAGE_KEY)
    helper_store = Store(hass, STORAGE_VERSION, HELPERS_STORAGE_KEY)
    rules = await rule_store.async_load() or {}
    helpers = await helper_store.async_load() or {}

    hass.data[DOMAIN] = {
        "rules": rules,
        "rule_store": rule_store,
        "helpers": helpers,
        "helper_store": helper_store,
        "entities": {},
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def upsert(call: ServiceCall):
        rule = json.loads(call.data["rule_json"])
        rule_id = str(rule["automation_rule_id"])
        rules[rule_id] = rule
        await rule_store.async_save(rules)

    async def remove(call: ServiceCall):
        rules.pop(str(call.data["rule_id"]), None)
        await rule_store.async_save(rules)

    async def create_helper(call: ServiceCall):
        helper_id = str(call.data["helper_id"])
        requested = str(call.data.get("entity_id", ""))
        object_id = requested.split(".")[-1] if requested else f"elysium_{slugify(call.data['name'])}"
        if not object_id.startswith("elysium_"):
            object_id = f"elysium_{object_id}"
        entity_id = f"switch.{slugify(object_id)}"

        record = {
            "helper_id": helper_id,
            "name": str(call.data["name"]),
            "entity_id": entity_id,
            "is_on": str(call.data.get("initial_state", "off")).lower() == "on",
        }
        is_new = helper_id not in helpers
        helpers[helper_id] = record
        await helper_store.async_save(helpers)

        entity = hass.data[DOMAIN]["entities"].get(helper_id)
        if is_new or entity is None:
            hass.data[DOMAIN]["add_toggle_helper"](record)
        else:
            entity._record.update(record)
            entity._attr_name = record["name"]
            entity._attr_is_on = record["is_on"]
            entity.async_write_ha_state()

    async def set_helper(call: ServiceCall):
        requested = str(call.data["entity_id"])
        state = str(call.data["state"]).lower()
        entity = next(
            (item for item in hass.data[DOMAIN]["entities"].values() if item.entity_id == requested),
            None,
        )
        if entity is None:
            return
        if state == "on":
            await entity.async_turn_on()
        else:
            await entity.async_turn_off()

    async def state_changed(event: Event):
        new = event.data.get("new_state")
        if new is None:
            return
        for rule in list(rules.values()):
            if not rule.get("is_active", True) or rule.get("target_entity_id") != new.entity_id:
                continue
            attribute = rule.get("target_attribute", "state")
            actual = new.state if attribute == "state" else new.attributes.get(attribute)
            if str(actual) != str(rule.get("target_value")):
                continue
            condition = rule.get("condition_type", "always")
            if condition == "helper_state":
                helper = rule.get("condition", {})
                helper_state = hass.states.get(helper.get("entity_id", ""))
                if helper_state is None or str(helper_state.state) != str(helper.get("value")):
                    continue
            await hass.services.async_call(
                rule["action_domain"],
                rule["action_service"],
                {"entity_id": rule["action_entity_id"], **rule.get("action_data", {})},
                blocking=False,
            )

    hass.services.async_register(
        DOMAIN,
        "upsert_rule",
        upsert,
        schema=vol.Schema({
            vol.Required("rule_json"): cv.string,
            vol.Optional("entity_id"): cv.string,
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "remove_rule",
        remove,
        schema=vol.Schema({
            vol.Required("rule_id"): cv.string,
            vol.Optional("entity_id"): cv.string,
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "create_helper",
        create_helper,
        schema=vol.Schema({
            vol.Required("helper_id"): cv.string,
            vol.Required("name"): cv.string,
            vol.Optional("entity_id"): cv.string,
            vol.Optional("initial_state", default="off"): vol.In(("on", "off")),
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "set_helper",
        set_helper,
        schema=vol.Schema({
            vol.Required("entity_id"): cv.string,
            vol.Required("state"): vol.In(("on", "off")),
        }),
    )
    entry.async_on_unload(hass.bus.async_listen("state_changed", state_changed))
    return True


async def async_unload_entry(hass: HomeAssistant, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False
    for service in ("upsert_rule", "remove_rule", "create_helper", "set_helper"):
        hass.services.async_remove(DOMAIN, service)
    hass.data.pop(DOMAIN, None)
    return True
