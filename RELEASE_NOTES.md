# PIMA Force 1.20.0

This is the first community release maintained at
`amithalp/pima-force-ha-integration`. It expands the original proof of concept
into a config-entry-based Home Assistant integration while preserving existing
entity unique IDs.

## Highlights

- Reliable streaming JSON framing, serialized requests, unique counters,
  duplicate-event suppression, ACK/NAK correlation and command timeouts.
- Alarm trigger/restore, multiple partitions, Away, Home 1-4, Shabbat and
  Disarm.
- Zone discovery, panel-provided names, rich status attributes and native Home
  Assistant **Shown as** customization.
- Panel-confirmed temporary bypass with clear failure when an acknowledged
  operation is not applied.
- Panel faults with pagination, heartbeat reconciliation and the
  `pima.refresh_faults` action.
- Internal/external sirens and controlled outputs.
- Persistent last-alarm and arm/disarm audit diagnostics.
- Config flow, YAML import, reconfiguration, device registry, redacted
  diagnostics, English/Hebrew translations and Home Assistant-native naming.

## Safety and upgrade notes

- Sirens and per-zone bypass switches are disabled by default. Enable only the
  entities you intentionally plan to operate.
- Existing YAML configuration is imported into a config entry. Verify the new
  entry, then remove the legacy `pima:` block and restart Home Assistant.
- The panel initiates the TCP connection, so availability after restart depends
  on the panel's reconnect interval.
- Permanent technician cancellation is not exposed by JSON Interface 2.3.

## Validation boundary

Physically validated with Force JSON Interface 2.3, Home Assistant Core
2026.8.3, one partition and 24 zones. Multiple partitions and controlled-output
behavior are covered by automated protocol tests but have not been physically
validated on suitable hardware.

## Credits

The release retains joint credit for aarbelle's original integration,
amithalp's direction, development and physical validation, and OpenAI Codex's
development assistance. See `AUTHORS.md` for details.
