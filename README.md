# Open payment processing resources

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21763617.svg)](https://doi.org/10.5281/zenodo.21763617)

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

**v1.1.2 — August 2, 2026** is the hardened, citable release candidate of the package and validator. It preserves the schema 1.1.0 record contract while adding complete tree inventory, bounded assets, behavioral regression execution, spreadsheet-formula rejection, trusted release identity checks, and immutable-tag protection. Prior release files remain immutable.

The reserved version DOI is **[doi:10.5281/zenodo.21763617](https://doi.org/10.5281/zenodo.21763617)**; the all-versions concept DOI is **[doi:10.5281/zenodo.21761714](https://doi.org/10.5281/zenodo.21761714)**; and the source release target is **[GitHub v1.1.2](https://github.com/Lifted-Holdings/payment-processing-resources/releases/tag/v1.1.2)**. The DOI is registered only when the Zenodo draft is published. The release is described for citation systems in [`CITATION.cff`](./CITATION.cff), for research archives in [`.zenodo.json`](./.zenodo.json), and for machine agents in [`codemeta.json`](./codemeta.json). Use [`checksums.txt`](./checksums.txt) to verify every release file before analysis.

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
python tools/publication_gate.py
```

The first command validates one record without echoing submitted values in an error. The corpus command must accept 2 valid synthetic vectors and reject 14 invalid vectors for their expected rules. The publication gate is fail-closed: it also requires aligned package/schema/DOI metadata, a complete manifest-to-tree inventory, bounded text assets, the candidate validator's behavioral regression suite, SHA-256 coverage, path containment, LF portability, full-release credential screening, immutable-tag protection, and a fresh validation report.

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

> Lifted Payments. (2026). *Lifted Payments Payment Statement Audit Model* (Version 1.1.2). Zenodo. https://doi.org/10.5281/zenodo.21763617

Contributions that clarify the processor-neutral taxonomy are welcome. Product support, pricing requests, and merchant applications should use the official channels below instead of GitHub issues.

## Official links

- [Lifted Payments](https://liftedpayments.com/)
- [Merchant processing application](https://liftedholdings.com/apply)
- [LiftedPOS](https://liftedpos.com/)
- [Lifted Holdings](https://liftedholdings.com/)
