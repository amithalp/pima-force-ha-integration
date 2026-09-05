# PIMA Force 1.21.0

This focused reliability release reduces unnecessary Home Assistant state
traffic and detects a connected panel that has silently stopped communicating.

## Changes

- `last_seen` and `last_heartbeat` are no longer copied onto the alarm control
  panel entity. Their existing dedicated diagnostic sensors remain unchanged.
- A PIMA keepalive no longer republishes an unchanged alarm state. Zone changes
  still update their zone entities immediately, while arm/disarm,
  trigger/restore, partition and connection transitions continue to update the
  alarm entity normally.
- An authoritative partition refresh no longer republishes an alarm state when
  it exactly matches the event already received from the panel.
- A new watchdog closes the active panel connection and reports it unavailable
  after 12 minutes with no received JSON traffic. Any valid panel traffic resets
  the watchdog, giving the normal four-minute heartbeat three expected periods
  before a stale connection is declared.
- Existing entity IDs, timestamp restore behavior, configuration and dashboards
  are preserved.

## Validation

Automated coverage verifies that alarm entities no longer subscribe to
timestamp-only updates, that ordinary panel traffic postpones the watchdog,
and that a stale session emits exactly one disconnect transition. Physical
validation should confirm quiet zone activation/deactivation traffic and normal
reconnect behavior before moving dependent automations to a production system.
