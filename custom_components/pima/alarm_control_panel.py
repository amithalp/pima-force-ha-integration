import logging

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from .const import (
    DOMAIN,
    OPTYPE_ARM_AWAY,
    OPTYPE_ARM_HOME1,
    OPTYPE_ARM_HOME2,
    OPTYPE_DISARM,
    panel_device_info,
)

_LOGGER = logging.getLogger(__name__)

# Map server state strings to HA alarm states
STATE_MAP = {
    "disarmed":      AlarmControlPanelState.DISARMED,
    "triggered":     AlarmControlPanelState.TRIGGERED,
    "armed_away":    AlarmControlPanelState.ARMED_AWAY,
    "armed_home_1":  AlarmControlPanelState.ARMED_HOME,
    "armed_home_2":  AlarmControlPanelState.ARMED_NIGHT,
    "armed_home_3":  AlarmControlPanelState.ARMED_HOME,
    "armed_home_4":  AlarmControlPanelState.ARMED_HOME,
    "armed_shabbat": AlarmControlPanelState.ARMED_HOME,
}

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up alarm entities from a config entry."""
    await _async_setup(hass, async_add_entities, entry.runtime_data, entry)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Support legacy platform loading during migration."""
    await _async_setup(hass, async_add_entities, hass.data[DOMAIN]["server"], None)


async def _async_setup(hass, async_add_entities, server, entry):
    _LOGGER.debug("PIMA alarm_control_panel platform loaded")
    entities = {}

    def listen(event_type, handler):
        remove = hass.bus.async_listen(event_type, handler)
        if entry is not None:
            entry.async_on_unload(remove)

    def create_panel(partition):
        panel = PimaAlarmControlPanel(server, partition)
        entities[partition] = panel
        return panel

    if server.existing_partitions:
        async_add_entities(
            [create_panel(partition) for partition in sorted(server.existing_partitions)]
        )

    async def handle_partitions_updated(event):
        existing = {int(partition) for partition in event.data.get("partitions", [])}
        new = []
        for partition in sorted(existing):
            if partition not in entities:
                new.append(create_panel(partition))
        if new:
            async_add_entities(new)
            _LOGGER.info("PIMA: created %s partition alarm entities", len(new))
        for partition, panel in entities.items():
            if partition not in existing:
                panel._attr_available = False
                if panel.hass is not None:
                    panel.async_write_ha_state()

    listen("pima_partitions_updated", handle_partitions_updated)

    async def handle_state(event):
        partition = int(event.data.get("partition", 1))
        if partition not in entities:
            panel = create_panel(partition)
            async_add_entities([panel])
        else:
            panel = entities[partition]
        previous_alarm_state = panel._attr_alarm_state
        previous_available = panel._attr_available
        previous_changed_by = getattr(panel, "_attr_changed_by", None)
        panel._attr_alarm_state = STATE_MAP.get(event.data.get("state"), AlarmControlPanelState.DISARMED)
        previous = dict(panel.extra_state_attributes or {})
        panel._attr_extra_state_attributes = {
            key: event.data[key]
            for key in (
                "partition", "zone", "alarm_type", "user", "user_name",
                "last_triggered_zone", "last_triggered_partition",
                "last_triggered_user", "last_triggered_user_name",
                "last_triggered_at",
            )
            if key in event.data
        }
        for key in (
            "user", "user_name", "last_triggered_zone",
            "last_triggered_partition", "last_triggered_user",
            "last_triggered_user_name", "last_triggered_at",
        ):
            if key in previous:
                panel._attr_extra_state_attributes.setdefault(key, previous[key])
        panel._attr_extra_state_attributes["pima_mode"] = event.data.get("state")
        panel._attr_extra_state_attributes["partition"] = partition
        if "user" in event.data:
            panel._attr_changed_by = event.data.get("user_name") or str(event.data["user"])
        panel._attr_available = True
        changed = (
            panel._attr_alarm_state != previous_alarm_state
            or panel._attr_available != previous_available
            or panel._attr_changed_by != previous_changed_by
            or panel._attr_extra_state_attributes != previous
        )
        if changed and panel.hass is not None:
            panel.async_write_ha_state()

    listen("pima_state", handle_state)

    async def handle_disconnected(event):
        for panel in entities.values():
            panel._attr_available = False
            if panel.hass is not None:
                panel.async_write_ha_state()

    listen("pima_disconnected", handle_disconnected)


class PimaAlarmControlPanel(AlarmControlPanelEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_unique_id = "pima_alarm"
    _attr_name = None
    _attr_code_format = CodeFormat.NUMBER
    _attr_code_arm_required = False
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_NIGHT
    )

    def __init__(self, server, partition):
        self.server = server
        self.partition = partition
        self._attr_device_info = panel_device_info(server.account)
        if partition == 1:
            self._attr_unique_id = "pima_alarm"
            # The primary alarm represents the panel device itself.
            self._attr_name = None
        else:
            self._attr_unique_id = f"pima_alarm_partition_{partition}"
            self._attr_name = f"Partition {partition}"
        self._attr_alarm_state = STATE_MAP.get(
            server.partition_states.get(partition, "disarmed"),
            AlarmControlPanelState.DISARMED,
        )
        self._attr_available = server.connected
        self._attr_extra_state_attributes = {"partition": partition}

    async def async_alarm_disarm(self, code=None):
        _LOGGER.info("PIMA: disarm requested")
        await self.server.send_operation(OPTYPE_DISARM, partition=self.partition)

    async def async_alarm_arm_away(self, code=None):
        _LOGGER.info("PIMA: arm away requested")
        await self.server.send_operation(OPTYPE_ARM_AWAY, partition=self.partition)

    async def async_alarm_arm_home(self, code=None):
        _LOGGER.info("PIMA: arm home requested")
        await self.server.send_operation(OPTYPE_ARM_HOME1, partition=self.partition)

    async def async_alarm_arm_night(self, code=None):
        _LOGGER.info("PIMA: arm night requested (Home 2)")
        await self.server.send_operation(OPTYPE_ARM_HOME2, partition=self.partition)
