# PIMA Force 1.21.2

Siren entities now start with an unknown state and wait for panel confirmation.
Reconnecting clears the previous connection's siren state. Empty status replies
confirm neither On nor Off and preserve confirmed physical output events.
Commands still require acknowledgement; an acknowledgement alone is not treated
as proof of the siren's physical state.

Panels returning no siren status values may show Unknown until a physical output
change event arrives. This update does not add polling support to those panels.

## Validation

Local regression tests cover empty replies and both siren event transitions.
On 2026-10-01, the maintainer confirmed on the physical panel that both sirens
initially show Unknown after installing the update, then correctly follow On/Off
changes. A HACS upgrade remains pending.

## Installation

Update through HACS after v1.21.2 is published, then restart Home Assistant.
