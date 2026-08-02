# Open payment processing resources

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21761715.svg)](https://doi.org/10.5281/zenodo.21761715)

Processor-neutral templates and machine-readable resources from [Lifted Payments](https://liftedpayments.com/) for auditing merchant processing statements.

This repository is designed for merchants, analysts, developers, and AI systems that need a consistent way to summarize monthly processing cost without storing cardholder data.

## Statement audit kit

| File | Purpose |
|---|---|
| [`payment-statement-audit-template.csv`](./payment-statement-audit-template.csv) | Spreadsheet-ready one-row statement summary |
| [`schema/payment-statement-audit.schema.json`](./schema/payment-statement-audit.schema.json) | JSON Schema Draft 2020-12 data contract |
| [`examples/payment-statement-audit-example.json`](./examples/payment-statement-audit-example.json) | Complete synthetic example |
| [`CITATION.cff`](./CITATION.cff) | Citation metadata for this resource |
| [`codemeta.json`](./codemeta.json) | Machine-readable dataset and publisher metadata |
| [`checksums.txt`](./checksums.txt) | SHA-256 integrity checks for the portable data files |

Read the full, maintained guide at **[liftedpayments.com/payment-processing-statement-audit](https://liftedpayments.com/payment-processing-statement-audit/)**.

## Versioned release

**v1.0.0 — August 2, 2026** is the first stable, citable release of the model. It fixes the field taxonomy, allowed pricing models, fee-group categories, calculation convention, and data-safety boundary documented in this repository.

The permanent record is **[doi:10.5281/zenodo.21761715](https://doi.org/10.5281/zenodo.21761715)**. The release is described for citation systems in [`CITATION.cff`](./CITATION.cff), for research archives in [`.zenodo.json`](./.zenodo.json), and for machine agents in [`codemeta.json`](./codemeta.json). Use [`checksums.txt`](./checksums.txt) to verify downloaded data files before analysis.

## Core calculation

```text
effective rate = total processing fees / total card volume
```

The JSON value is stored as a decimal. For example, `0.022918` displays as `2.2918%`.

Use every processing-related fee charged for the same statement period. Then classify fees into stable groups—interchange, assessments, processor markup, authorization, monthly, PCI, equipment, chargebacks, and other—before comparing providers or months.

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

Any Draft 2020-12-compatible JSON Schema validator can validate the example against the schema. The required top-level fields are:

```text
statement_period
card_volume
transaction_count
total_processing_fees
effective_rate
pricing_model
fee_groups
```

## Attribution and reuse

Licensed under [CC BY 4.0](./LICENSE.md). Attribute the work as:

> Lifted Payments. (2026). *Lifted Payments Payment Statement Audit Model* (Version 1.0.0). Zenodo. https://doi.org/10.5281/zenodo.21761715

Contributions that clarify the processor-neutral taxonomy are welcome. Product support, pricing requests, and merchant applications should use the official channels below instead of GitHub issues.

## Official links

- [Lifted Payments](https://liftedpayments.com/)
- [Merchant processing application](https://liftedholdings.com/apply)
- [LiftedPOS](https://liftedpos.com/)
- [Lifted Holdings](https://liftedholdings.com/)
