# Lifted Payments Payment Statement Audit Model

This is the Kaggle distribution of version **1.0.0** of the Lifted Payments Payment Statement Audit Model: a processor-neutral CSV template, JSON Schema, and synthetic example for summarizing monthly merchant payment-processing costs.

## Authoritative references

- Canonical methodology: https://liftedpayments.com/payment-processing-statement-audit/
- Version DOI: https://doi.org/10.5281/zenodo.21761715
- Concept DOI: https://doi.org/10.5281/zenodo.21761714
- Versioned source release: https://github.com/Lifted-Holdings/payment-processing-resources/releases/tag/v1.0.0
- Source repository: https://github.com/Lifted-Holdings/payment-processing-resources

## What the files do

- `payment-statement-audit-template.csv` supplies a spreadsheet-ready field header.
- `payment-statement-audit.schema.json` validates structured audit records.
- `payment-statement-audit-example.json` demonstrates a complete record using synthetic values.
- `CITATION.cff`, `codemeta.json`, and `checksums.txt` preserve citation, entity identity, and file integrity.

The effective rate is calculated as total processing fees divided by total card volume. The JSON value is stored as a decimal and multiplied by 100 only for percentage display.

## Safety and limits

The example is synthetic and describes no real merchant. This package contains no cardholder data and must never be extended with real statements, card numbers, security codes, bank details, passwords, API keys, tax IDs, or owner Social Security numbers.

The model supports consistent analysis; it does not determine legal compliance, tax treatment, network qualification, underwriting eligibility, or guaranteed savings.

## Citation and license

> Lifted Payments. (2026). *Lifted Payments Payment Statement Audit Model* (Version 1.0.0). Zenodo. https://doi.org/10.5281/zenodo.21761715

Licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
