# Open issues

## Siren state recovery after Home Assistant restart

- Status: Resolved on the tested panel in 1.21.3 — publication pending.
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
- On 2026-10-23, the maintainer confirmed that after HA restarted and the
  panel connected, both sirens automatically showed Off as expected.
- The maintainer also verified manual control of both sirens and Off state
  recovery after a second HA restart on 2026-10-23. Broader firmware
  compatibility has not been established.

### Follow-up

- [x] Record PIMA's response and implement its documented 2201 query.
- [x] Verify automatic Off state recovery after two HA restarts and manual
  On/Off control of both sirens on the physical panel.
- [ ] Complete GitHub validation and obtain approval to publish 1.21.3.
- [ ] Record installed firmware version for the compatibility record.

Restoring remembered siren state is not needed for the tested panel because
current-state querying works. Controlled-output firmware support is not
established by these siren tests.

Do not interpret an empty response or a command acknowledgement as proof of
the physical state. No automatic siren activation should be used to recover
state after restart.
