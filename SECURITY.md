# Security policy and publication threat model

## Supported release

Security fixes are applied to the newest versioned release. Published GitHub and Zenodo artifacts are immutable; a fix receives a new release, checksums, validation report, and Zenodo version DOI.

## What the publication gate defends

The release gate is designed to fail closed when it encounters:

- a malformed, incomplete, duplicated, absolute, or path-traversing manifest;
- an undeclared file in the candidate release tree;
- a missing, symlinked, non-UTF-8, or non-LF declared artifact;
- an excessive file count, individual asset size, or aggregate release size;
- a checksum mismatch or undeclared security-critical file;
- a validator that fails, times out, emits malformed output, or does not reproduce the corpus;
- a candidate validator that fails its bounded behavioral regression suite;
- an unpinned validation dependency or stale validation report;
- inconsistent package, schema, citation, DOI, or source-release identity;
- a candidate that reuses an existing release version while changing its tagged files;
- common private-key, cloud-key, repository-token, model-token, chat-token, or live payment-key signatures anywhere in the declared release; or
- synthetic records that violate structural, accounting, precision, period, privacy, size, depth, safe-number, or spreadsheet-formula rules.

Candidate validation runs in a bounded child process and must return a machine-readable corpus report. Gate output contains fixed rule messages and hashes, never released file contents or submitted statement values.

## Trust boundaries and non-goals

This repository accepts only statement-level aggregates. It is not designed to ingest source statements, cardholder data, bank data, merchant-owner data, credentials, or secrets. Automated pattern screening is defense in depth; it cannot prove arbitrary prose contains no identifying or confidential information. Human review remains mandatory before any record is made public.

The gate establishes reproducibility and internal consistency of the declared package. It is not a malware sandbox, digital signature, accounting opinion, legal determination, interchange-qualification audit, or guarantee that a mapped source statement is complete. Run the gate only on a locally reviewed candidate checkout. Verify the signed Git commit or release provenance separately when that assurance is required.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting workflow in the repository Security tab. Do not include real merchant statements, PANs, authentication data, bank details, credentials, or other sensitive values in a report. A minimal synthetic reproducer is sufficient.
