# Changelog

All notable changes to the versioned dataset package are recorded here. Published release artifacts remain immutable.

## 1.1.4 - 2026-08-03

- Build the release ZIP from the declared manifest with fixed timestamps, stable ordering, fixed permissions, and stored members so clean builds produce identical bytes across platforms.
- Extend published attestation to Kaggle and block stale metadata, divergent bundles, unexpected members, unsafe paths, symlinks, corrupt compression, or archive-byte disagreement.
- Add a deterministic Kaggle distribution builder that stages only the exact release archive and SHA-256 sidecar while injecting the observed digest into public metadata.
- Reject labeled, unlabeled, brand-masked, and first-six/last-five card references plus Unicode control characters that can obscure or reorder displayed audit notes or release text.
- Require exact Zenodo, Kaggle, and Hugging Face inventories, tie Hugging Face downloads to its reported immutable commit, and run public-attestation, release-asset, and provenance regressions before publication.
- Add registered hostile vectors and regression coverage for the new privacy, archive, compression, and mirror boundaries without changing schema 1.1.0.

## 1.1.3 - 2026-08-02

- Split portable package validation from publication readiness so a tagless archive can never claim release provenance.
- Require a clean committed tree, authoritative origin, complete remote tag inventory, exact local/remote tag alignment, and monotonic new versions.
- Run static inventory, path, size, encoding, checksum, credential-signature, identity, and provenance checks before executing candidate Python.
- Add a bounded non-executing public attestor for GitHub release assets, Zenodo metadata and bytes, DOI resolution, Hugging Face archive equality, and Software Heritage branch/tag provenance.
- Reject unsafe redirects, oversized responses, archive traversal, case-fold aliases, symlinks, undeclared members, digest mismatches, and public identity drift.
- Add 20 provenance and external-attestation regressions while preserving the schema 1.1.0 record contract.

## 1.1.2 - 2026-08-02

- Require the publication gate to compare the manifest with the complete candidate release tree.
- Run the candidate validator's behavioral regression suite in addition to the compact synthetic corpus.
- Bound release file count, individual asset size, and aggregate release size before content scanning.
- Reject spreadsheet-formula prefixes in CSV cells without echoing submitted values.
- Validate trusted title, semantic versions, release date, DOI pair, license, canonical URL, and source-release identity.
- Block changed files from masquerading as an existing immutable Git tag.
- Add regression coverage for identity, bank, credential, rounding-tie, and zero-fee edge cases.

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
