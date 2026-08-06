#!/usr/bin/env python3
"""Validate Lifted Payments statement-audit records without echoing input values."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date
from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    ROUND_HALF_UP,
    localcontext,
)
from importlib.metadata import version as package_version
from itertools import chain
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker, SchemaError, validators


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema/payment-statement-audit.schema.json"
SCHEMA_RELEASE_NAME = "schema/payment-statement-audit.schema.json"
CHECKSUMS_PATH = ROOT / "checksums.txt"
VALIDATOR_VERSION = "1.2.0"
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
MAX_NUMBER_DIGITS = 32
MAX_NUMBER_ABS_EXPONENT = 18
MAX_NUMBER_TOKEN_CHARS = 64
MONEY_QUANTUM = Decimal("0.01")
RATE_QUANTUM = Decimal("0.000001")
MONEY_MAXIMUM = Decimal("999999999999.99")
# Above this, the month is arithmetically true but uninformative: fixed fees dominate a
# trivial volume and the rate says nothing about pricing. Observed across a real portfolio
# in 17% of statements, topping out above 8000%. Such a record must not claim comparability.
RATE_COMPARABLE_MAXIMUM = Decimal("1")
FEE_CATEGORIES = (
    "interchange",
    "assessments",
    "processor_markup",
    "authorization",
    "monthly",
    "pci",
    "equipment",
    "chargebacks",
    "blended_discount",
    "other",
)
SAFE_PATH_KEYS = {
    "amex_acceptance",
    "amount",
    "average_ticket",
    "calculation_basis",
    "card_volume",
    "cardholder_funded_fees",
    "category",
    "combined",
    "comparable",
    "currency",
    "effective_rate",
    "end",
    "fee_groups",
    "gross_processing_fees",
    "merchant_borne_processing_fees",
    "net_cost_of_acceptance_rate",
    "non_recurring_fees",
    "notes",
    "pricing_model",
    "recurring_effective_rate",
    "review_notes",
    "schema_version",
    "start",
    "statement_credits",
    "statement_period",
    "total_processing_fees",
    "transaction_count",
    "volume_disclosed",
}
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
    "amex_acceptance",
    "comparable",
    "volume_disclosed",
    "cardholder_funded_fees",
    "merchant_borne_processing_fees",
    "net_cost_of_acceptance_rate",
    "non_recurring_fees",
    "recurring_effective_rate",
    "notes",
)
CSV_OPTIONAL_MONEY = (
    "cardholder_funded_fees",
    "merchant_borne_processing_fees",
    "non_recurring_fees",
)
CSV_OPTIONAL_RATE = ("net_cost_of_acceptance_rate", "recurring_effective_rate")

# --- PAN screening limits ---------------------------------------------------
# Card numbers are 13 to 19 digits. Windows are evaluated inside longer digit
# runs so a PAN does not escape the screen merely by having an expiry, an
# amount, or an invoice number butted up against it.
PAN_MIN_DIGITS = 13
PAN_MAX_DIGITS = 19
# A punctuation separator (full stop, comma, middle dot ...) joins two digit
# groups only when both are at least this long. Card masks group digits in fours, fives and
# sixes; money and rates in audit prose are 1-3 digits then exactly two cents,
# so this is what keeps "1,234.56 7,890.12 3,456.78" from being concatenated
# into an 18-digit candidate. Space and dash separators join unconditionally,
# which is exactly what the previous screen already did.
PAN_PUNCTUATION_JOIN_MIN_GROUP = 3
# A card mask is short: the longest real one, "xxxx-xxxx-xxxx-", is fifteen
# characters. Every mask quantifier below is bounded so each starting offset
# costs a constant amount of backtracking rather than an amount that grows with
# the length of the run; that bound is what makes these patterns linear instead
# of quadratic. The gap between a mask and its digits is bounded for the same
# reason -- an unbounded `\s*` re-scans the whole whitespace run once per
# backtracking combination.
MAX_MASK_RUN = 24
MAX_MASK_DIGIT_GAP = 8
_MASK_CHARACTERS = "*xX\u00b7\u2022\u2023\u2027\u25cf\u25e6"

_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_AUTHENTICATION_LABEL = re.compile(
    r"\b(?:cvv2?|cvc2?|cid|security\s*code|pin(?:\s*block)?)\b",
    re.I,
)
_BANK_VALUE = re.compile(
    r"\b(?:routing|account)(?P<qualifier>\s*(?:number|no))?\b"
    r"[^\r\n\d]{0,12}(?P<digits>\d{4,})",
    re.I,
)
# A brand or card label, then either an ending phrase or a run of mask
# characters, then the four digits that survive truncation. The mask branch is
# captured separately because a mask is unambiguous while an ending phrase is
# not: see _contains_truncated_pan_reference.
_LABELLED_TRUNCATED_PAN = re.compile(
    r"\b(?:card(?:\s*(?:number|no))?|pan|account|acct|visa|mastercard|amex|discover)\b"
    r"[^\r\n]{0,32}?(?:(?:end(?:ing|s)?(?:\s+in)?|last\s+(?:four|4)(?:\s+digits?)?)"
    rf"|(?P<mask>[{_MASK_CHARACTERS} -]{{2,{MAX_MASK_RUN}}}))"
    rf"\s{{0,{MAX_MASK_DIGIT_GAP}}}(?P<digits>\d{{4}})\b",
    re.I,
)
# An ending phrase and its trailing group, with no brand or card label at all.
_ENDING_PHRASE_DIGITS = re.compile(
    r"\b(?:end(?:ing|s)?(?:\s+in)?|last\s+(?:four|4|five|5)(?:\s+digits?)?)\b"
    r"[^\r\n\d]{0,16}(?P<digits>\d{4,5})\b",
    re.I,
)
# Mask characters adjacent to digits. A mask never appears in ordinary prose, so
# these need no further disambiguation.
_MASKED_DIGITS = re.compile(
    rf"(?<![\w\d])(?:[{_MASK_CHARACTERS}][ -]?){{4,{MAX_MASK_RUN}}}\d{{4,6}}(?!\d)|"
    rf"(?<!\d)\d{{6}}[ -]?(?:[{_MASK_CHARACTERS}][ -]?){{2,{MAX_MASK_RUN}}}\d{{4,5}}(?!\d)",
    re.I,
)
_FIRST_SIX_LAST_FOUR = re.compile(
    r"\bfirst\s+(?:six|6)(?:\s+digits?)?\b[^\r\n\d]{0,16}\d{6}\b"
    r"[^\r\n]{0,32}?\blast\s+(?:four|4|five|5)(?:\s+digits?)?\b"
    r"[^\r\n\d]{0,16}\d{4,5}\b",
    re.I,
)
_CALENDAR_YEAR = re.compile(r"(?:19|20)\d{2}")
# Tokens that name a card number outright. Only these promote a trailing
# calendar year back into a truncated-PAN reference; the bare words "card",
# "account" and "visa" appear constantly in legitimate fee prose.
_EXPLICIT_CARD_NUMBER_TOKEN = re.compile(
    r"\b(?:card\s*(?:number|no)\b|pan\b|primary\s+account\s+number\b|"
    r"account\s*(?:number|no)\b|last\s+(?:four|4)\s+digits\b)",
    re.I,
)
_LABELED_CREDENTIAL = re.compile(
    r"\b(?:password|api[_ -]?key|bearer|secret|access[_ -]?token)\b"
    r"\s*(?::|=|is)\s*[A-Za-z0-9_-]{3,}",
    re.I,
)
_CREDENTIAL = re.compile(r"\b(?:sk|pk|ghp|github_pat|hf)_[A-Za-z0-9_-]{12,}\b", re.I)
_PROHIBITED_KEY = re.compile(
    r"(?:pan|card_?number|cvv|cvc|security_?code|pin_?block|routing_?number|"
    r"bank_?account|account_?number|ssn|password|api_?key|secret|token)",
    re.I,
)
_SPREADSHEET_FORMULA = re.compile(r"^[\s\ufeff]*[=+\-@]")


@dataclass(frozen=True, order=True)
class ValidationIssue:
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _reject_constant(_: str) -> None:
    raise ValueError("non_finite_number: JSON numbers must be finite")


def _number_is_safe(value: int | float | Decimal) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        # Compare numerically instead of converting hostile giant integers to
        # text, which Python deliberately limits.
        return abs(value) < 10**MAX_NUMBER_DIGITS
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    if not number.is_finite():
        return False
    sign, digits, exponent = number.as_tuple()
    del sign
    return (
        len(digits) <= MAX_NUMBER_DIGITS
        and abs(exponent) <= MAX_NUMBER_ABS_EXPONENT
        and abs(number.adjusted()) <= MAX_NUMBER_ABS_EXPONENT
    )


def _safe_decimal_literal(source: str) -> Decimal:
    if len(source) > MAX_NUMBER_TOKEN_CHARS:
        raise ValueError("number_range: JSON number is outside safe limits")
    try:
        number = Decimal(source)
    except InvalidOperation as exc:
        raise ValueError("number_range: JSON number is outside safe limits") from exc
    if not _number_is_safe(number):
        raise ValueError("number_range: JSON number is outside safe limits")
    return number


def _safe_int_literal(source: str) -> int:
    digits = source.removeprefix("-")
    if len(digits) > MAX_NUMBER_DIGITS:
        raise ValueError("number_range: JSON number is outside safe limits")
    number = int(source)
    if not _number_is_safe(number):
        raise ValueError("number_range: JSON number is outside safe limits")
    return number


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
            parse_float=_safe_decimal_literal,
            parse_int=_safe_int_literal,
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


def _declared_checksum(name: str) -> str | None:
    """The SHA-256 that checksums.txt declares for a released file, if declared.

    Absence is deliberately not a failure. This validator is meant to run from a
    packaged, vendored or offline copy that may carry only the tool and the
    schema, and an integrity check that refuses to start without a manifest
    would break exactly those uses. Presence is authoritative, though:
    checksums.txt is the same declaration the publication gate verifies the
    whole release against, so a schema that disagrees with it has been
    substituted and must not be used to certify anything.
    """
    try:
        source = CHECKSUMS_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    for line in source.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == name:
            return parts[0]
    return None


_SCHEMA_VALIDATOR_CACHE: dict[str, Draft202012Validator] = {}


def schema_integrity_state() -> str:
    """`verified`, `undeclared`, or `mismatch` for the installed schema file."""
    declared = _declared_checksum(SCHEMA_RELEASE_NAME)
    if declared is None:
        return "undeclared"
    try:
        digest = hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()
    except OSError:
        return "mismatch"
    return "verified" if declared == digest else "mismatch"


def _schema_validator() -> Draft202012Validator:
    """Verify the schema against its declared checksum, then compile it.

    The bytes are re-read and re-hashed on every call, which costs about 60
    microseconds, so a schema swapped part way through a run cannot ride a warm
    cache. Only the compiled validator is cached, keyed by digest, because
    building one costs about 12 milliseconds and the corpus builds one per
    record.
    """
    source = SCHEMA_PATH.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    declared = _declared_checksum(SCHEMA_RELEASE_NAME)
    if declared is not None and declared != digest:
        raise ValueError(
            "schema_integrity: schema does not match its declared checksum"
        )
    cached = _SCHEMA_VALIDATOR_CACHE.get(digest)
    if cached is not None:
        return cached
    schema = json.loads(source.decode("utf-8"))
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
    validator = decimal_validator(schema, format_checker=FormatChecker())
    if len(_SCHEMA_VALIDATOR_CACHE) >= 4:
        _SCHEMA_VALIDATOR_CACHE.clear()
    _SCHEMA_VALIDATOR_CACHE[digest] = validator
    return validator


def _pointer(parts: Iterable[Any]) -> str:
    encoded = []
    for part in parts:
        if isinstance(part, int):
            segment = str(part)
        elif isinstance(part, str) and part in SAFE_PATH_KEYS:
            segment = part
        else:
            segment = "_unknown"
        encoded.append(segment.replace("~", "~0").replace("/", "~1"))
    return "/" + "/".join(encoded) if encoded else "/"


def _schema_issues(record: dict[str, Any]) -> list[ValidationIssue]:
    issues = []
    try:
        validator = _schema_validator()
    except (OSError, UnicodeError, ValueError, SchemaError):
        # Fail closed. A schema that cannot be read, parsed, or reconciled with
        # its declared checksum cannot establish that a record is valid, and a
        # substituted one would happily accept merchant identity or a non-USD
        # currency. No record is certified while the contract is in doubt.
        return [
            ValidationIssue(
                "schema_integrity",
                "/",
                "The schema could not be loaded or does not match the checksum declared for this release.",
            )
        ]
    for error in sorted(
        validator.iter_errors(record),
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
    return result if _number_is_safe(result) else None


def _money_decimal(value: Any) -> Decimal | None:
    number = _decimal(value)
    if (
        number is None
        or number < 0
        or number > MONEY_MAXIMUM
        or number.as_tuple().exponent < -2
    ):
        return None
    return number


def _signed_money_decimal(value: Any) -> Decimal | None:
    """Like _money_decimal but admits negatives, for the one field where a dual-price
    program can legitimately over-recover the merchant's processing cost."""
    number = _decimal(value)
    if (
        number is None
        or number < -MONEY_MAXIMUM
        or number > MONEY_MAXIMUM
        or number.as_tuple().exponent < -2
    ):
        return None
    return number


