# PIMA Force for Home Assistant

[![Validate](https://github.com/amithalp/pima-force-ha-integration/actions/workflows/validate.yaml/badge.svg)](https://github.com/amithalp/pima-force-ha-integration/actions/workflows/validate.yaml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/docs/faq/custom_repositories/)

A local Home Assistant custom integration for PIMA Force alarm panels using
PIMA's JSON-over-TCP interface.

This is an independent community project and is not affiliated with or
endorsed by PIMA Electronic Systems.

## Features

- Alarm control: Away, Home 1 and Disarm through the alarm panel entity.
- Additional buttons for Home 1, Home 2, Home 3, Home 4 and Shabbat.
- One binary sensor per installed zone, with panel-reported Hebrew names.
- Zone attributes for alarm, bypass, arming, tamper, battery, supervision and
  other reported conditions.
- Panel connection, trouble, heartbeat, alarm history and arm/disarm audit
  diagnostics.
- Internal and external siren controls, disabled by default.
- Confirmed per-zone bypass controls, disabled by default.
- Controlled-output switches for outputs 1-8.
- Multiple partition support when the panel reports multiple partitions.
- Local push updates, reconnect recovery, config flow, YAML migration,
  diagnostics download and English/Hebrew translations.

## Requirements and tested compatibility

- A PIMA Force panel with **JSON Interface support**. This is not present in
  every firmware build; ask PIMA or your installer for JSON-capable firmware.
- The panel must be configured in MOKED settings to connect to the Home
  Assistant host's static local IP and the same TCP port configured here.
- A panel account and a dedicated user code with privileges for the operations
  you intend to use.
- Home Assistant 2026.8.0 or newer.

Version 1.20.0 was physically validated with Force JSON Interface 2.3, Home
Assistant Core 2026.8.3, one partition and 24 zones. Testing covered discovery,
zone state, Home 1-4, Away, Shabbat, Disarm, alarm trigger/restore, sirens,
temporary bypass, permanently-disabled-zone rejection, user attribution,
reconnect and active-fault recovery.

Automated tests cover fragmented and combined JSON frames, heartbeat,
ACK/NAK, timeouts, counter rollover, duplicate events, fault pagination,
controlled-output decoding and multiple partitions. Physical testing of
configured controlled outputs and multiple partitions remains outstanding.

The current release supports one panel per Home Assistant installation.

## Installation

### HACS custom repository

1. Open HACS, then **Integrations**.
2. Open the three-dot menu and select **Custom repositories**.
3. Add `https://github.com/amithalp/pima-force-ha-integration` with category
   **Integration**.
4. Search for **PIMA Force**, install it, and restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration** and select
   **PIMA Force**.

### Manual installation

Copy `custom_components/pima` from this repository to
`<config>/custom_components/pima`, restart Home Assistant, then add the
integration from **Settings → Devices & services**.

## Configuration

Enter the panel account, privileged user code and TCP listener port. The port
must match the destination port configured in the panel's MOKED settings. The
panel initiates the connection; Home Assistant does not connect outward to the
panel. A delay before the first connection can therefore be caused by the
panel's own reconnect interval.

Legacy YAML is imported automatically:

```yaml
pima:
  account: !secret pima_account
  password: !secret pima_password
  port: 10006
```

After confirming the imported config entry works, remove the old `pima:` block
and restart Home Assistant. Further changes can be made with **Reconfigure** on
the integration entry.

Only one config entry is currently allowed. Rename the PIMA device using Home
Assistant's native device settings if you want a custom panel name.

## Entities

| Domain | Purpose |
|---|---|
| `alarm_control_panel` | Primary partition; Away, Home 1 and Disarm |
| `binary_sensor` | Zones, panel connection and panel trouble |
| `button` | Home 1, Home 2, Home 3, Home 4 and Shabbat commands |
| `sensor` | Fault count, timestamps, last alarm and arm/disarm audit data |
| `siren` | Internal and external sirens; disabled by default |
| `switch` | Outputs 1-8 and per-zone bypass controls |

Additional partitions are created as additional alarm control panel entities.
PIMA's JSON interface does not expose partition names, so they are displayed as
`Partition N`.

### Zone presentation

The JSON interface does not report whether a physical zone is a door contact,
window contact, motion detector, curtain detector or another sensor type. Zone
entities therefore use Home Assistant's generic `opening` class by default.

To correct one, open **Settings → Devices & services → Entities**, select the
zone, open its settings, and change **Shown as**. Home Assistant then supplies
the appropriate icon, state labels and colour. This native customization
survives integration upgrades and does not change PIMA behavior.

### Zone bypass

Bypass temporarily excludes a zone from protection. Each zone has a bypass
switch that is disabled by default. Enable only the specific switch you intend
to use from **Settings → Devices & services → Entities**.

The integration waits for the panel ACK and reads the authoritative bypass
state back before reporting success. If a zone is permanently cancelled in
technician programming, the panel may acknowledge a temporary-bypass request
without applying it; Home Assistant then reports the operation as failed.
Permanent technician cancellation is not exposed by JSON Interface 2.3.

### Sirens and outputs

Siren entities are disabled by default to prevent accidental activation. Enable
them intentionally from the entity registry and test them only when it is safe.

Output switches represent PIMA controlled outputs 1-8. Output decoding is
covered by automated tests, but physical output operation has not yet been
validated on a panel with configured outputs.

### Faults and historical diagnostics

Fault state is reconciled after relevant events and periodically while a fault
remains active. Run the `pima.refresh_faults` action for an immediate read-only
refresh without reloading the integration.

The last alarm zone, partition and time, as well as the last arm/disarm user and
action, are restored after a Home Assistant restart. The alarm event identifies
a zone rather than a person, so user diagnostics describe who armed or disarmed
the system; they do not claim that a user triggered the alarm.

## Troubleshooting

- **Entities remain unavailable after restart:** wait for the panel to reconnect
  and confirm its MOKED destination IP and port match Home Assistant.
- **Connection takes minutes:** the listener is already ready; connection timing
  is controlled by the panel's retry schedule. Saving relevant panel network
  settings may cause the panel to reconnect sooner, but is not required.
- **`Incorrect code` / `קוד שגוי`:** verify the configured user code and its
  permissions.
- **Bypass immediately returns off:** the panel did not apply it. Check whether
  the zone is permanently cancelled or otherwise unavailable.
- **Zone name changed at the keypad:** programming-change event CID 306 causes a
  delayed refresh. If the panel did not send it, reload the integration.
- **Stale trouble state:** run `pima.refresh_faults`; if necessary, reload the
  integration entry.

For debug logs, add temporarily:

```yaml
logger:
  logs:
    custom_components.pima: debug
```

Never publish logs containing real account numbers, user codes, IP addresses,
zone names or user names. Remove debug logging after testing.

## Contributions and support

Open issues at the [project issue tracker](https://github.com/amithalp/pima-force-ha-integration/issues).
For useful hardware reports, include panel model, firmware, JSON interface
version, zone count and partition count, with all private values redacted. See
[CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## Credits

- [aarbelle](https://github.com/aarbelle) created the original Home Assistant
  integration and foundational implementation.
- [amithalp](https://github.com/amithalp) directed and developed the expanded
  integration and performed the physical PIMA Force and Home Assistant testing.
- OpenAI Codex assisted amithalp with code analysis, implementation, automated
  tests, documentation and debugging. It is credited as a development tool,
  not as a repository owner or maintainer.
- PIMA Electronic Systems authored the Force Interface JSON Format
  Specification used to understand the panel protocol.

See [AUTHORS.md](AUTHORS.md) for full attribution. This project is distributed
under the [MIT License](LICENSE).
