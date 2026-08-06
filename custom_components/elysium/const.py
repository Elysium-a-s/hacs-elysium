DOMAIN = "elysium"
RULES_STORAGE_KEY = "elysium.rules"
HELPERS_STORAGE_KEY = "elysium.helpers"
STORAGE_VERSION = 1

# Konfigurácia vykonávacej slučky (ELYSIUM-42).
CONF_AGENT_TOKEN = "agent_token"
# ELYSIUM-108: čo používateľ naozaj zadá. Token sa zaň vymení a do config
# entry sa uloží už len token — kód je jednorazový a po použití bezcenný.
CONF_PAIRING_CODE = "pairing_code"
CONF_INTEGRATION_URL = "integration_base_url"
CONF_REWARD_URL = "reward_base_url"
CONF_BEHAVIOR_URL = "behavior_base_url"
# 0 znamená adaptívny interval riadený backendom. Kladná hodnota je vedomý
# manuálny override z Options Flow a používa sa pre každý poll.
CONF_POLL_INTERVAL_SECONDS = "poll_interval_seconds"
DEFAULT_POLL_INTERVAL_SECONDS = 0
MIN_POLL_INTERVAL_SECONDS = 30
MAX_POLL_INTERVAL_SECONDS = 3600

# Produkčné Render adresy. Sú to len predvyplnené hodnoty vo formulári —
# skutočné adresy sa čítajú z config entry, aby sa dal komponent nasmerovať
# na staging bez úpravy kódu.
DEFAULT_INTEGRATION_URL = "https://integration-service-l7fn.onrender.com"
DEFAULT_REWARD_URL = "https://reward-service-f71p.onrender.com"
DEFAULT_BEHAVIOR_URL = "https://behavior-engine.onrender.com"
