"""Disabled-by-default siren controls for PIMA Force."""

from homeassistant.components.siren import SirenEntity, SirenEntityFeature

from .const import DOMAIN, OPTYPE_OUTPUT_OFF, OPTYPE_OUTPUT_ON, panel_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sirens from a config entry."""
    await _async_setup(hass, async_add_entities, entry.runtime_data, entry)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Support legacy platform loading during migration."""
    await _async_setup(hass, async_add_entities, hass.data[DOMAIN]["server"], None)


async def _async_setup(hass, async_add_entities, server, entry):
    entities = [PimaSiren(server, number) for number in range(1, 3)]
    async_add_entities(entities)

    def listen(event_type, handler):
        remove = hass.bus.async_listen(event_type, handler)
        if entry is not None:
            entry.async_on_unload(remove)

    async def handle_update(event):
        number = int(event.data["siren"])
        if 1 <= number <= len(entities):
            entity = entities[number - 1]
            entity._attr_is_on = bool(event.data["is_on"])
            entity._attr_available = True
            if entity.hass is not None:
                entity.async_write_ha_state()

    listen("pima_siren_update", handle_update)

    def set_available(available):
        for entity in entities:
            entity._attr_available = available
            if entity.hass is not None:
                entity.async_write_ha_state()

    async def handle_connected(event):
        set_available(True)

    async def handle_disconnected(event):
        set_available(False)

    listen("pima_connected", handle_connected)
    listen("pima_disconnected", handle_disconnected)


class PimaSiren(SirenEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = False
    _attr_supported_features = SirenEntityFeature.TURN_ON | SirenEntityFeature.TURN_OFF

    def __init__(self, server, number):
        self.server = server
        self.number = number
        self._attr_device_info = panel_device_info(server.account)
        label = "External" if number == 1 else "Internal"
        self._attr_name = f"{label} siren"
        self._attr_unique_id = f"pima_siren_{number}"
        self._attr_is_on = server.sirens[number]
        self._attr_available = server.connected

    async def async_turn_on(self, **kwargs):
        await self.server.send_operation(OPTYPE_OUTPUT_ON, partition=0, order=self.number)

    async def async_turn_off(self, **kwargs):
        await self.server.send_operation(OPTYPE_OUTPUT_OFF, partition=0, order=self.number)
