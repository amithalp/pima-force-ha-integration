"""Controlled output switches for PIMA Force."""

from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN, OPTYPE_OUTPUT_OFF, OPTYPE_OUTPUT_ON, panel_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up output switches from a config entry."""
    await _async_setup(hass, async_add_entities, entry.runtime_data, entry)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Support legacy platform loading during migration."""
    await _async_setup(hass, async_add_entities, hass.data[DOMAIN]["server"], None)


async def _async_setup(hass, async_add_entities, server, entry):
    outputs = [PimaOutputSwitch(server, number) for number in range(1, 9)]
    bypasses = {}
    async_add_entities(outputs)

    def write_if_enabled(entity):
        """Write state only for entities HA actually loaded from the registry."""
        if entity.hass is not None and getattr(entity, "enabled", True):
            entity.async_write_ha_state()

    def listen(event_type, handler):
        remove = hass.bus.async_listen(event_type, handler)
        if entry is not None:
            entry.async_on_unload(remove)

    async def handle_update(event):
        number = int(event.data["output"])
        if 1 <= number <= len(outputs):
            entity = outputs[number - 1]
            entity._attr_is_on = bool(event.data["is_on"])
            entity._attr_available = True
            write_if_enabled(entity)

    listen("pima_output_update", handle_update)

    def create_bypass(zone):
        entity = PimaZoneBypassSwitch(server, zone)
        bypasses[zone] = entity
        return entity

    if server.installed_zones:
        async_add_entities(
            create_bypass(zone)
            for zone in range(1, server.installed_zones + 1)
            if zone not in bypasses
        )

    async def handle_zones_initialized(event):
        new = [
            create_bypass(zone)
            for zone in range(1, int(event.data.get("count", 0)) + 1)
            if zone not in bypasses
        ]
        if new:
            async_add_entities(new)

    async def handle_zone_update(event):
        zone = int(event.data.get("zone", 0))
        if not zone:
            return
        if zone not in bypasses:
            async_add_entities([create_bypass(zone)])
        entity = bypasses[zone]
        entity._attr_name = f"{event.data.get('name', f'Zone {zone}')} bypass"
        entity._attr_is_on = bool(event.data.get("manual_bypassed", False))
        entity._attr_available = True
        # Disabled-by-default entities do not have a hass object until the
        # user enables them in the entity registry.
        write_if_enabled(entity)

    listen("pima_zones_initialized", handle_zones_initialized)
    listen("pima_zone_update", handle_zone_update)

    def set_available(entities, available):
        for entity in entities:
            entity._attr_available = available
            write_if_enabled(entity)

    async def handle_connected(event):
        # Bypass controls wait for a fresh 2150 response before becoming
        # available; stale security state must not be presented as confirmed.
        set_available(outputs, True)

    async def handle_disconnected(event):
        set_available((*outputs, *bypasses.values()), False)

    listen("pima_connected", handle_connected)
    listen("pima_disconnected", handle_disconnected)


class PimaOutputSwitch(SwitchEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, server, number):
        self.server = server
        self.number = number
        self._attr_device_info = panel_device_info(server.account)
        self._attr_name = f"Output {number}"
        self._attr_unique_id = f"pima_output_{number}"
        self._attr_is_on = server.outputs[number]
        self._attr_available = server.connected

    async def async_turn_on(self, **kwargs):
        await self.server.send_operation(OPTYPE_OUTPUT_ON, partition=0, order=self.number + 33)

    async def async_turn_off(self, **kwargs):
        await self.server.send_operation(OPTYPE_OUTPUT_OFF, partition=0, order=self.number + 33)


class PimaZoneBypassSwitch(SwitchEntity):
    """Safely expose one zone's manual bypass state."""

    _attr_should_poll = False
    # Bypassing a security zone is consequential. Users must explicitly enable
    # the switches they intend to expose to dashboards or external bridges.
    _attr_entity_registry_enabled_default = False

    def __init__(self, server, zone):
        self.server = server
        self.zone = zone
        values = server.zones.get(zone, {})
        self._attr_device_info = panel_device_info(server.account)
        self._attr_name = f"{values.get('name', f'Zone {zone}')} bypass"
        self._attr_unique_id = f"pima_zone_{zone}_bypass"
        self._attr_is_on = bool(values.get("manual_bypassed", False))
        self._attr_available = server.connected and zone in server.zones

    async def async_turn_on(self, **kwargs):
        await self.server.send_zone_bypass(self.zone, True)

    async def async_turn_off(self, **kwargs):
        await self.server.send_zone_bypass(self.zone, False)
