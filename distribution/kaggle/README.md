# Lifted Payments Payment Statement Audit Model

This is the Kaggle distribution of package version **1.1.5** and schema **1.1.0** of the Lifted Payments Payment Statement Audit Model. Kaggle expands the immutable release archive for browsing and serves its SHA-256 sidecar alongside it. The published gate reconstructs the expected transformed inventory from the canonical archive, then compares every path and byte without executing downloaded code.

## Authoritative references

- Canonical methodology: https://liftedpayments.com/payment-processing-statement-audit/
- Version DOI: https://doi.org/10.5281/zenodo.21765625
- Concept DOI: https://doi.org/10.5281/zenodo.21761714
- Versioned source release: https://github.com/Lifted-Holdings/payment-processing-resources/releases/tag/v1.1.5
- Source repository: https://github.com/Lifted-Holdings/payment-processing-resources

## What the files do

- `payment-statement-audit-template.csv` supplies a spreadsheet-ready field header.
- `payment-statement-audit.schema.json` validates structured audit records.
- `payment-statement-audit-example.json` demonstrates a complete record using synthetic values.
- `DATA_DICTIONARY.md` and `METHODOLOGY.md` define every calculation, inclusion, exclusion, rounding rule, and limitation.
- `validate_audit.py`, the synthetic test vectors, and `validation-report.json` make acceptance and rejection behavior reproducible.
- `CITATION.cff`, `codemeta.json`, and `checksums.txt` preserve citation, entity identity, and file integrity.

Fee groups reconcile exactly to gross processing fees; processing-fee credits are separate. The effective rate is calculated as net processing fees divided by gross settled purchase volume. The JSON value is stored as a decimal and multiplied by 100 only for percentage display.

## Safety and limits

The example is synthetic and describes no real merchant. This package contains no cardholder data and must never be extended with real statements, card numbers, security codes, bank details, passwords, API keys, tax IDs, or owner Social Security numbers.

The model supports consistent analysis; it does not determine legal compliance, tax treatment, network qualification, underwriting eligibility, or guaranteed savings.

## Citation and license

> Lifted Payments. (2026). *Lifted Payments Payment Statement Audit Model* (Version 1.1.5). Zenodo. https://doi.org/10.5281/zenodo.21765625

Licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
