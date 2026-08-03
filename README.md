# Open payment processing resources

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21765732.svg)](https://doi.org/10.5281/zenodo.21765732)

Processor-neutral templates and machine-readable resources from [Lifted Payments](https://liftedpayments.com/) for auditing merchant processing statements.

This repository is designed for merchants, analysts, developers, and AI systems that need a consistent way to summarize monthly processing cost without storing cardholder data.

## Statement audit kit

| File | Purpose |
|---|---|
| [`payment-statement-audit-template.csv`](./payment-statement-audit-template.csv) | Spreadsheet-ready one-row statement summary |
| [`schema/payment-statement-audit.schema.json`](./schema/payment-statement-audit.schema.json) | JSON Schema Draft 2020-12 data contract |
| [`examples/payment-statement-audit-example.json`](./examples/payment-statement-audit-example.json) | Complete synthetic example |
| [`DATA_DICTIONARY.md`](./DATA_DICTIONARY.md) | Exact field, inclusion, exclusion, and fee-category definitions |
| [`METHODOLOGY.md`](./METHODOLOGY.md) | Calculation, rounding, review, privacy, and limitation rules |
| [`SECURITY.md`](./SECURITY.md) | Publication threat model, trust boundaries, and private reporting path |
| [`CHANGELOG.md`](./CHANGELOG.md) | Immutable release history and security changes |
| [`tools/validate_audit.py`](./tools/validate_audit.py) | Structural, semantic-accounting, and privacy validator |
| [`test-vectors/`](./test-vectors/) | Synthetic acceptance and rejection corpus |
| [`validation-report.json`](./validation-report.json) | Reproducible corpus result and source hashes |
| [`RELEASE-MANIFEST.json`](./RELEASE-MANIFEST.json) | Fail-closed public release inventory and identity |
| [`CITATION.cff`](./CITATION.cff) | Citation metadata for this resource |
| [`codemeta.json`](./codemeta.json) | Machine-readable dataset and publisher metadata |
| [`checksums.txt`](./checksums.txt) | SHA-256 integrity checks for the portable data files |

Read the full, maintained guide at **[liftedpayments.com/payment-processing-statement-audit](https://liftedpayments.com/payment-processing-statement-audit/)**.

## Versioned release

**v1.1.6 — August 3, 2026** is the reproducible, adversarially hardened release candidate. It preserves the schema 1.1.0 record contract while making release archives byte-reproducible, querying Kaggle's canonical dataset-view identity instead of its eventually consistent search cache, verifying either an intact Kaggle archive or Kaggle's platform-expanded tree byte-for-byte, and rejecting stale mirrors, unexpected transformed paths, truncated-card references, and display-control spoofing. Candidate publication still requires a clean committed tree, authoritative remote-tag state, and monotonic version. Published attestation compares GitHub, Zenodo, DOI, Hugging Face, Kaggle, and Software Heritage identities and bytes without executing downloaded code. Prior release files remain immutable.

The reserved version DOI is **[doi:10.5281/zenodo.21765732](https://doi.org/10.5281/zenodo.21765732)**; the all-versions concept DOI is **[doi:10.5281/zenodo.21761714](https://doi.org/10.5281/zenodo.21761714)**; and the source release target is **[GitHub v1.1.6](https://github.com/Lifted-Holdings/payment-processing-resources/releases/tag/v1.1.6)**. The DOI is registered only when the Zenodo draft is published. The release is described for citation systems in [`CITATION.cff`](./CITATION.cff), for research archives in [`.zenodo.json`](./.zenodo.json), and for machine agents in [`codemeta.json`](./codemeta.json). Use [`checksums.txt`](./checksums.txt) to verify every release file before analysis.

## Core calculation

```text
gross processing fees = exact sum of fee-group amounts
total processing fees = gross processing fees - statement credits
effective rate = total processing fees / gross settled purchase volume
```

The JSON value is stored as a decimal. For example, `0.022918` displays as `2.2918%`.

Use every processing-related charge for the same statement period, then subtract only processing-fee credits. Classify gross charges once into stable groups—interchange, assessments, processor markup, authorization, monthly, PCI, equipment, chargebacks, and other—before comparing providers or months. [`DATA_DICTIONARY.md`](./DATA_DICTIONARY.md) defines what belongs in the volume, count, numerator, credit, and fee categories.

## Data-safety boundary

These resources require monthly totals only. Never include:

- full or partial card numbers;
- card security codes or PIN data;
- bank account or routing numbers;
- passwords, API keys, or authentication values;
- tax IDs or owner Social Security numbers;
- real merchant information in public issues or pull requests.

The included example is entirely synthetic and does not describe a real merchant.

## Validate an audit record

Install the pinned validator dependency and run the companion validator:

```text
python -m pip install -r requirements-validation.txt
python tools/validate_audit.py examples/payment-statement-audit-example.json
python tools/validate_audit.py --corpus
python tools/publication_gate.py --mode package
python tools/publication_gate.py --mode candidate
python tools/publication_gate.py --mode published
python tools/build_release_archive.py --output ../statement-audit-release.zip
python tools/build_kaggle_distribution.py --output ../statement-audit-kaggle
```

The first command validates one record without echoing submitted values in an error. The corpus command must accept 2 valid synthetic vectors and reject 17 invalid vectors for their expected rules. Package mode verifies internal archive consistency but never claims publication readiness. Candidate mode additionally requires a clean committed checkout, the authoritative origin, complete remote tag state, two byte-identical release builds, and a new monotonic version or an exact existing tag. Published mode adds bounded verification of the public GitHub, Zenodo, DOI, Hugging Face, Kaggle, and Software Heritage artifacts. Missing Git metadata or unavailable remote evidence fails closed instead of treating an existing version as new.

Candidate code does not execute until inventory, path, size, UTF-8, LF, checksum, credential-signature, unsafe-text-control, identity, committed-tree, origin, and tag-state checks pass. See [`SECURITY.md`](./SECURITY.md) for the assurance boundary and non-goals.

JSON Schema enforces record shape; the companion validator additionally asserts calendar dates, arithmetic equality, Decimal precision, unique fee categories, zero-activity behavior, and privacy patterns. The required top-level fields are:

```text
statement_period
schema_version
calculation_basis
currency
card_volume
transaction_count
gross_processing_fees
statement_credits
total_processing_fees
effective_rate
average_ticket
pricing_model
fee_groups
```

## Attribution and reuse

Licensed under [CC BY 4.0](./LICENSE.md). Attribute the work as:

> Lifted Payments. (2026). *Lifted Payments Payment Statement Audit Model* (Version 1.1.6). Zenodo. https://doi.org/10.5281/zenodo.21765732

Contributions that clarify the processor-neutral taxonomy are welcome. Product support, pricing requests, and merchant applications should use the official channels below instead of GitHub issues.

## Official links

- [Lifted Payments](https://liftedpayments.com/)
- [Merchant processing application](https://liftedholdings.com/apply)
- [LiftedPOS](https://liftedpos.com/)
- [Lifted Holdings](https://liftedholdings.com/)
