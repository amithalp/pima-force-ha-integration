# Protocol fixtures

- `specification.jsonl` contains normalized examples derived from the supplied
  Force JSON specification. Accounts and command credentials are synthetic.
- `sanitized_panel_capture.jsonl` is representative panel traffic assembled
  from the currently observed message shapes and decoder examples. It contains
  no password and uses a synthetic account and English zone names.
- `sanitized_real_panel_capture.jsonl` preserves the message shapes, counter
  reuse, empty 2149 response, and zone-name pagination observed from the target
  FORCE installation. The account and every zone name are synthetic.
- `sanitized_bypass_confirmation.jsonl` records the authoritative distinction
  observed on the real panel: a permanently disabled zone ACKs a bypass write
  but reads back as normal, while the same enabled zone reads back as bypassed
  and emits CID 570.

When adding captures, keep counters and message ordering intact; replace account,
password, user names, zone names, network addresses, and other identifying data.
