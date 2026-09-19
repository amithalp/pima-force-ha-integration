"""Diagnostic sensors for PIMA Force."""

from datetime import datetime

from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, panel_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up diagnostic sensors from a config entry."""
    await _async_setup(hass, async_add_entities, entry.runtime_data, entry)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Support legacy platform loading during migration."""
    await _async_setup(hass, async_add_entities, hass.data[DOMAIN]["server"], None)


async def _async_setup(hass, async_add_entities, server, entry):
    latest_trigger = _latest_trigger(server.last_triggered)
    sensors = {
        "fault_count": PimaDiagnosticSensor(
            server, "fault_count", len(server.faults)
        ),
        "last_seen": PimaDiagnosticSensor(
            server,
            "last_seen",
            server.last_seen,
            SensorDeviceClass.TIMESTAMP,
        ),
        "last_heartbeat": PimaDiagnosticSensor(
            server,
            "last_heartbeat",
            server.last_heartbeat,
            SensorDeviceClass.TIMESTAMP,
        ),
        "last_triggered_zone": PimaDiagnosticSensor(
            server,
            "last_triggered_zone",
            _zone_label(server, latest_trigger.get("last_triggered_zone")),
            restore=True,
            attributes={"zone": latest_trigger.get("last_triggered_zone")},
        ),
        "last_triggered_partition": PimaDiagnosticSensor(
            server,
            "last_triggered_partition",
            _partition_label(latest_trigger.get("last_triggered_partition")),
            restore=True,
            attributes={
                "partition": latest_trigger.get("last_triggered_partition")
            },
        ),
        "last_triggered_user": PimaDiagnosticSensor(
            server,
            "last_triggered_user",
            _trigger_user(latest_trigger),
            restore=True,
            attributes={"user": latest_trigger.get("last_triggered_user")},
        ),
        "last_triggered_at": PimaDiagnosticSensor(
            server,
            "last_triggered_at",
            _as_datetime(latest_trigger.get("last_triggered_at")),
            SensorDeviceClass.TIMESTAMP,
            restore=True,
        ),
        "last_armed_by": PimaDiagnosticSensor(
            server, "last_armed_by", None, restore=True
        ),
        "last_armed_at": PimaDiagnosticSensor(
            server,
            "last_armed_at",
            None,
            SensorDeviceClass.TIMESTAMP,
            restore=True,
        ),
        "last_disarmed_by": PimaDiagnosticSensor(
            server, "last_disarmed_by", None, restore=True
        ),
        "last_disarmed_at": PimaDiagnosticSensor(
            server,
            "last_disarmed_at",
            None,
            SensorDeviceClass.TIMESTAMP,
            restore=True,
        ),
        "last_system_action": PimaDiagnosticSensor(
            server, "last_system_action", None, restore=True
        ),
    }
    sensors["fault_count"]._attr_extra_state_attributes = {
        "active_faults": [fault["label"] for fault in server.faults],
        "fault_details": list(server.faults),
    }
    sensors["fault_count"]._attr_available = (
        server.connected and server.faults_initialized
    )
    async_add_entities(list(sensors.values()))

    def listen(event_type, handler):
        remove = hass.bus.async_listen(event_type, handler)
        if entry is not None:
            entry.async_on_unload(remove)

    def write(sensor):
        if sensor.hass is not None:
            sensor.async_write_ha_state()

    async def handle_last_seen(event):
        for key in ("last_seen", "last_heartbeat"):
            if key in event.data:
                sensors[key]._attr_native_value = _as_datetime(event.data[key])
                sensors[key]._attr_available = True
                write(sensors[key])

    async def handle_faults(event):
        sensor = sensors["fault_count"]
        sensor._attr_native_value = int(event.data.get("fault_count", 0))
        sensor._attr_extra_state_attributes = {
            "active_faults": event.data.get("active_faults", []),
            "fault_details": event.data.get("fault_details", []),
        }
        sensor._attr_available = True
        write(sensor)

    async def handle_zone_names_updated(event):
        sensor = sensors["last_triggered_zone"]
        zone = sensor._attr_extra_state_attributes.get("zone")
        if zone is None:
            zone = _latest_trigger(server.last_triggered).get("last_triggered_zone")
        if zone is None:
            return
        label = _zone_label(server, zone)
        if sensor._attr_native_value != label:
            sensor._attr_native_value = label
            sensor._attr_extra_state_attributes = {"zone": zone}
            sensor._attr_available = True
            write(sensor)

    async def handle_state(event):
        if "last_triggered_zone" in event.data:
            values = {
                "last_triggered_zone": _zone_label(
                    server, event.data.get("last_triggered_zone")
                ),
                "last_triggered_partition": _partition_label(
                    event.data.get("last_triggered_partition")
                ),
                "last_triggered_user": _trigger_user(event.data),
                "last_triggered_at": _as_datetime(
                    event.data.get("last_triggered_at")
                ),
            }
            sensors["last_triggered_zone"]._attr_extra_state_attributes = {
                "zone": event.data.get("last_triggered_zone")
            }
            sensors["last_triggered_partition"]._attr_extra_state_attributes = {
                "partition": event.data.get("last_triggered_partition")
            }
            sensors["last_triggered_user"]._attr_extra_state_attributes = {
                "user": event.data.get("last_triggered_user")
            }
            for key, value in values.items():
                sensors[key]._attr_native_value = value
                sensors[key]._attr_available = True
                write(sensors[key])

        if event.data.get("action") not in ("armed", "disarmed"):
            return
        action = event.data["action"]
        prefix = "last_armed" if action == "armed" else "last_disarmed"
        actor = event.data.get("user_name") or event.data.get("user") or "Unknown"
        action_at = _as_datetime(event.data.get("action_at"))
        metadata = {
            key: event.data[key]
            for key in ("partition", "user", "state", "cid_type", "action_at")
            if key in event.data
        }
        if "state" in metadata:
            metadata["pima_mode"] = metadata.pop("state")
        for key, value in ((f"{prefix}_by", actor), (f"{prefix}_at", action_at)):
            sensors[key]._attr_native_value = value
            sensors[key]._attr_extra_state_attributes = dict(metadata)
            sensors[key]._attr_available = True
            write(sensors[key])
        action_sensor = sensors["last_system_action"]
        action_sensor._attr_native_value = _system_action_label(event.data.get("state"))
        action_sensor._attr_extra_state_attributes = dict(metadata)
        action_sensor._attr_available = True
        write(action_sensor)

    async def handle_disconnected(event):
        # Historical timestamps and trigger details remain valid while offline.
        # Only current fault status requires an active panel connection.
        sensors["fault_count"]._attr_available = False
        write(sensors["fault_count"])

    async def handle_connected(event):
        if event.data.get("last_seen"):
            sensors["last_seen"]._attr_native_value = _as_datetime(
                event.data["last_seen"]
            )
        for key, sensor in sensors.items():
            if key != "fault_count" and sensor._attr_native_value is not None:
                sensor._attr_available = True
                write(sensor)

    listen("pima_last_seen", handle_last_seen)
    listen("pima_faults_updated", handle_faults)
    listen("pima_zone_names_updated", handle_zone_names_updated)
    listen("pima_state", handle_state)
    listen("pima_disconnected", handle_disconnected)
    listen("pima_connected", handle_connected)


