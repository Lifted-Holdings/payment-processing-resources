# Changelog

All notable changes to the versioned dataset package are recorded here. Published release artifacts remain immutable.

## Unreleased

Validator availability and privacy-screening corrections. No change to the schema 1.2.0 record contract.

- Remove quadratic backtracking from the note-privacy screens. The unbounded mask-run quantifiers in the truncated-PAN patterns made scanning cost grow with the square of the note length, so a record inside the one-megabyte input limit could occupy the validator for hours; a 16,000-character note took 47 seconds before the fix and 6 milliseconds after.
- Screen card numbers over NFKC-normalized text and treat any Unicode space, punctuation, or format character as a digit separator, closing bypasses using U+00A0 and other non-breaking spaces, dot and middot separators, and compatibility digit forms. Card-number candidates are now matched as 13-to-19 digit windows inside longer digit runs, so an adjacent expiry or reference number no longer hides a PAN. Luhn remains the confirmation step.
- Stop reporting ordinary reporting prose as prohibited payment data. An ending phrase followed by a four-digit calendar year, and the bare word "account" near a four-digit number, are no longer treated as truncated card or bank references unless the text names a card or account number outright.
- Reject negative zero in any amount or rate. JSON Schema compares `-0.0` as equal to `0`, so a `minimum: 0` bound admitted it and the accounting rules reconciled, leaving `-0.00` to surface only in published output.
- Verify the schema file against the SHA-256 that `checksums.txt` declares for it before using it to validate anything, and fail closed on disagreement. A copy that ships without `checksums.txt` still validates and reports its schema as `undeclared`, so offline and packaged use is unaffected.
- Reject text containing unpaired surrogates, which pass every structural rule and then raise `UnicodeEncodeError` when the record is serialized.
- Require each invalid corpus vector to emit exactly its declared rule codes instead of a superset, so an unintended second defect in a vector can no longer pass unnoticed.
- Reword the CLI success line, which claimed a record "satisfies ... privacy rules" although `SECURITY.md` states that pattern screening cannot establish that prose is free of identifying information.
- Add registered hostile vectors for negative zero, separator-obfuscated card numbers, and unpaired surrogates, plus regression coverage for scan growth, obfuscation, prose false positives, schema integrity, and corpus code exactness.

## 1.1.7 - 2026-08-03

- Treat Kaggle's public version history as the immutable release index when its anonymous top-level current-version pointer lags behind a newly Ready version.
- Require one unique latest Ready version whose notes name the expected package, and reject malformed, duplicate, non-Ready, or superseded records.
- Verify the version-specific human page contains the exact package version, DOI, source release, and archive SHA-256 before downloading that declared version and comparing every path and byte.
- Preserve the v1.1.6 canonical dataset identity checks and every v1.1.5 transformed-tree, privacy, determinism, provenance, and non-goal boundary.

## 1.1.6 - 2026-08-03

- Replace Kaggle's eventually consistent search catalog with the canonical dataset-view endpoint for current identity, metadata, and version attestation.
- Require the canonical view response to match the exact dataset owner/slug before requesting its declared version bundle.
- Preserve the v1.1.5 byte-exact verification of Kaggle's platform-expanded archive tree and every schema 1.1.0 validation, privacy, provenance, and non-goal boundary.

## 1.1.5 - 2026-08-03

- Model Kaggle's platform archive expansion explicitly: accept either the intact canonical archive plus sidecar or the exact expanded archive tree plus sidecar.
- Reconstruct the expanded inventory only from the canonical release archive and compare every path and byte without extracting files or executing downloaded code.
- Reject extra, missing, duplicate, case-fold-colliding, traversal, absolute, backslash, NUL, symlink, oversized, corrupt, or unexpected transformed members.
- Declare the current versioned source and archival DOI in Kaggle's supported `userSpecifiedSources` metadata so old release provenance cannot persist silently.
- Preserve schema 1.1.0 and every v1.1.4 privacy, determinism, mirror-inventory, provenance, and non-goal boundary.

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
