"""PIMA-specific arming buttons.

Home Assistant's alarm-control-panel model represents Away, Home and Night.
PIMA also provides Home 3, Home 4 and Shabbat modes. Exposing each extended
mode as a ButtonEntity keeps those commands available to dashboards and
automations without inventing non-standard alarm states.
"""

from homeassistant.components.button import ButtonEntity

from .const import ARMING_SERVICES, DOMAIN, panel_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up extended arming buttons from a config entry."""
    await _async_setup(hass, async_add_entities, entry.runtime_data, entry)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Support legacy platform loading during migration."""
    await _async_setup(hass, async_add_entities, hass.data[DOMAIN]["server"], None)


async def _async_setup(hass, async_add_entities, server, entry):
    entities = {}

    def create_partition(partition):
        new = []
        for mode, operation in ARMING_SERVICES.items():
            key = (partition, mode)
            if key not in entities:
                entity = PimaArmingButton(server, mode, operation, partition)
                entities[key] = entity
                new.append(entity)
        return new

    partitions = server.existing_partitions or {1}
    async_add_entities(
        entity
        for partition in sorted(partitions)
        for entity in create_partition(partition)
    )

    async def handle_partitions_updated(event):
        new = []
        for partition in sorted(
            int(value) for value in event.data.get("partitions", [])
        ):
            new.extend(create_partition(partition))
        if new:
            async_add_entities(new)

    remove = hass.bus.async_listen(
        "pima_partitions_updated", handle_partitions_updated
    )
    if entry is not None:
        entry.async_on_unload(remove)


class PimaArmingButton(ButtonEntity):
    """Run one PIMA extended arming command for partition 1."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    def __init__(self, server, mode, operation, partition=1):
        self.server = server
        self.mode = mode
        self.operation = operation
        self.partition = partition
        self._attr_device_info = panel_device_info(server.account)
        suffix = "" if partition == 1 else f"_partition_{partition}"
        self._attr_unique_id = f"pima_{mode}{suffix}"
        if partition == 1:
            self._attr_translation_key = mode
        else:
            label = mode.removeprefix("arm_").replace("_", " ").title()
            self._attr_name = f"Arm {label} - Partition {partition}"
        self._attr_available = server.connected

    async def async_added_to_hass(self):
        """Track panel connectivity."""
        await super().async_added_to_hass()

        async def handle_connected(event):
            self._attr_available = True
            self.async_write_ha_state()

        async def handle_disconnected(event):
            self._attr_available = False
            self.async_write_ha_state()

        self.async_on_remove(
            self.hass.bus.async_listen("pima_connected", handle_connected)
        )
        self.async_on_remove(
            self.hass.bus.async_listen("pima_disconnected", handle_disconnected)
        )

    async def async_press(self):
        """Arm this partition using the selected PIMA mode."""
        await self.server.send_operation(self.operation, partition=self.partition)
