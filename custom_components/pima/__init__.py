"""PIMA Force integration."""

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import ConfigEntryNotReady

from .const import ARMING_SERVICES, DEFAULT_PORT, DOMAIN
from .server import PimaServer

_LOGGER = logging.getLogger(__name__)

CONF_ACCOUNT = "account"
PLATFORMS = [
    "alarm_control_panel",
    "binary_sensor",
    "button",
    "sensor",
    "siren",
    "switch",
]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_ACCOUNT): cv.positive_int,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Import legacy YAML configuration into a config entry."""
    hass.data.setdefault(DOMAIN, {})
    if yaml_config := config.get(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=dict(yaml_config),
            )
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PIMA Force from a config entry."""
    server = PimaServer(
        hass,
        account=entry.data[CONF_ACCOUNT],
        password=entry.data[CONF_PASSWORD],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
    )
    try:
        await server.start()
    except OSError as err:
        raise ConfigEntryNotReady(
            f"Unable to listen on TCP port {server.port}: {err}"
        ) from err

    entry.runtime_data = server
    hass.data.setdefault(DOMAIN, {})["server"] = server
    _register_services(hass, server)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await server.stop()
        for service in (*ARMING_SERVICES, "bypass_zone", "unbypass_zone", "refresh_faults"):
            hass.services.async_remove(DOMAIN, service)
        hass.data.get(DOMAIN, {}).pop("server", None)
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a PIMA config entry and close its listener."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.stop()
        for service in (*ARMING_SERVICES, "bypass_zone", "unbypass_zone", "refresh_faults"):
            hass.services.async_remove(DOMAIN, service)
        hass.data.get(DOMAIN, {}).pop("server", None)
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after reconfiguration."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant, server: PimaServer) -> None:
    """Register integration services for the active panel."""
    async def handle_arming_service(call):
        await server.send_operation(
            ARMING_SERVICES[call.service], partition=call.data["partition"]
        )

    service_schema = vol.Schema(
        {
            vol.Optional("partition", default=1): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=16)
            )
        }
    )
    for service in ARMING_SERVICES:
        hass.services.async_register(
            DOMAIN, service, handle_arming_service, schema=service_schema
        )

    async def handle_bypass_service(call):
        zone = call.data["zone"]
        bypassed = call.service == "bypass_zone"
        _LOGGER.info(
            "PIMA: %s zone %s requested",
            "bypass" if bypassed else "un-bypass",
            zone,
        )
        await server.send_zone_bypass(zone, bypassed)

    bypass_schema = vol.Schema(
        {vol.Required("zone"): vol.All(vol.Coerce(int), vol.Range(min=1, max=144))}
    )
    for service in ("bypass_zone", "unbypass_zone"):
        hass.services.async_register(
            DOMAIN, service, handle_bypass_service, schema=bypass_schema
        )

    async def handle_refresh_faults(call):
        _LOGGER.info("PIMA: manual fault refresh requested")
        await server.async_refresh_faults()

    hass.services.async_register(DOMAIN, "refresh_faults", handle_refresh_faults)
