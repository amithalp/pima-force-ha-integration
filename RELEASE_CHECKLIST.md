# Release checklist

## Required before publishing

- [x] Add the MIT License authorized for the community release as `LICENSE`.
- [x] Create or confirm the public repository at
  `amithalp/pima-force-ha-integration` with Issues enabled.
- [x] Confirm the repository description and topics include Home Assistant,
  PIMA, alarm and HACS.
- [ ] Push the complete Git history and release candidate.
- [ ] Require the unit-test, HACS and hassfest validation jobs to pass.
- [ ] Perform an upgrade through HACS from 1.21.0.
- [ ] Create a full GitHub release for `v1.21.1`, not only a tag, using
  `RELEASE_NOTES.md`.

## Completed release preparation

- [x] Public metadata points to `amithalp/pima-force-ha-integration`.
- [x] Maintainer metadata names the active maintainer; attribution separately
  credits aarbelle, amithalp and OpenAI Codex accurately.
- [x] Documentation covers installation, configuration, entities, safety,
  privacy, troubleshooting, limitations and tested compatibility.
- [x] The public release scope contains only Home Assistant integration code,
  tests, fixtures and related documentation.
- [x] Credentials and account fields are redacted in integration logs and
  diagnostics.
- [x] Sirens and zone-bypass entities are disabled by default.

## Validation status

- [x] One JSON-capable PIMA Force panel: JSON 2.3, HA 2026.8.3, 24 zones,
  one partition.
- [x] Discovery, reconnect, zone states and native zone presentation overrides.
- [x] Away, Home 1-4, Shabbat and Disarm.
- [x] Alarm trigger/restore and persistent last-alarm diagnostics.
- [x] User attribution for keypad, app and Home Assistant operations.
- [x] Internal and external siren ON/OFF.
- [x] Temporary zone bypass from the panel and Home Assistant.
- [x] Rejection when temporary bypass is not applied to a permanently disabled
  zone.
- [x] Live connection/trouble state and active-fault recovery after reload.
- [x] Confirm zone open/close and the four-minute heartbeat no longer republish
  an unchanged alarm entity on the physical panel.
- [x] Confirm the alarm entity still updates for arm/disarm and genuine
  connection transitions.
- [ ] Confirm the 12-minute watchdog disconnects and later reconnects on a
  physical panel; automated coverage is complete.
- [ ] Multiple physical partitions — automated only; no suitable panel tested.
- [ ] Controlled outputs — protocol automated tests only; no configured output
  available for physical verification.
- [ ] Additional independent panel/firmware installations.

## Optional future distribution

- [ ] Submit the repository to Home Assistant Brands with the required icon.
- [ ] After Brands approval and community use, consider requesting inclusion in
  the HACS default repository list. A custom-repository HACS release does not
  require waiting for that review.
