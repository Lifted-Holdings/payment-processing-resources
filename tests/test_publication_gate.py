import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "tools/publication_gate.py"
MANIFEST_PATH = ROOT / "RELEASE-MANIFEST.json"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PublicationGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GATE_PATH.is_file():
            raise AssertionError("tools/publication_gate.py is required")
        cls.gate = load_module(GATE_PATH, "publication_gate")

    def test_release_manifest_has_one_explicit_versioned_identity(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual("1.1.0", manifest["version"])
        self.assertEqual(
            "10.5281/zenodo.21761714", manifest["concept_doi"]
        )
        self.assertEqual(
            "https://liftedpayments.com/payment-processing-statement-audit/",
            manifest["canonical_url"],
        )
        self.assertTrue(manifest["source_release"].endswith("/releases/tag/v1.1.0"))
        self.assertEqual(len(manifest["files"]), len(set(manifest["files"])))
        self.assertGreaterEqual(len(manifest["files"]), 20)

    def test_gate_is_fail_closed_until_every_release_condition_is_satisfied(self):
        report = self.gate.build_publication_report(ROOT)
        self.assertIn(report["status"], {"blocked", "ready"})
        self.assertEqual(report["check_count"], len(report["checks"]))
        self.assertEqual(
            report["failed_check_count"],
            sum(check["status"] == "fail" for check in report["checks"]),
        )
        self.assertIn("corpus_validation", {check["code"] for check in report["checks"]})
        self.assertIn("dependency_lock", {check["code"] for check in report["checks"]})
        self.assertIn("utf8_text_assets", {check["code"] for check in report["checks"]})
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if manifest["version_doi"] is None:
            self.assertEqual("blocked", report["status"])
            self.assertIn(
                "version_doi_reserved",
                {check["code"] for check in report["checks"] if check["status"] == "fail"},
            )

    def test_gate_report_contains_hashes_and_no_file_contents(self):
        report = self.gate.build_publication_report(ROOT)
        rendered = json.dumps(report, sort_keys=True)
        self.assertIn("manifest_sha256", report)
        self.assertRegex(report["manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("4111 1111", rendered)
        self.assertNotIn("CVV 123", rendered)
        for check in report["checks"]:
            self.assertEqual(
                {"code", "status", "message"}, set(check), "gate checks must stay value-free"
            )

    def test_cli_exit_code_matches_release_readiness(self):
        result = subprocess.run(
            [sys.executable, str(GATE_PATH), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        report = json.loads(result.stdout)
        expected = 0 if report["status"] == "ready" else 1
        self.assertEqual(expected, result.returncode)

    def test_checksum_tool_verifies_the_exact_manifest_without_rewriting(self):
        result = subprocess.run(
            [sys.executable, "tools/update_checksums.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("checksums.txt is current\n", result.stdout)


if __name__ == "__main__":
    unittest.main()
