# Security policy

## Reporting a vulnerability

Do not disclose vulnerabilities, passwords, RADIUS shared secrets, SSH private
keys, serial transcripts or configuration backups in a public issue.

Contact the maintainer privately and include:

- affected ConsolePi+ version;
- a concise reproduction procedure;
- the expected and actual behaviour;
- logs with secrets and customer data removed.

The maintainer should acknowledge a report promptly, prepare a fix privately
and publish the fix and advisory once users can update safely.

## Supported releases

The current supported release is **1.9.1**. Only the latest released version
should be treated as supported. Application update packages must be signed
with the release administrator's offline/private signing key. Published source,
installer and image archives have SHA-256 checksums; checksums alone are not signatures.

## Security assessment material for 1.9.1

See [the security documentation](docs/security/README.md) for the auditor
summary, technical document and acceptance workbook with dated UI screenshots.
Screenshots illustrate controls; they do not establish that a test passed.
The documents identify a mismatch between logging labels and the session
implementation. Both `output` and `full` use `picocom` output logging; the
active path does not apply the redaction writer. Device output may contain
credentials, echoed input or configuration. Keep events-only logging when
terminal content must not be retained.

## Optional remote syslog

[Remote event forwarding](docs/SYSLOG.md) is disabled by default. TLS verifies the
server certificate and identity. Serial transcripts are excluded, but event
metadata requires controlled server access and retention. A bounded queue can
lose messages when full; successful TCP submission does not prove durable server
storage. Factory reset and generic-image sanitization clear the destination,
custom CA and pending events.