def _numeric_safety_issues(
    value: Any, path: tuple[Any, ...] = ()
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if isinstance(value, dict):
        for key, child in value.items():
            issues.extend(_numeric_safety_issues(child, (*path, key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(_numeric_safety_issues(child, (*path, index)))
    elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        if not _number_is_safe(value):
            issues.append(
                ValidationIssue(
                    "number_range",
                    _pointer(path),
                    "A number exceeds the validator's safe magnitude or precision limits.",
                )
            )
    return issues


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


_BREAK = -1
_FREE_SEPARATOR = -2
_PUNCTUATION_SEPARATOR = -3
_CHARACTER_ROLE_CACHE: dict[str, int] = {}


def _character_role(character: str) -> int:
    """Digit value, separator kind, or break, memoized per distinct character.

    Unicode categories are consulted rather than a literal character class so
    that every space, punctuation and format character counts as a separator.
    The previous screen tolerated only ASCII space and hyphen, which a statement
    PDF defeats by pasting U+00A0 between the digit groups.
    """
    cached = _CHARACTER_ROLE_CACHE.get(character)
    if cached is not None:
        return cached
    category = unicodedata.category(character)
    if category == "Nd":
        role = unicodedata.decimal(character)
    elif character.isspace() or category in ("Zs", "Zl", "Zp", "Pd", "Cf"):
        # `isspace` is checked as well as the Z categories so that tab, newline
        # and carriage return count as separators. Those three are exactly the
        # control characters _string_contains_unsafe_text_control permits in a
        # note, so they are the ones a spreadsheet or PDF paste can legitimately
        # leave between the digit groups of a card number.
        role = _FREE_SEPARATOR
    elif category.startswith("P"):
        role = _PUNCTUATION_SEPARATOR
    else:
        role = _BREAK
    _CHARACTER_ROLE_CACHE[character] = role
    return role


def _digit_runs(text: str) -> Iterable[list[int]]:
    """Yield the digit runs long enough to hide a PAN, in one linear pass."""
    run: list[int] = []
    group: list[int] = []
    previous_group_length = 0
    pending = 0  # 0 none, 1 free separator, 2 punctuation separator

    def close_group() -> list[int] | None:
        """Attach the finished group to the open run, or start a new run."""
        nonlocal run, group, previous_group_length, pending
        if not group:
            return None
        joins = run and (
            pending == 1
            or (
                pending == 2
                and previous_group_length >= PAN_PUNCTUATION_JOIN_MIN_GROUP
                and len(group) >= PAN_PUNCTUATION_JOIN_MIN_GROUP
            )
        )
        finished = None
        if joins:
            run.extend(group)
        else:
            finished = run
            run = list(group)
        previous_group_length = len(group)
        group = []
        pending = 0
        return finished

    def end_run() -> list[int] | None:
        nonlocal run, previous_group_length, pending
        finished = run
        run = []
        previous_group_length = 0
        pending = 0
        return finished

    def long_enough(finished: list[int] | None) -> bool:
        return bool(finished) and len(finished or ()) >= PAN_MIN_DIGITS

    for character in text:
        role = _character_role(character)
        if role >= 0:
            group.append(role)
            continue
        closed = close_group()
        if long_enough(closed):
            yield closed  # type: ignore[misc]
        # close_group leaves `pending` alone when there was no group to close,
        # so a truthy `pending` here means two separators in a row.
        if role == _BREAK or pending:
            ended = end_run()
            if long_enough(ended):
                yield ended  # type: ignore[misc]
        elif run:
            pending = 1 if role == _FREE_SEPARATOR else 2
    for finished in (close_group(), end_run()):
        if long_enough(finished):
            yield finished  # type: ignore[misc]


_DOUBLED_DIGIT = tuple(
    value * 2 - 9 if value * 2 > 9 else value * 2 for value in range(10)
)


def _run_hides_a_pan(run: list[int]) -> bool:
    """True when any 13-to-19 digit window of the run passes Luhn.

    Two running sums make each window an O(1) test: `even` doubles the
    even-indexed digits below each offset and `odd` doubles the odd-indexed
    ones, and a window [start, end) doubles exactly the positions congruent to
    `end` modulo two. Luhn itself stays the confirmation step -- a window is only
    reported after _luhn_valid agrees on the actual digits -- so the whole scan
    is linear in the length of the run instead of quadratic.

    Only the last PAN_MAX_DIGITS + 1 running sums are retained, in a ring
    buffer, because no window reaches further back than that. Keeping a full
    prefix array instead cost 84 MiB on a one-megabyte all-digit note, which
    would have traded the quadratic time defect for an allocation one.
    """
    span = PAN_MAX_DIGITS + 1
    even_history = [0] * span
    odd_history = [0] * span
    even_total = 0
    odd_total = 0
    for index, value in enumerate(run):
        doubled = _DOUBLED_DIGIT[value]
        if index % 2 == 0:
            even_total += doubled
            odd_total += value
        else:
            even_total += value
            odd_total += doubled
        end = index + 1
        even_history[end % span] = even_total
        odd_history[end % span] = odd_total
        if end < PAN_MIN_DIGITS:
            continue
        if end % 2 == 0:
            total, history = even_total, even_history
        else:
            total, history = odd_total, odd_history
        for start in range(max(0, end - PAN_MAX_DIGITS), end - PAN_MIN_DIGITS + 1):
            # history[start % span] still holds the sum at `start`: at most
            # PAN_MAX_DIGITS entries have been written since, and the buffer
            # holds one more than that.
            if (total - history[start % span]) % 10 == 0 and _luhn_valid(
                "".join(map(str, run[start:end]))
            ):
                return True
    return False


def _contains_pan(value: str) -> bool:
    return any(_run_hides_a_pan(run) for run in _digit_runs(value))


def _contains_truncated_pan_reference(value: str) -> bool:
    """Truncated-PAN references, without swallowing ordinary reporting prose.

    A mask, or a "first six ... last four" pair, is unambiguous. A bare ending
    phrase is not: "the quarter ending in 2025" is a reporting period, not a
    card. A four-digit calendar year after an ending phrase is therefore only
    treated as a truncated PAN when the text also names a card number outright,
    which is the trade the screen has to make in either direction. Non-year
    groups such as 4242, and every five-digit group, still fail.
    """
    if _MASKED_DIGITS.search(value) or _FIRST_SIX_LAST_FOUR.search(value):
        return True
    names_a_card_number: bool | None = None
    # chain, not a materialized tuple: the first prohibited match must be able
    # to return without both patterns having scanned the whole string first.
    for match in chain(
        _ENDING_PHRASE_DIGITS.finditer(value),
        _LABELLED_TRUNCATED_PAN.finditer(value),
    ):
        if match.groupdict().get("mask") is not None:
            return True
        if not _CALENDAR_YEAR.fullmatch(match.group("digits")):
            return True
        if names_a_card_number is None:
            names_a_card_number = bool(_EXPLICIT_CARD_NUMBER_TOKEN.search(value))
        if names_a_card_number:
            return True
    return False


def _contains_bank_value(value: str) -> bool:
    """Routing and account numbers, without catching the word "account" near a year.

    The label alone is far too weak on its own in this corpus: "the account
    ending in 2026 fiscal year" put a bare "account" within twelve characters of
    a four-digit number and was reported as bank data. A qualifier such as
    "number" still flags any following digits, and an unqualified label still
    flags anything that is not a bare calendar year.
    """
    for match in _BANK_VALUE.finditer(value):
        if match.group("qualifier") is not None:
            return True
        if not _CALENDAR_YEAR.fullmatch(match.group("digits")):
            return True
    return False


def _screen_text(value: str) -> bool:
    if _SSN.search(value) or _EMAIL.search(value) or _CREDENTIAL.search(value):
        return True
    if _contains_pan(value):
        return True
    if (
        _AUTHENTICATION_LABEL.search(value)
        or _contains_bank_value(value)
        or _contains_truncated_pan_reference(value)
        or _LABELED_CREDENTIAL.search(value)
    ):
        return True
    return False


def _string_contains_prohibited_data(value: str) -> bool:
    """Screen the text as written, and again after NFKC normalization.

    Text pasted out of a statement PDF routinely carries compatibility digit
    forms and non-breaking separators that NFKC folds to the ASCII shapes these
    screens are written against. Both forms are screened rather than only the
    normalized one, so normalization can only add coverage and can never drop a
    match the raw text would have produced.
    """
    if _screen_text(value):
        return True
    normalized = unicodedata.normalize("NFKC", value)
    return normalized != value and _screen_text(normalized)


def _string_contains_unsafe_text_control(value: str) -> bool:
    return any(
        character not in "\t\n\r" and unicodedata.category(character) in {"Cc", "Cf"}
        for character in value
    )


def _string_is_unencodable(value: str) -> bool:
    """True for text that cannot be written back out as UTF-8.

    json.loads turns a "\\udc80"-style escape into a lone surrogate, which
    validates against every structural rule and then raises UnicodeEncodeError
    at the moment anything serializes the record. Rejecting it here attributes
    the failure to the record instead of to whatever tries to publish it.
    """
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
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
    elif isinstance(value, str):
        if _string_contains_prohibited_data(value):
            issues.append(
                ValidationIssue(
                    "prohibited_payment_data",
                    _pointer(path),
                    "Text may contain prohibited payment, identity, bank, or credential data.",
                )
            )
        if _string_contains_unsafe_text_control(value):
            issues.append(
                ValidationIssue(
                    "unsafe_text_control",
                    _pointer(path),
                    "Text contains a control character that can obscure or reorder displayed content.",
                )
            )
        if _string_is_unencodable(value):
            issues.append(
                ValidationIssue(
                    "unencodable_text",
                    _pointer(path),
                    "Text contains a code point that cannot be encoded as UTF-8.",
                )
            )
    return issues


def _signed_zero_issues(
    value: Any, path: tuple[Any, ...] = ()
) -> list[ValidationIssue]:
    """Reject negative zero anywhere in the record.

    JSON Schema compares -0.0 as equal to 0, so the `minimum: 0` bound on every
    money and rate definition admits it unchanged, and the arithmetic rules then
    reconcile because -0.00 == 0.00. It survives only into the published output,
    where a nonnegative amount renders as "-0.00". It is never a meaningful
    value in this contract, on signed fields either, so it is refused outright.
    """
    issues: list[ValidationIssue] = []
    if isinstance(value, dict):
        for key, child in value.items():
            issues.extend(_signed_zero_issues(child, (*path, key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(_signed_zero_issues(child, (*path, index)))
    elif isinstance(value, (float, Decimal)) and not isinstance(value, bool):
        number = _decimal(value)
        if number is not None and number == 0 and number.is_signed():
            issues.append(
                ValidationIssue(
                    "negative_zero",
                    _pointer(path),
                    "A signed negative zero is not an accepted amount or rate.",
                )
            )
    return issues


def _semantic_issues(record: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = _signed_zero_issues(record)

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
            _money_decimal(group.get("amount"))
            for group in groups
            if isinstance(group, dict)
        ]
        gross = _money_decimal(record.get("gross_processing_fees"))
        if (
            gross is not None
            and amounts
            and all(amount is not None for amount in amounts)
        ):
            if (
                sum((amount for amount in amounts if amount is not None), Decimal("0"))
                != gross
            ):
                issues.append(
                    ValidationIssue(
                        "fee_group_reconciliation",
                        "/gross_processing_fees",
                        "Fee-group amounts must exactly equal gross processing fees at cent precision.",
                    )
                )

    gross = _money_decimal(record.get("gross_processing_fees"))
    credits = _money_decimal(record.get("statement_credits"))
    net = _money_decimal(record.get("total_processing_fees"))
    if gross is not None and credits is not None and net is not None:
        if gross - credits != net:
            issues.append(
                ValidationIssue(
                    "net_fee_reconciliation",
                    "/total_processing_fees",
                    "Net processing fees must exactly equal gross fees minus statement credits.",
                )
            )

    volume = _money_decimal(record.get("card_volume"))
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
            expected_rate = (net / volume).quantize(
                RATE_QUANTUM, rounding=ROUND_HALF_UP
            )
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

    issues.extend(_contract_120_issues(record, volume=volume, rate=rate))
    return issues


def _contract_120_issues(
    record: dict[str, Any], *, volume: Decimal | None, rate: Any
) -> list[ValidationIssue]:
    """Rules for the fields the 1.2.0 record contract adds.

    Every one of these exists because a real acquirer statement broke the 1.1.0 contract:
    a dual-priced account whose cardholder-funded offset had nowhere to go and could be
    read two ways for a 115x spread; dormant months emitting four-digit percentages; and
    annual charges silently inflating a single month's rate.
    """
    issues: list[ValidationIssue] = []
    for name in ("comparable", "volume_disclosed"):
        if not isinstance(record.get(name), bool):
            issues.append(
                ValidationIssue(
                    "missing_disclosure_flag",
                    f"/{name}",
                    "A 1.2.0 record must state this boolean explicitly.",
                )
            )

    # --- cardholder-funded fees -------------------------------------------------
    funded_present = "cardholder_funded_fees" in record
    if record.get("pricing_model") == "dual_pricing" and not funded_present:
        issues.append(
            ValidationIssue(
                "dual_pricing_offset_required",
                "/cardholder_funded_fees",
                "A dual_pricing record must state cardholder_funded_fees, using 0.00 with a note when none were collected.",
            )
        )

    borne = record.get("merchant_borne_processing_fees")
    acceptance = record.get("net_cost_of_acceptance_rate")
    if funded_present:
        funded = _money_decimal(record.get("cardholder_funded_fees"))
        net = _money_decimal(record.get("total_processing_fees"))
        borne_value = _signed_money_decimal(borne)
        if funded is None:
            issues.append(
                ValidationIssue(
                    "money_precision",
                    "/cardholder_funded_fees",
                    "USD amounts must use no more than two decimal places.",
                )
            )
        if borne_value is None:
            issues.append(
                ValidationIssue(
                    "missing_derived_field",
                    "/merchant_borne_processing_fees",
                    "cardholder_funded_fees requires merchant_borne_processing_fees.",
                )
            )
        if "net_cost_of_acceptance_rate" not in record:
            issues.append(
                ValidationIssue(
                    "missing_derived_field",
                    "/net_cost_of_acceptance_rate",
                    "cardholder_funded_fees requires net_cost_of_acceptance_rate.",
                )
            )
        if funded is not None and volume is not None and funded > volume:
            issues.append(
                ValidationIssue(
                    "offset_exceeds_volume",
                    "/cardholder_funded_fees",
                    "Cardholder-funded fees are settled inside card volume and cannot exceed it.",
                )
            )
        if funded is not None and net is not None and borne_value is not None:
            if net - funded != borne_value:
                issues.append(
                    ValidationIssue(
                        "merchant_borne_reconciliation",
                        "/merchant_borne_processing_fees",
                        "Merchant-borne fees must exactly equal net processing fees minus cardholder-funded fees.",
                    )
                )
            base = None if volume is None else volume - funded
            observed = _decimal(acceptance)
            if base is not None and base > 0:
                expected = (borne_value / base).quantize(
                    RATE_QUANTUM, rounding=ROUND_HALF_UP
                )
                if observed != expected:
                    issues.append(
                        ValidationIssue(
                            "acceptance_rate_mismatch",
                            "/net_cost_of_acceptance_rate",
                            "Net cost of acceptance does not match merchant-borne fees divided by merchant-retained volume.",
                        )
                    )
            elif base is not None and acceptance is not None:
                issues.append(
                    ValidationIssue(
                        "zero_base_acceptance_rate",
                        "/net_cost_of_acceptance_rate",
                        "Net cost of acceptance must be null when card volume net of cardholder-funded fees is zero.",
                    )
                )
    else:
        for name, value in (
            ("merchant_borne_processing_fees", borne),
            ("net_cost_of_acceptance_rate", acceptance),
        ):
            if name in record:
                issues.append(
                    ValidationIssue(
                        "orphan_derived_field",
                        f"/{name}",
                        "This field requires cardholder_funded_fees.",
                    )
                )
            del value

    # --- non-recurring fees -----------------------------------------------------
    if "non_recurring_fees" in record:
        annual = _money_decimal(record.get("non_recurring_fees"))
        gross = _money_decimal(record.get("gross_processing_fees"))
        net = _money_decimal(record.get("total_processing_fees"))
        recurring = record.get("recurring_effective_rate")
        if annual is None:
            issues.append(
                ValidationIssue(
                    "money_precision",
                    "/non_recurring_fees",
                    "USD amounts must use no more than two decimal places.",
                )
            )
        if "recurring_effective_rate" not in record:
            issues.append(
                ValidationIssue(
                    "missing_derived_field",
                    "/recurring_effective_rate",
                    "non_recurring_fees requires recurring_effective_rate.",
                )
            )
        if annual is not None and gross is not None and annual > gross:
            issues.append(
                ValidationIssue(
                    "non_recurring_exceeds_gross",
                    "/non_recurring_fees",
                    "Non-recurring fees are part of gross processing fees and cannot exceed them.",
                )
            )
        if annual is not None and net is not None and volume is not None:
            if volume > 0:
                expected = ((net - annual) / volume).quantize(
                    RATE_QUANTUM, rounding=ROUND_HALF_UP
                )
                if _decimal(recurring) != expected:
                    issues.append(
                        ValidationIssue(
                            "recurring_rate_mismatch",
                            "/recurring_effective_rate",
                            "Recurring effective rate does not match net fees less non-recurring fees divided by card volume.",
                        )
                    )
            elif recurring is not None:
                issues.append(
                    ValidationIssue(
                        "zero_volume_rate",
                        "/recurring_effective_rate",
                        "Recurring effective rate must be null when card volume is zero.",
                    )
                )
    elif "recurring_effective_rate" in record:
        issues.append(
            ValidationIssue(
                "orphan_derived_field",
                "/recurring_effective_rate",
                "This field requires non_recurring_fees.",
            )
        )

    # --- comparability ----------------------------------------------------------
    comparable = record.get("comparable")
    disclosed = record.get("volume_disclosed")
    if comparable is True:
        reason = None
        if disclosed is False:
            reason = "A record whose source did not disclose settled volume cannot claim comparability."
        elif volume is not None and volume == 0:
            reason = "A zero-volume record cannot claim comparability."
        else:
            observed = _decimal(rate)
            if observed is not None and observed > RATE_COMPARABLE_MAXIMUM:
                reason = "An effective rate above 100 percent is dominated by fixed fees and cannot claim comparability."
        if reason is not None:
            issues.append(ValidationIssue("not_comparable", "/comparable", reason))
    if disclosed is False and volume is not None and volume != 0:
        issues.append(
            ValidationIssue(
                "undisclosed_volume_nonzero",
                "/card_volume",
                "Card volume must be 0.00 when the source statement disclosed no settled volume total.",
            )
        )

    groups = record.get("fee_groups")
    if isinstance(groups, list):
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            # blended_discount exists only because the source fused interchange,
            # assessments and markup into one undecomposable line, so it carries the
            # same disclosure duty as an explicitly combined bucket.
            fused = (
                group.get("combined") is True
                or group.get("category") == "blended_discount"
            )
            if fused and not isinstance(group.get("notes"), str):
                issues.append(
                    ValidationIssue(
                        "combined_group_requires_note",
                        f"/fee_groups/{index}/notes",
                        "A combined fee group must name what the source statement merged into it.",
                    )
                )
    return issues


def validate_record(record: dict[str, Any]) -> list[ValidationIssue]:
    issues = _numeric_safety_issues(record)
    # jsonschema is not required to handle non-finite or million-exponent
    # Decimal instances supplied directly by Python callers. Reject those
    # before schema comparison or arithmetic can stringify or operate on them.
    if not issues:
        issues.extend(_schema_issues(record))
        # Do not inherit a host application's Decimal precision. Fifty digits
        # safely covers every bounded amount and derived value in this model.
        arithmetic_context = Context(
            prec=50,
            rounding=ROUND_HALF_UP,
            Emin=-999999,
            Emax=999999,
            traps=[InvalidOperation, DivisionByZero, Overflow],
        )
        with localcontext(arithmetic_context):
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


def _csv_boolean(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    raise ValueError("boolean column must be true or false")


def _record_from_csv(row: dict[str, str]) -> dict[str, Any]:
    groups = []
    for category in FEE_CATEGORIES:
        amount = Decimal(row[category])
        if amount != 0:
            group: dict[str, Any] = {"category": category, "amount": amount}
            # The flat template has one notes column and no per-group notes, so a
            # blended discount — which must always say what the source fused into it —
            # borrows that column rather than being unrepresentable in CSV.
            if category == "blended_discount" and row.get("notes"):
                group["notes"] = row["notes"]
            groups.append(group)
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
        **_csv_120_fields(row),
    }


def _csv_120_fields(row: dict[str, str]) -> dict[str, Any]:
    """The 1.2.0 columns, omitted entirely for a 1.1.0 row so the older flat contract
    keeps validating unchanged. A blank optional cell means absent; the literal `null`
    means present-and-null, which a nullable derived rate legitimately needs."""
    if row.get("schema_version") != "1.2.0":
        return {}
    fields: dict[str, Any] = {
        "comparable": _csv_boolean(row["comparable"]),
        "volume_disclosed": _csv_boolean(row["volume_disclosed"]),
    }
    if row.get("amex_acceptance"):
        fields["amex_acceptance"] = row["amex_acceptance"]
    for name in CSV_OPTIONAL_MONEY:
        if row.get(name):
            fields[name] = Decimal(row[name])
    for name in CSV_OPTIONAL_RATE:
        value = (row.get(name) or "").strip()
        if value.lower() == "null":
            fields[name] = None
        elif value:
            fields[name] = Decimal(value)
    return fields


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
    if any(
        _SPREADSHEET_FORMULA.match(value)
        for value in rows[0].values()
        if isinstance(value, str)
    ):
        return [
            ValidationIssue(
                "csv_formula",
                "/",
                "CSV example contains a spreadsheet-formula prefix.",
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
    valid_expectations = manifest.get("valid", [])
    valid_files = sorted((root / "test-vectors/valid").glob("*.json"))
    invalid_expectations = manifest.get("invalid", {})
    unexpected: list[dict[str, str]] = []

    valid_names = {path.name for path in valid_files}
    valid_inventory = (
        isinstance(valid_expectations, list)
        and all(isinstance(name, str) for name in valid_expectations)
        and len(valid_expectations) == len(set(valid_expectations))
        and valid_names == set(valid_expectations)
    )
    if not valid_inventory:
        unexpected.append({"file": "valid-corpus", "result": "inventory_mismatch"})

    for path in valid_files:
        try:
            issues = validate_record(load_record(path))
        except ValueError:
            issues = [
                ValidationIssue("parse_error", "/", "Record could not be parsed.")
            ]
        if issues:
            unexpected.append({"file": path.name, "result": "unexpected_invalid"})

    invalid_dir = root / "test-vectors/invalid"
    invalid_files = {path.name for path in invalid_dir.glob("*.json")}
    if invalid_files != set(invalid_expectations):
        unexpected.append({"file": "invalid-corpus", "result": "inventory_mismatch"})
    for filename, expected_codes in sorted(invalid_expectations.items()):
        path = invalid_dir / filename
        try:
            observed = {issue.code for issue in validate_record(load_record(path))}
        except (OSError, UnicodeError, ValueError) as exc:
            observed = {str(exc).split(":", maxsplit=1)[0]}
        # Exact equality, not subset containment. Under subset semantics an
        # invalid vector could emit any number of undeclared codes -- including
        # ones that only appear because the vector is malformed in a second,
        # unintended way -- and still be reported as reproducing the corpus.
        if set(expected_codes) != observed:
            missing = set(expected_codes) - observed
            unexpected.append(
                {
                    "file": filename,
                    "result": (
                        "expected_rule_not_observed"
                        if missing
                        else "undeclared_rule_observed"
                    ),
                }
            )

    csv_issues = validate_csv_template(root / "payment-statement-audit-template.csv")
    if csv_issues:
        unexpected.append(
            {"file": "payment-statement-audit-template.csv", "result": "invalid"}
        )

    return {
        "report_version": "1.0",
        "validator_version": VALIDATOR_VERSION,
        "status": "pass" if not unexpected else "fail",
        "valid_vectors": len(valid_files),
        "invalid_vectors": len(invalid_expectations),
        "unexpected_results": len(unexpected),
        "unexpected": unexpected,
        "schema_sha256": _sha256(root / "schema/payment-statement-audit.schema.json"),
        # State of the schema this validator actually loaded, so a consumer can
        # tell a checksum-verified run from one where no declaration shipped.
        "schema_integrity": schema_integrity_state(),
        "validator_sha256": _sha256(root / "tools/validate_audit.py"),
        "jsonschema_version": package_version("jsonschema"),
        "dependency_versions": {
            name: package_version(name) for name in VALIDATION_DEPENDENCIES
        },
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a schema v1.1.0 or v1.2.0 Lifted Payments statement-audit JSON record."
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
        if isinstance(exc, (OSError, UnicodeError)):
            code = "input_read"
        else:
            candidate = str(exc).split(":", maxsplit=1)[0]
            code = (
                candidate
                if candidate
                in {
                    "duplicate_key",
                    "input_depth",
                    "input_size",
                    "invalid_json",
                    "invalid_root",
                    "non_finite_number",
                    "number_range",
                }
                else "invalid_json"
            )
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
        # SECURITY.md is explicit that pattern screening "cannot prove arbitrary
        # prose contains no identifying or confidential information", so the
        # success line reports what was actually established -- the structural
        # and accounting rules passed, and no prohibited pattern matched -- and
        # does not claim the record satisfies "privacy rules".
        print(
            "VALID: record satisfies the structural, accounting, and precision rules, "
            "and no prohibited pattern was detected."
        )
        print(
            "Pattern screening cannot establish that free text is free of identifying "
            "or confidential information; human review is still required."
        )
    else:
        print(f"INVALID: {report['issue_count']} rule violation(s).")
        for issue in report["issues"]:
            print(f"- {issue['code']} at {issue['path']}: {issue['message']}")
    return 0 if report["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
