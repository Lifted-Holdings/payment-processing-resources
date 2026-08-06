import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from decimal import Decimal, Inexact, localcontext
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema/payment-statement-audit.schema.json"
EXAMPLE_PATH = ROOT / "examples/payment-statement-audit-example.json"
VALIDATOR_PATH = ROOT / "tools/validate_audit.py"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("audit_validator", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the audit validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AuditValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not VALIDATOR_PATH.is_file():
            raise AssertionError("tools/validate_audit.py is required")
        cls.validator = load_validator_module()
        cls.valid_record = cls.validator.load_record(EXAMPLE_PATH)

    def issue_codes(self, record):
        return {issue.code for issue in self.validator.validate_record(record)}

    def mutated(self, mutator):
        record = copy.deepcopy(self.valid_record)
        mutator(record)
        return record

    def test_schema_is_valid_draft_2020_12_and_example_passes_every_rule(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual([], self.validator.validate_record(self.valid_record))

    def test_json_loader_preserves_decimals_and_rejects_duplicate_keys(self):
        self.assertIsInstance(self.valid_record["card_volume"], Decimal)
        duplicate = '{"schema_version":"1.1.0","schema_version":"1.1.0"}'
        with self.assertRaisesRegex(ValueError, "duplicate_key"):
            self.validator.loads_record(duplicate)

    def test_reversed_and_overlong_statement_periods_are_rejected(self):
        reversed_record = self.mutated(
            lambda row: row["statement_period"].update(
                {"start": "2026-07-01", "end": "2026-06-30"}
            )
        )
        overlong_record = self.mutated(
            lambda row: row["statement_period"].update(
                {"start": "2026-01-01", "end": "2026-04-01"}
            )
        )
        self.assertIn("period_order", self.issue_codes(reversed_record))
        self.assertIn("period_duration", self.issue_codes(overlong_record))

    def test_invalid_calendar_dates_are_rejected_even_when_schema_format_is_annotation(
        self,
    ):
        record = self.mutated(
            lambda row: row["statement_period"].update({"end": "2026-02-30"})
        )
        self.assertIn("schema_format", self.issue_codes(record))

    def test_fee_categories_must_be_unique_and_reconcile_to_gross_fees(self):
        duplicate = self.mutated(
            lambda row: row["fee_groups"].append(copy.deepcopy(row["fee_groups"][0]))
        )
        mismatch = self.mutated(
            lambda row: row.update({"gross_processing_fees": Decimal("2864.74")})
        )
        self.assertIn("duplicate_fee_category", self.issue_codes(duplicate))
        self.assertIn("fee_group_reconciliation", self.issue_codes(mismatch))

    def test_statement_credits_reconcile_gross_and_net_processing_fees(self):
        valid_credit = self.mutated(
            lambda row: row.update(
                {
                    "statement_credits": Decimal("10.00"),
                    "total_processing_fees": Decimal("2854.75"),
                    "effective_rate": Decimal("0.022838"),
                }
            )
        )
        invalid_credit = self.mutated(
            lambda row: row.update({"statement_credits": Decimal("10.00")})
        )
        self.assertEqual([], self.validator.validate_record(valid_credit))
        self.assertIn("net_fee_reconciliation", self.issue_codes(invalid_credit))

    def test_effective_rate_and_average_ticket_are_recomputed(self):
        wrong_rate = self.mutated(
            lambda row: row.update({"effective_rate": Decimal("2.291800")})
        )
        wrong_ticket = self.mutated(
            lambda row: row.update({"average_ticket": Decimal("67.21")})
        )
        self.assertIn("effective_rate_mismatch", self.issue_codes(wrong_rate))
        self.assertIn("average_ticket_mismatch", self.issue_codes(wrong_ticket))

    def test_decimal_math_is_independent_of_the_callers_context(self):
        with localcontext() as context:
            context.prec = 4
            context.Emax = 9
            context.Emin = -9
            context.traps[Inexact] = True
            self.assertEqual([], self.validator.validate_record(self.valid_record))

    def test_money_and_rate_precision_are_explicit(self):
        fractional_cent = self.mutated(
            lambda row: row.update({"card_volume": Decimal("125000.001")})
        )
        overprecise_rate = self.mutated(
            lambda row: row.update({"effective_rate": Decimal("0.0229181")})
        )
        self.assertIn("money_precision", self.issue_codes(fractional_cent))
        self.assertIn("rate_precision", self.issue_codes(overprecise_rate))

    def test_zero_activity_semantics_are_unambiguous(self):
        zero = self.mutated(
            lambda row: row.update(
                {
                    "card_volume": Decimal("0.00"),
                    "transaction_count": 0,
                    "gross_processing_fees": Decimal("49.00"),
                    "statement_credits": Decimal("0.00"),
                    "total_processing_fees": Decimal("49.00"),
                    "effective_rate": None,
                    "average_ticket": None,
                    # 1.2.0: a month with no settled volume has no rate to compare,
                    # so it must say so rather than being silently ranked against
                    # months that do.
                    "comparable": False,
                    "fee_groups": [{"category": "monthly", "amount": Decimal("49.00")}],
                }
            )
        )
        inconsistent = self.mutated(
            lambda row: row.update(
                {"card_volume": Decimal("0.00"), "effective_rate": None}
            )
        )
        self.assertEqual([], self.validator.validate_record(zero))
        self.assertIn("activity_pair", self.issue_codes(inconsistent))

        zero_fee = self.mutated(
            lambda row: row.update(
                {
                    "card_volume": Decimal("0.00"),
                    "transaction_count": 0,
                    "gross_processing_fees": Decimal("0.00"),
                    "statement_credits": Decimal("0.00"),
                    "total_processing_fees": Decimal("0.00"),
                    "effective_rate": None,
                    "average_ticket": None,
                    "comparable": False,
                    "fee_groups": [{"category": "other", "amount": Decimal("0.00")}],
                }
            )
        )
        self.assertEqual([], self.validator.validate_record(zero_fee))

    def test_published_half_up_rounding_is_enforced_at_exact_ties(self):
        average_ticket_tie = self.mutated(
            lambda row: row.update(
                {
                    "card_volume": Decimal("0.01"),
                    "transaction_count": 2,
                    "gross_processing_fees": Decimal("0.00"),
                    "statement_credits": Decimal("0.00"),
                    "total_processing_fees": Decimal("0.00"),
                    "effective_rate": Decimal("0.000000"),
                    "average_ticket": Decimal("0.01"),
                    "fee_groups": [{"category": "other", "amount": Decimal("0.00")}],
                }
            )
        )
        effective_rate_tie = self.mutated(
            lambda row: row.update(
                {
                    "card_volume": Decimal("20000.00"),
                    "transaction_count": 1,
                    "gross_processing_fees": Decimal("0.01"),
                    "statement_credits": Decimal("0.00"),
                    "total_processing_fees": Decimal("0.01"),
                    "effective_rate": Decimal("0.000001"),
                    "average_ticket": Decimal("20000.00"),
                    "fee_groups": [{"category": "other", "amount": Decimal("0.01")}],
                }
            )
        )
        self.assertEqual([], self.validator.validate_record(average_ticket_tie))
        self.assertEqual([], self.validator.validate_record(effective_rate_tie))

    def test_non_finite_numbers_and_unknown_fields_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "non_finite_number"):
            self.validator.loads_record('{"card_volume": NaN}')
        unknown = self.mutated(lambda row: row.update({"merchant_name": "Example"}))
        self.assertIn("schema_additionalProperties", self.issue_codes(unknown))

    def test_pathological_number_literals_fail_closed_without_decimal_crashes(self):
        hostile_literals = (
            '{"card_volume":1e-999999}',
            '{"effective_rate":1e999999}',
            '{"transaction_count":' + ("9" * 5000) + "}",
        )
        for source in hostile_literals:
            with self.subTest(source_length=len(source)):
                with self.assertRaisesRegex(ValueError, "number_range"):
                    self.validator.loads_record(source)

        direct_record = self.mutated(
            lambda row: row.update({"card_volume": Decimal("1e-999999")})
        )
        self.assertIn("number_range", self.issue_codes(direct_record))

    def test_direct_nonfinite_and_extreme_numbers_are_safe_rejections(self):
        hostile_values = (
            Decimal("Infinity"),
            Decimal("NaN"),
            Decimal("1e999999"),
            float("inf"),
            float("nan"),
            10**32,
            10**5000,
        )
        for value in hostile_values:
            with self.subTest(value_type=type(value).__name__):
                record = self.mutated(
                    lambda row, hostile=value: row.update({"card_volume": hostile})
                )
                self.assertIn("number_range", self.issue_codes(record))

    def test_oversized_and_deeply_nested_inputs_fail_closed(self):
        oversized = '{"review_notes":["' + ("x" * 1_000_000) + '"]}'
        with self.assertRaisesRegex(ValueError, "input_size"):
            self.validator.loads_record(oversized)

        nested = "{}"
        for _ in range(40):
            nested = '{"unknown":' + nested + "}"
        with self.assertRaisesRegex(ValueError, "input_depth"):
            self.validator.loads_record(nested)

    def test_malformed_nested_shapes_return_issues_instead_of_crashing(self):
        malformed_records = [
            {"statement_period": []},
            {"fee_groups": [None, [], {"amount": []}]},
            {"statement_period": {"start": [], "end": {}}},
            {"review_notes": [{"unexpected": [1, 2, 3]}]},
        ]
        for record in malformed_records:
            with self.subTest(record=record):
                issues = self.validator.validate_record(record)
                self.assertTrue(issues)

    def test_luhn_pan_and_contextual_security_data_in_notes_are_rejected(self):
        pan = self.mutated(
            lambda row: row.update(
                {"review_notes": ["Card number 4111 1111 1111 1111"]}
            )
        )
        cvv = self.mutated(lambda row: row.update({"review_notes": ["CVV 123"]}))
        self.assertIn("prohibited_payment_data", self.issue_codes(pan))
        self.assertIn("prohibited_payment_data", self.issue_codes(cvv))

    def test_truncated_pan_and_display_control_spoofing_are_rejected(self):
        prohibited_notes = (
            "Card ending in 4242",
            "PAN **** **** **** 4242",
            "Account last four 4242",
            "Visa •••• 4242",
            "Mastercard last 4 digits 5454",
            "Card ends in 1111",
            "ending in 4242",
            "last four 4242",
            "xxxx-xxxx-xxxx-4242",
            "411111 **** 11111",
            "first six 411111, last five 11111",
        )
        for note in prohibited_notes:
            with self.subTest(note=note):
                record = self.mutated(
                    lambda row, value=note: row.update({"review_notes": [value]})
                )
                self.assertIn("prohibited_payment_data", self.issue_codes(record))

        for marker in ("\u202e", "\u2066", "\u0000"):
            with self.subTest(codepoint=ord(marker)):
                record = self.mutated(
                    lambda row, value=marker: row.update(
                        {"review_notes": [f"classification {value}reversed"]}
                    )
                )
                self.assertIn("unsafe_text_control", self.issue_codes(record))

    def test_pan_screening_survives_separator_and_lookalike_obfuscation(self):
        """Each of these read as clean before NFKC folding and windowed Luhn.

        4111 1111 1111 1111 is the published synthetic test PAN; every form
        below is that same number, re-spelled the way a statement PDF, a
        spreadsheet paste, or a deliberate evasion would spell it.

        The obfuscating code points are written as escapes rather than literals
        so this file stays ASCII. The publication gate scans every declared
        release asset for format and control characters, and a literal U+200B
        here blocks the release from inside its own regression suite.
        """
        obfuscated = (
            ("non_breaking_space", "Card 4111\u00a01111\u00a01111\u00a01111 noted"),
            ("narrow_no_break_space", "Card 4111\u202f1111\u202f1111\u202f1111 noted"),
            ("thin_space", "Card 4111\u20091111\u20091111\u20091111 noted"),
            ("zero_width_space", "Card 4111\u200b1111\u200b1111\u200b1111 noted"),
            # Tab and newline are the two separators a spreadsheet or PDF paste
            # is most likely to leave behind, and are the control characters a
            # note is otherwise allowed to contain.
            ("tab_separator", "Card 4111\t1111\t1111\t1111 noted"),
            ("newline_separator", "Card 4111\n1111\n1111\n1111 noted"),
            ("dot_separator", "Card 4111.1111.1111.1111 noted"),
            ("middot_separator", "Card 4111\u00b71111\u00b71111\u00b71111 noted"),
            ("trailing_expiry_digits", "Card 41111111111111110126 noted"),
            ("leading_digits", "Ref 99994111111111111111 noted"),
            ("circled_digits", "Card \u2463" + "\u2460" * 15 + " noted"),
            ("superscript_digits", "Card \u2074\u00b9\u00b9\u00b9111111111111 noted"),
            ("fullwidth_digits", "Card \uff14\uff11\uff11\uff11111111111111 noted"),
        )
        for label, note in obfuscated:
            with self.subTest(obfuscation=label):
                record = self.mutated(
                    lambda row, value=note: row.update({"review_notes": [value]})
                )
                self.assertIn("prohibited_payment_data", self.issue_codes(record))

        # The separator and window widening must not disturb the plain forms.
        for note in ("Card 4111 1111 1111 1111", "Card 4111-1111-1111-1111"):
            with self.subTest(note=note):
                record = self.mutated(
                    lambda row, value=note: row.update({"review_notes": [value]})
                )
                self.assertIn("prohibited_payment_data", self.issue_codes(record))

    def test_privacy_screening_is_linear_in_the_length_of_the_text(self):
        """The mask quantifiers were unbounded, so backtracking was quadratic.

        Measured on the pristine tree: 61 ms at n=2000, 262 ms at n=4000 and
        1009 ms at n=8000 for an all-asterisk note, which extrapolates to hours
        for an in-limit one-megabyte record. Growth is asserted rather than a
        wall-clock bound so the test does not turn into a machine-speed probe.
        """
        screen = self.validator._string_contains_prohibited_data
        for label, filler in (
            ("mask_run", "*"),
            ("card_label_then_spaces", " "),
            ("dots", "."),
            ("digits", "7"),
            ("middots", "\u00b7"),
        ):
            timings = {}
            for size in (8_000, 64_000):
                text = filler * size
                if label == "card_label_then_spaces":
                    text = "card " + text
                # Best of three: the smallest sample is the least polluted by
                # scheduling noise on a shared machine.
                timings[size] = min(self._elapsed_ms(screen, text) for _ in range(3))
            growth = timings[64_000] / max(timings[8_000], 0.05)
            with self.subTest(filler=label, timings=timings, growth=growth):
                # Linear would be 8x for an 8x input; quadratic would be 64x.
                self.assertLess(growth, 24.0)

    @staticmethod
    def _elapsed_ms(function, argument):
        start = time.perf_counter()
        function(argument)
        return (time.perf_counter() - start) * 1000

    def test_ordinary_audit_prose_is_not_screened_as_payment_data(self):
        """An ending phrase near a calendar year is a reporting period.

        Every note below was rejected as prohibited payment data before this
        change, which pushes analysts toward deleting legitimate explanations.
        """
        permitted = (
            "Reclassified the card fee for the period ending in 2026",
            "Account reconciliation completed for the quarter ending in 2025",
            "Card present volume for the cycle ending in 2024 was restated",
            "PCI fee ends in 2026 per the acquirer schedule",
            "Visa assessments for the month ending in 2026",
            "Reviewed the account ending in 2026 fiscal year",
            "Cardholder funded fees for the period ending in 2026 were 1,240.00",
            "Dual pricing program ended in 2025; discount rate ends in 2026",
            "Interchange 1,234.56, assessments 7,890.12, markup 3,456.78",
            "Gross 125,431.90 net 2,864.75 credits 0.00 for the cycle",
            "Volume 1,000,000.00 across 14,882 transactions at 2.29 percent",
            "Monthly 49.00 PCI 19.95 equipment 35.00 gateway 10.00 total 113.95",
            "Statement dated 2026-07-31 covering 2026-07-01 through 2026-07-31",
            "Line items 1.11 2.22 3.33 4.44 5.55 6.66 7.77 8.88 9.99 10.10",
            "Rates 0.0229 0.0195 0.0201 0.0188 0.0213 0.0177 0.0230 0.0209",
            "Terminal 765 DBA 857 MID 1296297 batch 4471 lane 2",
        )
        for note in permitted:
            with self.subTest(note=note):
                record = self.mutated(
                    lambda row, value=note: row.update({"review_notes": [value]})
                )
                self.assertEqual([], self.validator.validate_record(record))

        # A calendar year is still a truncated PAN when the text names a card
        # number outright, which is the boundary the year rule turns on.
        for note in (
            "Card number ending in 2026",
            "Account number ending in 2024",
            "PAN ending in 2025",
            "last four digits 2026",
        ):
            with self.subTest(note=note):
                record = self.mutated(
                    lambda row, value=note: row.update({"review_notes": [value]})
                )
                self.assertIn("prohibited_payment_data", self.issue_codes(record))

    def test_negative_zero_is_not_a_nonnegative_amount(self):
        """JSON Schema compares -0.0 as equal to 0, so `minimum: 0` admits it.

        The arithmetic rules reconcile for the same reason, so the record was
        reported valid and only rendered as "-0.00" downstream.
        """
        for label, value in (
            ("decimal", Decimal("-0.00")),
            ("float", -0.0),
        ):
            with self.subTest(kind=label):
                record = self.mutated(
                    lambda row, amount=value: row.update({"statement_credits": amount})
                )
                self.assertIn("negative_zero", self.issue_codes(record))

        parsed = self.validator.loads_record('{"statement_credits":-0.0}')
        self.assertTrue(parsed["statement_credits"].is_signed())

        unsigned = self.mutated(
            lambda row: row.update({"statement_credits": Decimal("0.00")})
        )
        self.assertEqual([], self.validator.validate_record(unsigned))

    def test_lone_surrogates_are_rejected_before_they_break_serialization(self):
        record = self.validator.loads_record('{"review_notes":["note \\ud800 here"]}')
        mutated = self.mutated(
            lambda row: row.update({"review_notes": record["review_notes"]})
        )
        self.assertIn("unencodable_text", self.issue_codes(mutated))
        with self.assertRaises(UnicodeEncodeError):
            record["review_notes"][0].encode("utf-8")

    def test_schema_is_verified_against_its_declared_checksum(self):
        """A substituted schema must not be able to certify a record.

        checksums.txt already carried the schema digest and the validator
        already computed one, but nothing compared them, so a schema edited to
        permit merchant identity and a non-USD currency reported VALID.
        """
        self.assertEqual("verified", self.validator.schema_integrity_state())

        original = SCHEMA_PATH.read_bytes()
        substituted = original.replace(b'"const": "USD"', b'"const": "EUR"')
        self.assertNotEqual(original, substituted)
        try:
            SCHEMA_PATH.write_bytes(substituted)
            self.assertEqual("mismatch", self.validator.schema_integrity_state())
            self.assertEqual({"schema_integrity"}, self.issue_codes(self.valid_record))
        finally:
            SCHEMA_PATH.write_bytes(original)
        self.assertEqual("verified", self.validator.schema_integrity_state())
        self.assertEqual([], self.validator.validate_record(self.valid_record))

    def test_schema_verification_does_not_break_an_offline_or_packaged_copy(self):
        """Absence of checksums.txt is not failure; disagreement with it is.

        A vendored or offline copy may ship only the tool and the schema, so an
        undeclared schema still validates and the corpus report says so.
        """
        original = self.validator.CHECKSUMS_PATH
        try:
            self.validator.CHECKSUMS_PATH = ROOT / "checksums-not-present.txt"
            self.assertEqual("undeclared", self.validator.schema_integrity_state())
            self.assertEqual([], self.validator.validate_record(self.valid_record))
        finally:
            self.validator.CHECKSUMS_PATH = original
        self.assertEqual(
            "verified", self.validator.build_corpus_report(ROOT)["schema_integrity"]
        )

    def test_corpus_requires_invalid_vectors_to_emit_exactly_declared_codes(self):
        """Subset semantics let a vector emit any number of undeclared codes."""
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "release"
            shutil.copytree(ROOT, candidate)
            manifest_path = candidate / "test-vectors/manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["invalid"]["overprecise-rate.json"] = ["rate_precision"]
            manifest_path.write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
            )

            report = self.validator.build_corpus_report(candidate)
            self.assertEqual("fail", report["status"])
            self.assertIn(
                {
                    "file": "overprecise-rate.json",
                    "result": "undeclared_rule_observed",
                },
                report["unexpected"],
            )

    def test_cli_success_line_does_not_claim_privacy_rules_are_satisfied(self):
        """SECURITY.md states screening cannot prove prose is free of
        identifying information, so the success line must not claim it does."""
        result = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH), str(EXAMPLE_PATH)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(0, result.returncode)
        self.assertIn("VALID:", result.stdout)
        self.assertNotIn("privacy rules", result.stdout)
        self.assertIn("cannot establish", result.stdout)
        self.assertIn("human review", result.stdout)

    def test_identity_bank_and_credential_values_in_notes_are_rejected(self):
        prohibited_notes = (
            "Owner email is merchant@example.com",
            "Owner SSN is 123-45-6789",
            "Routing number: 021000021",
            "Password is CorrectHorseBatteryStaple",
        )
        for note in prohibited_notes:
            with self.subTest(note_kind=note.split()[0].lower()):
                record = self.mutated(
                    lambda row, value=note: row.update({"review_notes": [value]})
                )
                self.assertIn("prohibited_payment_data", self.issue_codes(record))

    def test_errors_never_echo_input_values(self):
        sensitive = "4111 1111 1111 1111"
        record = self.mutated(
            lambda row: row.update({"review_notes": [f"Card number {sensitive}"]})
        )
        report = self.validator.validation_result(record)
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn(sensitive, rendered)
        self.assertEqual("invalid", report["status"])

    def test_unknown_field_names_never_leak_through_issue_paths(self):
        sensitive_key = "password_SUPERSECRET_12345"
        record = {sensitive_key: Decimal("1e999999")}
        rendered = json.dumps(self.validator.validation_result(record), sort_keys=True)
        self.assertNotIn(sensitive_key, rendered)
        self.assertIn("/_unknown", rendered)

    def test_csv_header_matches_the_documented_flat_contract(self):
        issues = self.validator.validate_csv_template(
            ROOT / "payment-statement-audit-template.csv"
        )
        self.assertEqual([], issues)

    def test_csv_rejects_spreadsheet_formula_payloads_without_echoing_them(self):
        formula_prefixes = (
            "=1+1",
            "+1+1",
            "-1+1",
            "@SUM(1)",
            "\t=1+1",
            "\ufeff=1+1",
        )
        for marker in formula_prefixes:
            with self.subTest(prefix=marker[0]):
                with tempfile.TemporaryDirectory() as directory:
                    candidate = Path(directory) / "statement.csv"
                    source = (ROOT / "payment-statement-audit-template.csv").read_text(
                        encoding="utf-8"
                    )
                    lines = source.splitlines()
                    lines[1] = lines[1].rsplit(",", maxsplit=1)[0] + "," + marker
                    candidate.write_text("\n".join(lines) + "\n", encoding="utf-8")

                    issues = self.validator.validate_csv_template(candidate)
                    self.assertIn("csv_formula", {issue.code for issue in issues})
                    self.assertNotIn(
                        marker, json.dumps([issue.to_dict() for issue in issues])
                    )

    def test_shipped_corpus_has_broad_expected_failure_coverage(self):
        report = self.validator.build_corpus_report(ROOT)
        self.assertEqual("pass", report["status"])
        self.assertGreaterEqual(report["valid_vectors"], 2)
        self.assertGreaterEqual(report["invalid_vectors"], 12)
        self.assertEqual(0, report["unexpected_results"])
        self.assertIn("schema_sha256", report)
        self.assertIn("validator_sha256", report)

    def test_corpus_report_records_the_complete_pinned_validation_runtime(self):
        report = self.validator.build_corpus_report(ROOT)
        expected = {
            "attrs",
            "jsonschema",
            "jsonschema-specifications",
            "referencing",
            "rpds-py",
        }
        self.assertEqual(expected, set(report["dependency_versions"]))
        pins = {
            line.split("==", maxsplit=1)[0]: line.split("==", maxsplit=1)[1]
            for line in (ROOT / "requirements-validation.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line and not line.startswith("#")
        }
        self.assertEqual(report["dependency_versions"], pins)

    def test_cli_returns_nonzero_and_machine_readable_safe_output_for_invalid_input(
        self,
    ):
        invalid_path = ROOT / "test-vectors/invalid/security-data-in-note.json"
        result = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH), "--json", str(invalid_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(1, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("invalid", report["status"])
        self.assertNotIn("4111", result.stdout)

    def test_cli_uses_a_stable_value_free_code_for_unreadable_input(self):
        marker = "private-merchant-statement-do-not-echo.json"
        result = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH), "--json", str(ROOT / marker)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(1, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("input_read", report["issues"][0]["code"])
        self.assertNotIn(marker, result.stdout)

    def test_corpus_reports_a_missing_vector_without_throwing(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "release"
            shutil.copytree(ROOT, candidate)
            (candidate / "test-vectors/invalid/wrong-effective-rate.json").unlink()

            report = self.validator.build_corpus_report(candidate)
            self.assertEqual("fail", report["status"])
            self.assertGreaterEqual(report["unexpected_results"], 1)

    def test_corpus_rejects_a_missing_registered_valid_vector(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "release"
            shutil.copytree(ROOT, candidate)
            (candidate / "test-vectors/valid/standard-month.json").unlink()

            report = self.validator.build_corpus_report(candidate)
            self.assertEqual("fail", report["status"])
            self.assertIn(
                {"file": "valid-corpus", "result": "inventory_mismatch"},
                report["unexpected"],
            )

    def test_corpus_rejects_an_unregistered_invalid_vector(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "release"
            shutil.copytree(ROOT, candidate)
            shutil.copyfile(
                candidate / "test-vectors/valid/standard-month.json",
                candidate / "test-vectors/invalid/unregistered.json",
            )

            report = self.validator.build_corpus_report(candidate)
            self.assertEqual("fail", report["status"])
            self.assertIn(
                {"file": "invalid-corpus", "result": "inventory_mismatch"},
                report["unexpected"],
            )


if __name__ == "__main__":
    unittest.main()