class PimaDiagnosticSensor(RestoreSensor):
    """A non-polling diagnostic value reported by the panel."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        server,
        key,
        value,
        device_class=None,
        *,
        restore=False,
        attributes=None,
    ):
        self.server = server
        self._restore = restore
        self._attr_device_info = panel_device_info(server.account)
        self._attr_unique_id = f"pima_{key}"
        self._attr_translation_key = key
        self._attr_native_value = _as_datetime(value) if device_class else value
        self._attr_device_class = device_class
        self._attr_available = server.connected and value is not None
        self._attr_extra_state_attributes = {
            key: value for key, value in (attributes or {}).items() if value is not None
        }

    async def async_added_to_hass(self):
        """Restore historical trigger data after a restart or reload."""
        await super().async_added_to_hass()
        if not self._restore or self._attr_native_value is not None:
            return
        if (restored := await self.async_get_last_sensor_data()) is None:
            return
        if restored.native_value is None:
            return
        self._attr_native_value = restored.native_value
        self._attr_available = True
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_extra_state_attributes = {
                key: last_state.attributes[key]
                for key in (
                    "zone",
                    "partition",
                    "user",
                    "pima_mode",
                    "cid_type",
                    "action_at",
                )
                if key in last_state.attributes
            }


def _as_datetime(value):
    """Convert an ISO timestamp to the datetime required by HA timestamp sensors."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _trigger_user(data):
    """Prefer the human-readable user name and fall back to the user number."""
    return data.get("last_triggered_user_name") or data.get("last_triggered_user")


def _zone_label(server, zone):
    """Return a readable zone name while retaining its number as an attribute."""
    if zone is None:
        return None
    return server.zones.get(zone, {}).get("name") or f"Zone {zone}"


def _partition_label(partition):
    """Return a readable fallback because Force JSON exposes no partition names."""
    if partition is None:
        return None
    return f"Partition {partition}"


def _system_action_label(state):
    """Convert the internal PIMA mode into a readable audit value."""
    return {
        "armed_away": "Armed Away",
        "armed_home_1": "Armed Home 1",
        "armed_home_2": "Armed Home 2",
        "armed_home_3": "Armed Home 3",
        "armed_home_4": "Armed Home 4",
        "armed_shabbat": "Armed Shabbat",
        "disarmed": "Disarmed",
    }.get(state, state)


def _latest_trigger(triggers):
    """Return the newest trigger across all partitions."""
    if not triggers:
        return {}
    return max(
        triggers.values(),
        key=lambda item: item.get("last_triggered_at") or "",
    )
