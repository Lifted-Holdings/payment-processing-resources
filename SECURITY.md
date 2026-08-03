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
- release archives that cannot be rebuilt twice to identical bytes from the declared manifest;
- a validator that fails, times out, emits malformed output, or does not reproduce the corpus;
- a candidate validator that fails its bounded behavioral regression suite;
- an unpinned validation dependency or stale validation report;
- inconsistent package, schema, citation, DOI, or source-release identity;
- a candidate that reuses an existing release version while changing its tagged files;
- a tagless archive or incomplete clone presented as publication-ready;
- a dirty or uncommitted candidate tree;
- an origin outside the authoritative Lifted Holdings repository;
- an unavailable, malformed, missing, divergent, or non-monotonic remote release tag;
- common private-key, cloud-key, repository-token, model-token, chat-token, or live payment-key signatures anywhere in the declared release;
- Unicode control characters that can conceal or reorder displayed release text;
- synthetic records that violate structural, accounting, precision, period, privacy, size, depth, safe-number, or spreadsheet-formula rules; or
- a stale, private, mislabeled, byte-divergent, corrupt, or extra-file Kaggle catalog version; or
- a Zenodo or Hugging Face mirror with an extra or missing file, mutable-ref byte read, or byte mismatch.

Candidate validation runs in a bounded child process and must return a machine-readable corpus report. Gate output contains fixed rule messages and hashes, never released file contents or submitted statement values.

## Assurance modes and execution order

`--mode package` is portable and proves internal consistency only. Its successful status is `valid`, never `ready` or `verified`. `--mode candidate` is the publication boundary and requires a real clean Git worktree, committed byte identity, the authoritative origin, a complete remote tag inventory, and two byte-identical archive builds. `--mode published` additionally verifies GitHub, Zenodo, DOI, Hugging Face, Kaggle, and Software Heritage evidence; a network, rate-limit, redirect, digest, or identity failure blocks rather than falling back to local success.

The gate performs bounded manifest, path, inventory, size, encoding, checksum, secret-signature, unsafe-text-control, identity, Git, and tag checks before it executes the candidate validator or its behavioral regression suite. The candidate suite includes public-attestation, release-asset, and provenance regressions, so mirror-verifier failures are found before publication. This prevents an untrusted or incomplete candidate from reaching the executable portion of the workflow merely because it can rewrite its own checksum file.

## Trust boundaries and non-goals

This repository accepts only statement-level aggregates. It is not designed to ingest source statements, cardholder data, bank data, merchant-owner data, credentials, or secrets. Automated pattern screening is defense in depth; it cannot prove arbitrary prose contains no identifying or confidential information. Human review remains mandatory before any record is made public.

The gate establishes reproducibility, internal consistency, and declared release provenance. It is not a malware sandbox, digital signature, accounting opinion, legal determination, interchange-qualification audit, or guarantee that a mapped source statement is complete. SHA-256 proves byte agreement, not author identity; the authoritative Git origin, immutable tag, DOI record, and independent archive surfaces supply the declared provenance boundary. Published mode requires exact mirror inventories and downloads Hugging Face bytes from the reported immutable commit rather than the mutable `main` ref. Run executable candidate validation only on a locally reviewed checkout. Published mode verifies release identity and bytes; it does not make arbitrary contributed Python safe to execute.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting workflow in the repository Security tab. Do not include real merchant statements, PANs, authentication data, bank details, credentials, or other sensitive values in a report. A minimal synthetic reproducer is sufficient.
