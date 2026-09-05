"""Diagnostics support for PIMA Force."""

from homeassistant.components.diagnostics import async_redact_data


TO_REDACT = {
    "account",
    "password",
    "name",
    "user_name",
    "last_triggered_user_name",
}


async def async_get_config_entry_diagnostics(hass, entry):
    """Return a privacy-safe diagnostic snapshot for a config entry."""
    server = entry.runtime_data
    zones = {
        zone: dict(values)
        for zone, values in sorted(server.zones.items())
    }
    data = {
        "config_entry": dict(entry.data),
        "connection": {
            "connected": server.connected,
            "port": server.port,
            "last_seen": _isoformat(server.last_seen),
            "last_heartbeat": _isoformat(server.last_heartbeat),
        },
        "panel": {
            "installed_zones": server.installed_zones,
            "existing_partitions": sorted(server.existing_partitions),
            "partition_states": dict(server.partition_states),
            "zone_count": len(server.zones),
            "zones": zones,
            "faults_initialized": server.faults_initialized,
            "faults": list(server.faults),
            "bypassed_zones": sorted(
                zone
                for zone, values in server.zones.items()
                if values.get("manual_bypassed")
            ),
            "user_count": len(server.users),
            "last_triggered": dict(server.last_triggered),
            "sirens": dict(server.sirens),
            "controlled_outputs": dict(server.outputs),
        },
    }
    return async_redact_data(data, TO_REDACT)


def _isoformat(value):
    """Serialize optional datetime values."""
    return value.isoformat() if value is not None else None
