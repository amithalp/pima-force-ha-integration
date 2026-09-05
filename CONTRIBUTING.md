# Contributing

Contributions and additional real-panel test reports are welcome.

## Development checks

Run from the repository root:

```text
python -m compileall -q custom_components/pima tests
python -m unittest discover -s tests -v
```

Open changes against a feature branch, add or update tests, and keep the
manifest version unchanged unless the maintainer is preparing a release.

Pull requests should keep credentials, account numbers, IP addresses, user and
zone names out of logs and fixtures. New protocol behavior should include a
sanitized fixture and a focused automated test. State-changing panel commands
must correlate ACK/NAK, report timeouts and refresh the authoritative panel
state where the protocol supports it.

## Real-panel reports

Include the panel model, firmware version, JSON interface version, installed
zone count and partition count. Describe the observed result, but redact
accounts, passwords, network addresses and personal names.
