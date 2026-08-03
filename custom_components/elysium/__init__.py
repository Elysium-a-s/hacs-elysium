import json
import logging
from homeassistant.core import HomeAssistant, ServiceCall, Event
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.util import slugify
import voluptuous as vol
from .api import ElysiumApi
from .const import (
    CONF_AGENT_TOKEN,
    CONF_BEHAVIOR_URL,
    CONF_INTEGRATION_URL,
    CONF_REWARD_URL,
    DEFAULT_BEHAVIOR_URL,
    DEFAULT_INTEGRATION_URL,
    DEFAULT_REWARD_URL,
    DOMAIN,
    RULES_STORAGE_KEY,
    HELPERS_STORAGE_KEY,
    STORAGE_VERSION,
)
from .coordinator import ElysiumExecutionCoordinator
from .helper_base import DOMAIN_BY_TYPE

_LOGGER = logging.getLogger(__name__)

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
        record.setdefault("desired_version", 1)
        record.setdefault("integration_version", "0.7.0")

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
        normalized_name = str(payload["name"]).strip().casefold()
        duplicate = next(
            (
                item for current_id, item in helpers.items()
                if current_id != helper_id
                and str(item.get("name", "")).strip().casefold() == normalized_name
            ),
            None,
        )
        if duplicate is not None:
            raise ValueError("A helper with this name already exists")

        desired_version = int(payload.get("desired_version", 1))
        existing = helpers.get(helper_id)
        if existing is not None and int(existing.get("desired_version", 1)) > desired_version:
            return
        record = {
            "helper_id": helper_id,
            "helper_type": helper_type,
            "name": str(payload["name"]).strip(),
            "entity_id": existing.get("entity_id") if existing else f"{domain}.{slugify(object_id)}",
            "config": payload.get("config", {}),
            "state": payload.get("state"),
            "desired_version": desired_version,
            "integration_version": "0.7.0",
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
        desired_version = int(payload.get("desired_version", record.get("desired_version", 1)))
        if desired_version < int(record.get("desired_version", 1)):
            return
        normalized_name = str(payload["name"]).strip().casefold()
        if any(
            current_id != helper_id
            and str(item.get("name", "")).strip().casefold() == normalized_name
            for current_id, item in helpers.items()
        ):
            raise ValueError("A helper with this name already exists")
        old_entity_id = record.get("entity_id")
        record["name"] = str(payload["name"]).strip()
        record["config"] = payload.get("config", {})
        record["desired_version"] = desired_version
        if "state" in payload:
            record["state"] = payload["state"]
        await helper_store.async_save(helpers)
        entity = hass.data[DOMAIN]["entities"].get(helper_id)
        if entity is not None:
            requested = str(call.data.get("entity_id", "")).strip()
            current_entity_id = old_entity_id or entity.entity_id
            if requested and requested != current_entity_id:
                registry = er.async_get(hass)
                registry.async_update_entity(current_entity_id, new_entity_id=requested)
                record["entity_id"] = requested
                entity.entity_id = requested
                await helper_store.async_save(helpers)
            entity.apply_record(record)

    async def replace_helper(call: ServiceCall):
        payload = json.loads(call.data["helper_json"])
        replaced_id = str(call.data["replaced_helper_id"])
        old = helpers.get(replaced_id)
        if old is None:
            raise ValueError("Helper to replace was not found")
        helper_id = str(payload["helper_id"])
        if helper_id == replaced_id:
            raise ValueError("Replacement must have a new helper_id")
        await create_helper(call)
        new_entity = hass.data[DOMAIN]["entities"].get(helper_id)
        if new_entity is None:
            raise ValueError("Replacement entity was not created")
        entity = hass.data[DOMAIN]["entities"].pop(replaced_id, None)
        helpers.pop(replaced_id, None)
        await helper_store.async_save(helpers)
        if entity is not None:
            await entity.async_remove()

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

    async def set_agent_token(call: ServiceCall):
        """Prijme credential, ktorým si hub pýta prácu z backendu (ELYSIUM-58).

        Volá to mobilná appka po spárovaní jednotky, tou istou cestou, akou
        sem posiela pravidlá a helpery. Predtým sa token prepisoval ručne cez
        Configure — najkrehkejší krok onboardingu, po ktorom relock ticho
        nefungoval, ak ho používateľ nedokončil.

        Zapisuje sa do config entry, nie do pamäte: inak by sa po reštarte HA
        stratil a hub by prestal pracovať bez zjavného dôvodu. Zápis spustí
        update listener, ktorý entry znova načíta a rozbehne slučku — bez
        reštartu.
        """
        token = str(call.data["agent_token"]).strip()
        if not token:
            raise ValueError("agent_token must not be empty")

        updates = {**entry.data, CONF_AGENT_TOKEN: token}

        # Adresy sú voliteľné a appka ich posiela preto, aby hub hovoril s tým
        # istým prostredím ako ona. Bez toho by build namierený na staging
        # (ELYSIUM-47) nechal hub pollovať produkciu.
        for field, key in (
            ("integration_base_url", CONF_INTEGRATION_URL),
            ("reward_base_url", CONF_REWARD_URL),
            ("behavior_base_url", CONF_BEHAVIOR_URL),
        ):
            value = str(call.data.get(field, "")).strip()
            if value:
                updates[key] = value

        hass.config_entries.async_update_entry(entry, data=updates)

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
    hass.services.async_register(DOMAIN, "replace_helper", replace_helper, schema=vol.Schema({
        vol.Required("helper_json"): cv.string,
        vol.Required("replaced_helper_id"): cv.string,
        vol.Optional("entity_id"): cv.string,
    }))
    hass.services.async_register(DOMAIN, "delete_helper", delete_helper, schema=vol.Schema({vol.Required("helper_id"): cv.string, vol.Optional("entity_id"): cv.string}))
    hass.services.async_register(DOMAIN, "set_agent_token", set_agent_token, schema=vol.Schema({
        vol.Required("agent_token"): cv.string,
        vol.Optional("integration_base_url"): cv.string,
        vol.Optional("reward_base_url"): cv.string,
        vol.Optional("behavior_base_url"): cv.string,
        vol.Optional("entity_id"): cv.string,
    }))
    hass.services.async_register(DOMAIN, "set_helper", set_helper, schema=vol.Schema({vol.Required("helper_id"): cv.string, vol.Required("state"): cv.string, vol.Optional("entity_id"): cv.string}))
    entry.async_on_unload(hass.bus.async_listen("state_changed", state_changed))
    # Registruje sa nepodmienene. Keď visel až za kontrolou tokenu, hub bez
    # tokenu ho nikdy nedostal — a práve ten je príjemcom set_agent_token,
    # takže by sa slučka rozbehla až po reštarte HA.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await _async_start_execution(hass, entry)
    return True


async def _async_start_execution(hass: HomeAssistant, entry) -> None:
    """Spustí vykonávaciu slučku, ak má jednotka agent token (ELYSIUM-42).

    Bez tokenu komponent funguje ako doteraz — prijíma pravidlá a helpery —
    len nevykonáva relock ani čakajúce akcie. Inštalácie spárované pred
    ELYSIUM-42 sú presne v tomto stave, kým im appka token nedoplní.
    """
    config = {**entry.data, **entry.options}
    agent_token = (config.get(CONF_AGENT_TOKEN) or "").strip()
    if not agent_token:
        # WARNING, nie INFO. Toto je jediná stopa po hube, ktorý nič nevykonáva
        # — odmeny sa nezamykajú, čakajúce akcie sa nespúšťajú — a na INFO ju
        # HA v predvolenom nastavení nezobrazí. Presne takto vyzeralo 2. 8.
        # zvonku: session dobehla, zariadenie ostalo odomknuté a nikde ani
        # riadok o tom, prečo.
        _LOGGER.warning(
            "Elysium: this hub has no agent token, so nothing is being "
            "executed — rewards will not lock themselves and pending actions "
            "will not run. Finish pairing from the mobile app "
            "(Settings > Hub Token). If pairing reports an error, the backend "
            "could not reach this hub."
        )
        return

    api = ElysiumApi(
        session=async_get_clientsession(hass),
        integration_base_url=config.get(CONF_INTEGRATION_URL) or DEFAULT_INTEGRATION_URL,
        reward_base_url=config.get(CONF_REWARD_URL) or DEFAULT_REWARD_URL,
        behavior_base_url=config.get(CONF_BEHAVIOR_URL) or DEFAULT_BEHAVIOR_URL,
        agent_token=agent_token,
    )
    coordinator = ElysiumExecutionCoordinator(hass, api)
    hass.data[DOMAIN]["coordinator"] = coordinator

    # Zámerne async_refresh a nie async_config_entry_first_refresh: tá druhá
    # pri zlyhaní zdvihne ConfigEntryNotReady a zhodí celý setup. Keď je
    # backend dole, komponent musí ďalej obsluhovať pravidlá a helpery
    # lokálne — to je práve to, čo na Home Assistante funguje bez internetu.
    await coordinator.async_refresh()


async def _async_reload_entry(hass: HomeAssistant, entry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False
    for service in ("upsert_rule", "remove_rule", "create_helper", "update_helper", "replace_helper", "delete_helper", "set_helper", "set_agent_token"):
        hass.services.async_remove(DOMAIN, service)
    hass.data.pop(DOMAIN, None)
    return True
