import json
from homeassistant.core import HomeAssistant, ServiceCall, Event
from homeassistant.helpers.storage import Store
from homeassistant.helpers import config_validation as cv
from homeassistant.util import slugify
import voluptuous as vol
from .const import DOMAIN, RULES_STORAGE_KEY, HELPERS_STORAGE_KEY, STORAGE_VERSION
from .helper_base import DOMAIN_BY_TYPE

PLATFORMS = ["switch", "number", "select", "text", "button", "sensor"]

async def async_setup_entry(hass: HomeAssistant, entry):
    rule_store = Store(hass, STORAGE_VERSION, RULES_STORAGE_KEY)
    helper_store = Store(hass, STORAGE_VERSION, HELPERS_STORAGE_KEY)
    rules = await rule_store.async_load() or {}
    helpers = await helper_store.async_load() or {}

    for helper_id, record in helpers.items():
        record.setdefault("helper_id", helper_id)
        record.setdefault("helper_type", "toggle")
        if "is_on" in record and "state" not in record:
            record["state"] = bool(record.pop("is_on"))
        record.setdefault("config", {})

    hass.data[DOMAIN] = {
        "rules": rules,
        "rule_store": rule_store,
        "helpers": helpers,
        "helper_store": helper_store,
        "entities": {},
        "add_helper": {},
    }
    await helper_store.async_save(helpers)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def upsert(call: ServiceCall):
        rule = json.loads(call.data["rule_json"])
        rules[str(rule["automation_rule_id"])] = rule
        await rule_store.async_save(rules)

    async def remove(call: ServiceCall):
        rules.pop(str(call.data["rule_id"]), None)
        await rule_store.async_save(rules)

    async def create_helper(call: ServiceCall):
        payload = json.loads(call.data["helper_json"])
        helper_id = str(payload["helper_id"])
        helper_type = str(payload["helper_type"])
        if helper_type not in DOMAIN_BY_TYPE:
            raise ValueError(f"Unsupported helper type: {helper_type}")
        domain = DOMAIN_BY_TYPE[helper_type]
        requested = str(call.data.get("entity_id", ""))
        object_id = requested.split(".")[-1] if requested else f"elysium_{slugify(payload['name'])}"
        if not object_id.startswith("elysium_"):
            object_id = f"elysium_{object_id}"
        record = {
            "helper_id": helper_id,
            "helper_type": helper_type,
            "name": str(payload["name"]),
            "entity_id": f"{domain}.{slugify(object_id)}",
            "config": payload.get("config", {}),
            "state": payload.get("state"),
        }
        helpers[helper_id] = record
        await helper_store.async_save(helpers)
        callback = hass.data[DOMAIN]["add_helper"].get(helper_type)
        if callback is None:
            raise ValueError(f"Platform for {helper_type} is unavailable")
        entity = callback(record)
        entity.apply_record(record)
        await hass.async_block_till_done()

    async def update_helper(call: ServiceCall):
        payload = json.loads(call.data["helper_json"])
        helper_id = str(payload["helper_id"])
        record = helpers.get(helper_id)
        if record is None:
            raise ValueError("Helper not found")
        record["name"] = str(payload["name"])
        record["config"] = payload.get("config", {})
        if "state" in payload:
            record["state"] = payload["state"]
        await helper_store.async_save(helpers)
        entity = hass.data[DOMAIN]["entities"].get(helper_id)
        if entity is not None:
            entity.apply_record(record)

    async def delete_helper(call: ServiceCall):
        helper_id = str(call.data["helper_id"])
        entity = hass.data[DOMAIN]["entities"].pop(helper_id, None)
        helpers.pop(helper_id, None)
        await helper_store.async_save(helpers)
        if entity is not None:
            await entity.async_remove()

    async def set_helper(call: ServiceCall):
        helper_id = str(call.data["helper_id"])
        entity = hass.data[DOMAIN]["entities"].get(helper_id)
        record = helpers.get(helper_id)
        if entity is None or record is None:
            raise ValueError("Helper not found")
        raw = call.data["state"]
        helper_type = record["helper_type"]
        if helper_type == "toggle":
            record["state"] = str(raw).lower() in ("on", "true", "1")
        elif helper_type in ("number", "counter", "timer"):
            record["state"] = float(raw)
        else:
            record["state"] = str(raw)
        await helper_store.async_save(helpers)
        entity.apply_record(record)

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
                condition_data = rule.get("condition", {})
                helper_state = hass.states.get(condition_data.get("entity_id", ""))
                if helper_state is None or str(helper_state.state) != str(condition_data.get("value")):
                    continue
            await hass.services.async_call(
                rule["action_domain"], rule["action_service"],
                {"entity_id": rule["action_entity_id"], **rule.get("action_data", {})},
                blocking=False,
            )

    hass.services.async_register(DOMAIN, "upsert_rule", upsert, schema=vol.Schema({vol.Required("rule_json"): cv.string, vol.Optional("entity_id"): cv.string}))
    hass.services.async_register(DOMAIN, "remove_rule", remove, schema=vol.Schema({vol.Required("rule_id"): cv.string, vol.Optional("entity_id"): cv.string}))
    hass.services.async_register(DOMAIN, "create_helper", create_helper, schema=vol.Schema({vol.Required("helper_json"): cv.string, vol.Optional("entity_id"): cv.string}))
    hass.services.async_register(DOMAIN, "update_helper", update_helper, schema=vol.Schema({vol.Required("helper_json"): cv.string, vol.Optional("entity_id"): cv.string}))
    hass.services.async_register(DOMAIN, "delete_helper", delete_helper, schema=vol.Schema({vol.Required("helper_id"): cv.string, vol.Optional("entity_id"): cv.string}))
    hass.services.async_register(DOMAIN, "set_helper", set_helper, schema=vol.Schema({vol.Required("helper_id"): cv.string, vol.Required("state"): cv.string, vol.Optional("entity_id"): cv.string}))
    entry.async_on_unload(hass.bus.async_listen("state_changed", state_changed))
    return True

async def async_unload_entry(hass: HomeAssistant, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False
    for service in ("upsert_rule", "remove_rule", "create_helper", "update_helper", "delete_helper", "set_helper"):
        hass.services.async_remove(DOMAIN, service)
    hass.data.pop(DOMAIN, None)
    return True
