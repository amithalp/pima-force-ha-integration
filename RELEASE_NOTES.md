# PIMA Force 1.21.3 — release candidate

This update addresses sirens remaining Unknown after Home Assistant restarts.
The integration now requests physical output status using ID 2201 instead of
2301 for sirens, following PIMA's supplied "JSON outputs report and status"
document. The first two values identify the external and internal siren state.

Requests run at startup, reconnect, and after acknowledged siren commands.
Live event 770 updates remain supported. Empty or invalid responses do not
replace confirmed state; before confirmation the state remains Unknown.
Controlled-output switches retain their existing 2301 queries.

In the monitoring station configured for Home Assistant, enable
"Zone/output status reporting" on the fourth Event Reporting screen, as
instructed by PIMA support.

## Validation and publication gate

All 69 local tests passed; compilation and whitespace checks passed.
Automated coverage includes startup requests, command refresh, documented
16-output responses, page offsets, invalid/empty values, and live events.
On 2026-10-23, the maintainer confirmed both sirens automatically showed Off
after HA restarted and the panel connected, without siren activation.
Live On/Off regression checks and a second restart remain pending.
Do not publish until the maintainer confirms the test build on the panel.

## Manual test installation

The test ZIP contains a top-level pima/ directory. With the ZIP uploaded to
/homeassistant/custom_components, use Terminal & SSH:

```sh
cd /homeassistant/custom_components
unzip -o pima-integration-test-v1.21.3.zip
ha core check
```

Only after a successful check, run `ha core restart`.
Verify both physically inactive sirens automatically become Off without sending
siren commands. Enable debug logging to capture the 2201 request and response.
Then verify live On/Off updates, post-command refresh, and a second restart.
