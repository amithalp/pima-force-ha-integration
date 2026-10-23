# Open issues

## Siren state recovery after Home Assistant restart

- Status: Fix prepared in 1.21.3 — awaiting physical-panel validation.
- Recorded: 2026-10-22.
- Affected integration version: 1.21.2.

Both sirens start as Unknown after startup or reconnect until the panel supplies
a status value or a physical output-change event. Frequent HA restarts therefore
leave the user without a known siren state, even when both sirens are off.

### Confirmed evidence

- The captured panel response to DATA-REQ 2301, orders 1–2, contains an empty
  parameters list. This does not confirm either On or Off.
- Physical On/Off changes update both siren entities successfully through output
  events (770).
- A colour copy of PIMA's JSON interface specification version 2.3 highlights
  both siren-status queries (2301, orders 1–2) and controlled-output status
  queries (2301, orders 34–41) as unsupported in Force firmware 1.6.86.
- The installed panel firmware version has not yet been confirmed in this
  investigation. The document does not establish support in later versions.
- PIMA responded with "JSON outputs report and status", reviewed 2026-10-23:
  request 2201 with partition=0 and opclass=1; first and second parameters are
  external/internal sirens (0=Off, 1=On). Live updates use event 770.
- PIMA requires Zone/output status reporting enabled on the fourth Event
  Reporting screen of the monitoring station configured for HA.
- The 1.21.3 candidate implements this request. Firmware compatibility and
  physical-panel startup/reconnect verification remain open.

### Follow-up

- [ ] Record PIMA's response and the installed panel firmware version.
- [ ] Confirm which JSON-capable firmware supports current siren/output status
  queries, and whether an alternative supported query exists.
- [ ] Verify startup and reconnect state recovery on the physical panel using
  the supported mechanism, if available.
- [ ] If current-state queries remain unavailable, decide whether to restore
  the last confirmed state with explicit restored/unconfirmed metadata. This
  is a proposed fallback, not an implemented or approved behavior change.

Do not interpret an empty response or a command acknowledgement as proof of
the physical state. No automatic siren activation should be used to recover
state after restart.
