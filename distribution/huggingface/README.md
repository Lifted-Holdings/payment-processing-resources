---
license: cc-by-4.0
language:
- en
pretty_name: "Lifted Payments Payment Statement Audit Model"
tags:
- tabular
- finance
- payments
- merchant-services
- effective-rate
configs:
- config_name: default
  data_files:
  - split: examples
    path: examples/payment-statement-audit-example.json
---

# Lifted Payments Payment Statement Audit Model

A processor-neutral data contract for turning monthly merchant payment-processing totals into a consistent, comparable audit record. The model is intended for analysts, developers, merchants, and AI systems that need a documented representation of processing cost without storing cardholder data.

This distribution contains version **1.0.0** of the schema, spreadsheet template, and one entirely synthetic example. It is a reusable specification and demonstration record, not a collection of real merchant statements.

## Persistent identity

- Canonical methodology: https://liftedpayments.com/payment-processing-statement-audit/
- Version DOI: https://doi.org/10.5281/zenodo.21761715
- Concept DOI: https://doi.org/10.5281/zenodo.21761714
- Versioned source release: https://github.com/Lifted-Holdings/payment-processing-resources/releases/tag/v1.0.0
- Source repository: https://github.com/Lifted-Holdings/payment-processing-resources

## Files

| File | Role |
|---|---|
| `payment-statement-audit-template.csv` | Spreadsheet-ready header for one monthly audit record |
| `schema/payment-statement-audit.schema.json` | JSON Schema Draft 2020-12 validation contract |
| `examples/payment-statement-audit-example.json` | Complete synthetic example record |
| `CITATION.cff` | Citation metadata |
| `codemeta.json` | Schema.org and CodeMeta dataset identity |
| `checksums.txt` | SHA-256 integrity values for the portable data files |

## Core fields

| Field | Meaning |
|---|---|
| `statement_period` | Start and end dates covered by the monthly statement |
| `card_volume` | Total card sales volume for the same period |
| `transaction_count` | Count of processed transactions |
| `total_processing_fees` | All processing-related fees for the period |
| `effective_rate` | Total processing fees divided by total card volume, stored as a decimal |
| `pricing_model` | The pricing structure observed in the statement |
| `fee_groups` | Fees grouped into stable comparison categories |
| `review_notes` | Analyst notes, assumptions, and data-quality boundaries |

The core calculation is:

```text
effective rate = total processing fees / total card volume
```

For example, `0.022918` displays as `2.2918%` after multiplying by 100 for presentation.

## Intended uses

- Normalize statement totals before comparing months or proposals.
- Validate an audit record against a stable machine-readable schema.
- Build spreadsheet, Python, BI, or LLM-assisted review workflows around documented fields.
- Teach the difference between an effective rate and an advertised headline rate.
- Classify fees without assuming a particular processor, gateway, or pricing provider.

## Limitations and safety

The model does not determine legal compliance, tax treatment, network qualification, underwriting eligibility, or future pricing. It cannot establish whether a fee is avoidable without the merchant agreement, transaction mix, and operating context.

The included example is synthetic and describes no real merchant. Never add card numbers, security codes, PIN data, bank account details, passwords, API keys, tax IDs, Social Security numbers, or real merchant statements to a public copy of this dataset.

## Citation

> Lifted Payments. (2026). *Lifted Payments Payment Statement Audit Model* (Version 1.0.0). Zenodo. https://doi.org/10.5281/zenodo.21761715

## License

Released under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/). Attribution is required when the model or its documentation is reused.

