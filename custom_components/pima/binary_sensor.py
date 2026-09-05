import logging

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers import entity_registry as er
from .const import DOMAIN, panel_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up binary sensors from a config entry."""
    await _async_setup(hass, async_add_entities, entry.runtime_data, entry)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Support legacy platform loading during migration."""
    await _async_setup(hass, async_add_entities, hass.data[DOMAIN]["server"], None)


async def _async_setup(hass, async_add_entities, server, entry):
    _LOGGER.debug("PIMA binary_sensor platform loaded")
    entities = {}  # zone_num -> PimaZoneBinarySensor
    trouble = PimaPanelTroubleBinarySensor(server)
    connectivity = PimaPanelConnectivityBinarySensor(server)
    async_add_entities([trouble, connectivity])

    def listen(event_type, handler):
        remove = hass.bus.async_listen(event_type, handler)
        if entry is not None:
            entry.async_on_unload(remove)

    def _create_sensor(zone_num):
        sensor = PimaZoneBinarySensor(server, zone_num)
        entities[zone_num] = sensor
        return sensor

    # If zones are already known (e.g. panel was connected before platform loaded)
    if server.zones:
        new = [_create_sensor(z) for z in server.zones if z not in entities]
        if new:
            async_add_entities(new)
            _LOGGER.info("PIMA: registered %s zones at platform load", len(new))

    # pima_zones_initialized: panel told us how many zones exist.
    # Create all entities immediately as unavailable — they become available on first update.
    async def handle_zones_initialized(event):
        count = event.data.get("count", 0)
        _LOGGER.info("PIMA zones initialized: count=%s", count)
        new = []
        for zone_num in range(1, count + 1):
            if zone_num not in entities:
                new.append(_create_sensor(zone_num))
        if new:
            async_add_entities(new)
            _LOGGER.info("PIMA: created %s zone entities", len(new))

    listen("pima_zones_initialized", handle_zones_initialized)

    # pima_zone_names_updated: all zone names have been fetched from the panel.
    # Update both the entity's _attr_name AND the HA entity registry so the
    # display name persists correctly across restarts.
    async def handle_zone_names_updated(event):
        registry = er.async_get(hass)
        for zone_num, sensor in entities.items():
            name = server.zones.get(zone_num, {}).get("name", f"PIMA Zone {zone_num}")
            previous_name = sensor._attr_name
            sensor._attr_name = name
            # Registry entry.name is a user override. Older integration
            # versions populated it with the previous panel name; migrate that
            # legacy value, but never replace a genuine HA customization.
            entry = registry.async_get(sensor.entity_id)
            if entry and entry.name not in (None, name):
                if entry.name == previous_name or entry.name.startswith("PIMA Zone"):
                    registry.async_update_entity(sensor.entity_id, name=name)
                    _LOGGER.debug("Updated registry name for zone %s", zone_num)
            sensor.async_write_ha_state()

    listen("pima_zone_names_updated", handle_zone_names_updated)

    # pima_zone_update: state/attribute update arrives from panel
    async def handle_zone_update(event):
        zone = event.data.get("zone")
        if zone is None:
            return

        # Late-create if we somehow missed initialization
        if zone not in entities:
            _LOGGER.warning("PIMA: late-creating entity for zone %s", zone)
            async_add_entities([_create_sensor(zone)])

        sensor = entities[zone]
        sensor._attr_name = event.data.get("name", f"PIMA Zone {zone}")
        sensor._attr_is_on = event.data.get("open", False)
        sensor._attr_available = True
        sensor._attr_extra_state_attributes = _build_attrs(event.data)
        sensor.async_write_ha_state()

    listen("pima_zone_update", handle_zone_update)

    async def handle_faults_updated(event):
        trouble._attr_is_on = bool(event.data.get("problem"))
        trouble._attr_available = True
        trouble._attr_extra_state_attributes = {
            "fault_count": event.data.get("fault_count", 0),
            "active_faults": event.data.get("active_faults", []),
            "fault_details": event.data.get("fault_details", []),
        }
        trouble.async_write_ha_state()

    listen("pima_faults_updated", handle_faults_updated)

    # Mark all unavailable on disconnect, available on reconnect
    async def handle_disconnected(event):
        _LOGGER.info("PIMA: panel disconnected — marking zones unavailable")
        for sensor in entities.values():
            sensor._attr_available = False
            sensor.async_write_ha_state()
        trouble._attr_available = False
        trouble.async_write_ha_state()
        connectivity._attr_is_on = False
        connectivity.async_write_ha_state()

    listen("pima_disconnected", handle_disconnected)

    async def handle_connected(event):
        _LOGGER.info("PIMA: panel reconnected — waiting for fresh zone status")
        connectivity._attr_is_on = True
        connectivity.async_write_ha_state()

    listen("pima_connected", handle_connected)


def _build_attrs(data):
    return {
        "zone": data.get("zone"),
        "manual_bypassed": data.get("manual_bypassed", False),
        "auto_bypassed": data.get("auto_bypassed", False),
        "alarmed": data.get("alarmed", False),
        "armed": data.get("armed", False),
        "supervision_loss": data.get("supervision_loss", False),
        "low_battery": data.get("low_battery", False),
        "short": data.get("short", False),
        "cut_tamper": data.get("cut_tamper", False),
        "soak": data.get("soak", False),
        "chime": data.get("chime", False),
        "anti_mask": data.get("anti_mask", False),
        "duress": data.get("duress", False),
        "fire": data.get("fire", False),
        "medical": data.get("medical", False),
        "panic": data.get("panic", False),
        "last_event": data.get("last_event"),
    }


class PimaZoneBinarySensor(BinarySensorEntity):
    """A PIMA zone with a generic opening classification by default.

    The Force JSON protocol does not expose the physical detector type. Home
    Assistant users can override this default per entity with the "Shown as"
    setting without changing the stable unique ID.
    """

    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.OPENING

    def __init__(self, server, zone_num):
        self.server = server
        self.zone = zone_num
        self._attr_device_info = panel_device_info(server.account)
        self._attr_name = server.zones.get(zone_num, {}).get("name", f"PIMA Zone {zone_num}")
        self._attr_unique_id = f"pima_zone_{zone_num}"
        self._attr_is_on = server.zones.get(zone_num, {}).get("open", False)
        self._attr_available = False  # unavailable until first real update arrives
        self._attr_extra_state_attributes = {"zone": zone_num}


class PimaPanelTroubleBinarySensor(BinarySensorEntity):
    """True when the panel reports one or more active faults."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_unique_id = "pima_panel_trouble"
    _attr_translation_key = "panel_trouble"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, server):
        self.server = server
        self._attr_device_info = panel_device_info(server.account)
        self._attr_is_on = bool(server.faults)
        self._attr_available = server.connected and server.faults_initialized
        self._attr_extra_state_attributes = {
            "fault_count": len(server.faults),
            "active_faults": [fault["label"] for fault in server.faults],
            "fault_details": list(server.faults),
        }


class PimaPanelConnectivityBinarySensor(BinarySensorEntity):
    """Show whether the PIMA panel currently has an active TCP connection."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_unique_id = "pima_panel_connected"
    _attr_translation_key = "panel_connection"
    _attr_available = True

    def __init__(self, server):
        self.server = server
        self._attr_device_info = panel_device_info(server.account)
        self._attr_is_on = server.connected
