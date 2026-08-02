# Changelog

All notable changes to the versioned dataset package are recorded here. Published release artifacts remain immutable.

## 1.1.1 - 2026-08-02

Security and release-engineering patch; the record contract remains schema version 1.1.0.

- Reject pathological JSON number magnitudes and exponents before Decimal arithmetic.
- Return stable, value-free errors for unreadable inputs and hostile direct numeric values.
- Execute the candidate release's own corpus validator in a bounded child process.
- Block malformed manifests, path traversal, missing critical assets, stale reports, and candidate-validator failures.
- Scan every declared release asset for common credential signatures.
- Add an adversarial extreme-number vector and public security/threat-model documentation.

## 1.1.0 - 2026-08-02

- Defined gross settled purchase volume and net processing fees as the calculation basis.
- Added exact fee-group, credit, effective-rate, and average-ticket reconciliation.
- Added the semantic validator, adversarial corpus, pinned runtime, checksums, and fail-closed publication gate.
