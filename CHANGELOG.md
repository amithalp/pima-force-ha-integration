# Changelog

All notable changes to the PIMA Force Home Assistant integration will be
documented in this file. Versions follow semantic versioning.

## 1.20.0 - Community release

- Prepared the authorized `amithalp/pima-force-ha-integration` community
  repository with updated project metadata and joint attribution.
- Added complete Home Assistant installation, configuration, entity, safety,
  troubleshooting, privacy and release documentation.
- Restricted public release material to the Home Assistant integration, tests,
  fixtures and directly related documentation.
- Documented all completed physical tests and the remaining controlled-output
  and multi-partition hardware validation boundaries.

## 1.19.0 - Native entity naming

- Removed duplicated `PIMA` prefixes from the alarm, siren, output and
  additional-partition entity names.
- Adopted Home Assistant device-relative naming while preserving every stable
  unique ID and existing entity-registry association.
- Confirmed the current release scope as one PIMA panel per HA instance and
  documented native HA zone device-class customization.

## 1.18.0 - Self-healing fault state

- Reconcile active faults on later panel heartbeats so a restore missed during
  a power or network outage cannot leave stale trouble state indefinitely.
- Added a `pima.refresh_faults` action for an immediate authoritative `2250`
  refresh without reloading the integration.
- Corrected communication-fault labels so the protocol path byte is not shown
  as a misleading device number such as `#4`.

## 1.17.0 - Confirmed bypass and live configuration refresh

- Verify zone bypass writes against the subsequent `2150` response and report
  commands acknowledged but not applied by the panel.
- Refresh discoverable panel configuration after CID `306`, including zone and
  user names, without overwriting Home Assistant name customizations.
- Avoid update calls for bypass entities that remain disabled in Home Assistant.
- Document real-panel behavior for temporarily bypassed and permanently
  disabled zones.

## 1.16.1 - Test-package correction

- Show PIMA arming buttons as normal device controls instead of configuration
  entities.
- Avoid writing HA state for disabled bypass entities before they are added to
  Home Assistant.

## 1.16.0 - Controls and release preparation

- Added standard Home Assistant buttons for Home 1-4 and Shabbat.
- Added panel-confirmed per-zone bypass switches, disabled by default for
  safety.
- Added contribution, security and pull-request guidance.
- Excluded local iterative test ZIP files from source control.

## 1.15.0 - Release preparation

- Declared the integration explicitly as a Home Assistant hub.
- Added the real-panel compatibility boundary to the documentation.
- Added unit tests and compilation checks to the validation workflow.
- Added an explicit public-release checklist and provenance blocker.

## 1.14.0 - Reliable startup baseline

- Added reliable JSON stream framing and duplicate-event protection.
- Added ACK/NAK correlation, timeouts, and connection-loss handling.
- Added independent partition state and Home 1-4/Shabbat commands.
- Added panel trouble, fault pagination, zone bypass, sirens, and outputs.
- Added config flow, device registry, diagnostics, and English/Hebrew strings.
- Added persistent alarm-trigger and arm/disarm audit information.
- Added configurable Home Assistant zone presentation using generic `opening`
  entities and per-entity **Shown as** overrides.
- Serialized and paced startup requests, with bounded fault-query retries.
- Added sanitized real-panel fixtures and 52 automated tests.
