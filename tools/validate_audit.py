#!/usr/bin/env python3
"""Validate Lifted Payments statement-audit records without echoing input values."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker, validators


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema/payment-statement-audit.schema.json"
VALIDATOR_VERSION = "1.1.0"
VALIDATION_DEPENDENCIES = (
    "attrs",
    "jsonschema",
    "jsonschema-specifications",
    "referencing",
    "rpds-py",
)
MAX_PERIOD_DAYS = 62
MAX_INPUT_BYTES = 1_000_000
MAX_INPUT_DEPTH = 32
MONEY_QUANTUM = Decimal("0.01")
RATE_QUANTUM = Decimal("0.000001")
FEE_CATEGORIES = (
    "interchange",
    "assessments",
    "processor_markup",
    "authorization",
    "monthly",
    "pci",
    "equipment",
    "chargebacks",
    "other",
)
CSV_HEADER = (
    "schema_version",
    "calculation_basis",
    "statement_start",
    "statement_end",
    "currency",
    "card_volume",
    "transaction_count",
    "gross_processing_fees",
    "statement_credits",
    "total_processing_fees",
    "effective_rate",
    "average_ticket",
    "pricing_model",
    *FEE_CATEGORIES,
    "notes",
)

_PAN_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_AUTHENTICATION_LABEL = re.compile(
    r"\b(?:cvv2?|cvc2?|cid|security\s*code|pin(?:\s*block)?)\b",
    re.I,
)
_BANK_VALUE = re.compile(
    r"\b(?:routing|account)(?:\s*(?:number|no))?\b[^\r\n\d]{0,12}\d{4,}",
    re.I,
)
_LABELED_CREDENTIAL = re.compile(
    r"\b(?:password|api[_ -]?key|bearer|secret|access[_ -]?token)\b"
    r"\s*(?::|=|is)\s*[A-Za-z0-9_-]{3,}",
    re.I,
)
_CREDENTIAL = re.compile(
    r"\b(?:sk|pk|ghp|github_pat|hf)_[A-Za-z0-9_-]{12,}\b", re.I
)
_PROHIBITED_KEY = re.compile(
    r"(?:pan|card_?number|cvv|cvc|security_?code|pin_?block|routing_?number|"
    r"bank_?account|account_?number|ssn|password|api_?key|secret|token)",
    re.I,
)


@dataclass(frozen=True, order=True)
class ValidationIssue:
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _reject_constant(_: str) -> None:
    raise ValueError("non_finite_number: JSON numbers must be finite")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key: JSON object keys must be unique")
        result[key] = value
    return result


def loads_record(source: str) -> dict[str, Any]:
    if len(source.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("input_size: audit record exceeds the one-megabyte limit")
    try:
        result = json.loads(
            source,
            parse_float=Decimal,
            parse_int=int,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid_json: input is not valid JSON") from exc
    if not isinstance(result, dict):
        raise ValueError("invalid_root: audit record must be a JSON object")
    stack: list[tuple[Any, int]] = [(result, 1)]
    while stack:
        value, depth = stack.pop()
        if depth > MAX_INPUT_DEPTH:
            raise ValueError("input_depth: audit record is nested too deeply")
        if isinstance(value, dict):
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)
    return result


def load_record(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("input_size: audit record exceeds the one-megabyte limit")
    return loads_record(path.read_text(encoding="utf-8"))


def _schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    number_check = Draft202012Validator.TYPE_CHECKER.redefine(
        "number",
        lambda checker, instance: (
            not isinstance(instance, bool)
            and isinstance(instance, (int, float, Decimal))
        ),
    )
    decimal_validator = validators.extend(
        Draft202012Validator, type_checker=number_check
    )
    return decimal_validator(schema, format_checker=FormatChecker())


def _pointer(parts: Iterable[Any]) -> str:
    encoded = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(encoded) if encoded else "/"


def _schema_issues(record: dict[str, Any]) -> list[ValidationIssue]:
    issues = []
    for error in sorted(
        _schema_validator().iter_errors(record),
        key=lambda error: _pointer(error.absolute_path),
    ):
        validator_name = str(error.validator or "validation")
        issues.append(
            ValidationIssue(
                code=f"schema_{validator_name}",
                path=_pointer(error.absolute_path),
                message=f"Record violates the schema {validator_name} rule.",
            )
        )
    return issues


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _has_scale(value: Any, places: int) -> bool:
    number = _decimal(value)
    return number is not None and number.as_tuple().exponent >= -places


def _luhn_valid(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        value = int(char)
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _string_contains_prohibited_data(value: str) -> bool:
    if _SSN.search(value) or _EMAIL.search(value) or _CREDENTIAL.search(value):
        return True
    for candidate in _PAN_CANDIDATE.finditer(value):
        digits = re.sub(r"\D", "", candidate.group(0))
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            return True
    if (
        _AUTHENTICATION_LABEL.search(value)
        or _BANK_VALUE.search(value)
        or _LABELED_CREDENTIAL.search(value)
    ):
        return True
    return False


def _privacy_issues(value: Any, path: tuple[Any, ...] = ()) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, key)
            if _PROHIBITED_KEY.search(key):
                issues.append(
                    ValidationIssue(
                        "prohibited_field",
                        _pointer(child_path),
                        "A prohibited payment, identity, bank, or credential field is present.",
                    )
                )
            issues.extend(_privacy_issues(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(_privacy_issues(child, (*path, index)))
    elif isinstance(value, str) and _string_contains_prohibited_data(value):
        issues.append(
            ValidationIssue(
                "prohibited_payment_data",
                _pointer(path),
                "Text may contain prohibited payment, identity, bank, or credential data.",
            )
        )
    return issues


def _semantic_issues(record: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    period = record.get("statement_period")
    if isinstance(period, dict):
        try:
            start = date.fromisoformat(period["start"])
            end = date.fromisoformat(period["end"])
        except (KeyError, TypeError, ValueError):
            start = end = None
        if start is not None and end is not None:
            if end < start:
                issues.append(
                    ValidationIssue(
                        "period_order",
                        "/statement_period",
                        "Statement period end must not precede start.",
                    )
                )
            elif (end - start).days + 1 > MAX_PERIOD_DAYS:
                issues.append(
                    ValidationIssue(
                        "period_duration",
                        "/statement_period",
                        f"Statement period must cover no more than {MAX_PERIOD_DAYS} inclusive days.",
                    )
                )

    money_paths: list[tuple[str, Any]] = [
        (f"/{name}", record.get(name))
        for name in (
            "card_volume",
            "gross_processing_fees",
            "statement_credits",
            "total_processing_fees",
            "average_ticket",
        )
        if record.get(name) is not None
    ]
    groups = record.get("fee_groups")
    if isinstance(groups, list):
        for index, group in enumerate(groups):
            if isinstance(group, dict) and group.get("amount") is not None:
                money_paths.append((f"/fee_groups/{index}/amount", group["amount"]))
    for path, value in money_paths:
        if _decimal(value) is not None and not _has_scale(value, 2):
            issues.append(
                ValidationIssue(
                    "money_precision",
                    path,
                    "USD amounts must use no more than two decimal places.",
                )
            )

    rate = record.get("effective_rate")
    if rate is not None and _decimal(rate) is not None and not _has_scale(rate, 6):
        issues.append(
            ValidationIssue(
                "rate_precision",
                "/effective_rate",
                "Effective rate must use no more than six decimal places.",
            )
        )

    if isinstance(groups, list):
        categories = [
            group.get("category") for group in groups if isinstance(group, dict)
        ]
        if len(categories) != len(set(categories)):
            issues.append(
                ValidationIssue(
                    "duplicate_fee_category",
                    "/fee_groups",
                    "Each fee category may appear at most once.",
                )
            )
        amounts = [
            _decimal(group.get("amount"))
            for group in groups
            if isinstance(group, dict)
        ]
        gross = _decimal(record.get("gross_processing_fees"))
        if gross is not None and amounts and all(amount is not None for amount in amounts):
            if sum((amount for amount in amounts if amount is not None), Decimal("0")) != gross:
                issues.append(
                    ValidationIssue(
                        "fee_group_reconciliation",
                        "/gross_processing_fees",
                        "Fee-group amounts must exactly equal gross processing fees at cent precision.",
                    )
                )

    gross = _decimal(record.get("gross_processing_fees"))
    credits = _decimal(record.get("statement_credits"))
    net = _decimal(record.get("total_processing_fees"))
    if gross is not None and credits is not None and net is not None:
        if gross - credits != net:
            issues.append(
                ValidationIssue(
                    "net_fee_reconciliation",
                    "/total_processing_fees",
                    "Net processing fees must exactly equal gross fees minus statement credits.",
                )
            )

    volume = _decimal(record.get("card_volume"))
    count = record.get("transaction_count")
    count_is_integer = isinstance(count, int) and not isinstance(count, bool)
    if volume is not None and count_is_integer:
        if (volume == 0) != (count == 0):
            issues.append(
                ValidationIssue(
                    "activity_pair",
                    "/transaction_count",
                    "Card volume and settled transaction count must both be zero or both be positive.",
                )
            )

        if volume == 0:
            if rate is not None:
                issues.append(
                    ValidationIssue(
                        "zero_volume_rate",
                        "/effective_rate",
                        "Effective rate must be null when card volume is zero.",
                    )
                )
        elif net is not None:
            observed_rate = _decimal(rate)
            expected_rate = (net / volume).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)
            if observed_rate != expected_rate:
                issues.append(
                    ValidationIssue(
                        "effective_rate_mismatch",
                        "/effective_rate",
                        "Effective rate does not match net fees divided by card volume at six-decimal rounding.",
                    )
                )

        ticket = record.get("average_ticket")
        if count == 0:
            if ticket is not None:
                issues.append(
                    ValidationIssue(
                        "zero_count_ticket",
                        "/average_ticket",
                        "Average ticket must be null when transaction count is zero.",
                    )
                )
        elif volume is not None:
            observed_ticket = _decimal(ticket)
            expected_ticket = (volume / Decimal(count)).quantize(
                MONEY_QUANTUM, rounding=ROUND_HALF_UP
            )
            if observed_ticket != expected_ticket:
                issues.append(
                    ValidationIssue(
                        "average_ticket_mismatch",
                        "/average_ticket",
                        "Average ticket does not match card volume divided by transaction count at cent rounding.",
                    )
                )

    return issues


def validate_record(record: dict[str, Any]) -> list[ValidationIssue]:
    issues = _schema_issues(record)
    issues.extend(_semantic_issues(record))
    issues.extend(_privacy_issues(record))
    return sorted(set(issues))


def validation_result(record: dict[str, Any]) -> dict[str, Any]:
    issues = validate_record(record)
    return {
        "validator_version": VALIDATOR_VERSION,
        "status": "valid" if not issues else "invalid",
        "issue_count": len(issues),
        "issues": [issue.to_dict() for issue in issues],
    }


def _record_from_csv(row: dict[str, str]) -> dict[str, Any]:
    groups = []
    for category in FEE_CATEGORIES:
        amount = Decimal(row[category])
        if amount != 0:
            groups.append({"category": category, "amount": amount})
    return {
        "schema_version": row["schema_version"],
        "calculation_basis": row["calculation_basis"],
        "statement_period": {
            "start": row["statement_start"],
            "end": row["statement_end"],
        },
        "currency": row["currency"],
        "card_volume": Decimal(row["card_volume"]),
        "transaction_count": int(row["transaction_count"]),
        "gross_processing_fees": Decimal(row["gross_processing_fees"]),
        "statement_credits": Decimal(row["statement_credits"]),
        "total_processing_fees": Decimal(row["total_processing_fees"]),
        "effective_rate": (
            None if not row["effective_rate"] else Decimal(row["effective_rate"])
        ),
        "average_ticket": (
            None if not row["average_ticket"] else Decimal(row["average_ticket"])
        ),
        "pricing_model": row["pricing_model"],
        "fee_groups": groups or [{"category": "other", "amount": Decimal("0.00")}],
        "review_notes": [row["notes"]] if row["notes"] else [],
    }


def validate_csv_template(path: Path | str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    try:
        with Path(path).open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != CSV_HEADER:
                return [
                    ValidationIssue(
                        "csv_header",
                        "/",
                        "CSV columns do not match the versioned flat contract.",
                    )
                ]
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error):
        return [
            ValidationIssue("csv_read", "/", "CSV template could not be read safely.")
        ]
    if len(rows) != 1 or None in rows[0]:
        return [
            ValidationIssue(
                "csv_example_count",
                "/",
                "CSV template must contain exactly one complete synthetic example row.",
            )
        ]
    try:
        issues.extend(validate_record(_record_from_csv(rows[0])))
    except (InvalidOperation, KeyError, TypeError, ValueError):
        issues.append(
            ValidationIssue(
                "csv_value",
                "/",
                "CSV example contains an invalid typed value.",
            )
        )
    return sorted(set(issues))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_corpus_report(root: Path | str = ROOT) -> dict[str, Any]:
    root = Path(root)
    manifest_path = root / "test-vectors/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    valid_files = sorted((root / "test-vectors/valid").glob("*.json"))
    invalid_expectations = manifest.get("invalid", {})
    unexpected: list[dict[str, str]] = []

    for path in valid_files:
        try:
            issues = validate_record(load_record(path))
        except ValueError:
            issues = [ValidationIssue("parse_error", "/", "Record could not be parsed.")]
        if issues:
            unexpected.append({"file": path.name, "result": "unexpected_invalid"})

    invalid_dir = root / "test-vectors/invalid"
    for filename, expected_codes in sorted(invalid_expectations.items()):
        path = invalid_dir / filename
        try:
            observed = {issue.code for issue in validate_record(load_record(path))}
        except ValueError as exc:
            observed = {str(exc).split(":", maxsplit=1)[0]}
        if not set(expected_codes).issubset(observed):
            unexpected.append({"file": filename, "result": "expected_rule_not_observed"})

    csv_issues = validate_csv_template(root / "payment-statement-audit-template.csv")
    if csv_issues:
        unexpected.append({"file": "payment-statement-audit-template.csv", "result": "invalid"})

    return {
        "report_version": "1.0",
        "validator_version": VALIDATOR_VERSION,
        "status": "pass" if not unexpected else "fail",
        "valid_vectors": len(valid_files),
        "invalid_vectors": len(invalid_expectations),
        "unexpected_results": len(unexpected),
        "unexpected": unexpected,
        "schema_sha256": _sha256(root / "schema/payment-statement-audit.schema.json"),
        "validator_sha256": _sha256(root / "tools/validate_audit.py"),
        "jsonschema_version": package_version("jsonschema"),
        "dependency_versions": {
            name: package_version(name) for name in VALIDATION_DEPENDENCIES
        },
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a v1.1.0 Lifted Payments statement-audit JSON record."
    )
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--corpus", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.corpus:
        report = build_corpus_report(ROOT)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "pass" else 1
    if args.path is None:
        raise SystemExit("A JSON path is required unless --corpus is used.")
    try:
        report = validation_result(load_record(args.path))
    except (OSError, UnicodeError, ValueError) as exc:
        code = str(exc).split(":", maxsplit=1)[0]
        report = {
            "validator_version": VALIDATOR_VERSION,
            "status": "invalid",
            "issue_count": 1,
            "issues": [
                ValidationIssue(
                    code=code,
                    path="/",
                    message="Input could not be parsed as a safe audit record.",
                ).to_dict()
            ],
        }
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif report["status"] == "valid":
        print("VALID: record satisfies the v1.1.0 structural, accounting, and privacy rules.")
    else:
        print(f"INVALID: {report['issue_count']} rule violation(s).")
        for issue in report["issues"]:
            print(f"- {issue['code']} at {issue['path']}: {issue['message']}")
    return 0 if report["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
