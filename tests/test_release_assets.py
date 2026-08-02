import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TITLE = "Lifted Payments Payment Statement Audit Model"
CANONICAL_URL = "https://liftedpayments.com/payment-processing-statement-audit/"
REPOSITORY_URL = "https://github.com/Lifted-Holdings/payment-processing-resources"
VERSION = "1.0.0"
RELEASE_DATE = "2026-08-02"


class ReleaseAssetTests(unittest.TestCase):
    def test_zenodo_metadata_is_complete_and_consistent(self):
        metadata = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))

        self.assertEqual(metadata["title"], TITLE)
        self.assertEqual(metadata["version"], VERSION)
        self.assertEqual(metadata["publication_date"], RELEASE_DATE)
        self.assertEqual(metadata["upload_type"], "dataset")
        self.assertEqual(metadata["access_right"], "open")
        self.assertEqual(metadata["license"], "cc-by-4.0")
        self.assertEqual(metadata["language"], "eng")
        self.assertIn(
            {"name": "Lifted Payments", "affiliation": "Lifted Holdings"},
            metadata["creators"],
        )
        self.assertGreaterEqual(len(metadata["keywords"]), 6)

        related = {
            (item["identifier"], item["relation"])
            for item in metadata["related_identifiers"]
        }
        self.assertIn((CANONICAL_URL, "isDocumentedBy"), related)
        self.assertIn((REPOSITORY_URL, "isSourceOf"), related)

    def test_codemeta_describes_the_same_dataset(self):
        metadata = json.loads((ROOT / "codemeta.json").read_text(encoding="utf-8"))

        self.assertEqual(metadata["@type"], "Dataset")
        self.assertEqual(metadata["name"], TITLE)
        self.assertEqual(metadata["version"], VERSION)
        self.assertEqual(metadata["datePublished"], RELEASE_DATE)
        self.assertEqual(metadata["license"], "https://creativecommons.org/licenses/by/4.0/")
        self.assertEqual(metadata["url"], CANONICAL_URL)
        self.assertEqual(metadata["codeRepository"], REPOSITORY_URL)
        self.assertEqual(metadata["creator"]["name"], "Lifted Payments")
        self.assertEqual(metadata["publisher"]["name"], "Lifted Holdings")
        self.assertTrue(metadata["isAccessibleForFree"])

    def test_citation_metadata_matches_release(self):
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")

        self.assertRegex(citation, rf'(?m)^title: "{re.escape(TITLE)}"$')
        self.assertRegex(citation, rf"(?m)^version: {re.escape(VERSION)}$")
        self.assertRegex(citation, rf"(?m)^date-released: {re.escape(RELEASE_DATE)}$")
        self.assertIn(f'url: "{CANONICAL_URL}"', citation)
        self.assertIn(f'repository-code: "{REPOSITORY_URL}"', citation)
        self.assertRegex(citation, r"(?m)^type: dataset$")
        self.assertRegex(citation, r"(?m)^license: CC-BY-4\.0$")

    def test_schema_and_synthetic_example_are_internally_consistent(self):
        schema = json.loads(
            (ROOT / "schema/payment-statement-audit.schema.json").read_text(
                encoding="utf-8"
            )
        )
        example = json.loads(
            (ROOT / "examples/payment-statement-audit-example.json").read_text(
                encoding="utf-8"
            )
        )

        for field in schema["required"]:
            self.assertIn(field, example)
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertAlmostEqual(
            example["effective_rate"],
            example["total_processing_fees"] / example["card_volume"],
            places=6,
        )
        self.assertTrue(
            any("synthetic" in note.lower() for note in example["review_notes"])
        )

    def test_checksums_cover_the_three_portable_data_files(self):
        expected_files = {
            "payment-statement-audit-template.csv",
            "schema/payment-statement-audit.schema.json",
            "examples/payment-statement-audit-example.json",
        }
        checksum_lines = (ROOT / "checksums.txt").read_text(encoding="utf-8").splitlines()
        checksums = {}
        for line in checksum_lines:
            digest, filename = re.split(r"\s+", line.strip(), maxsplit=1)
            checksums[filename] = digest

        self.assertEqual(set(checksums), expected_files)
        for filename, expected_digest in checksums.items():
            actual_digest = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
            self.assertEqual(expected_digest, actual_digest)

    def test_readme_presents_the_versioned_release_and_canonical_citation(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("## Versioned release", readme)
        self.assertIn("v1.0.0", readme)
        self.assertIn("August 2, 2026", readme)
        self.assertIn(CANONICAL_URL, readme)
        self.assertIn("CITATION.cff", readme)
        self.assertNotIn("DOI_PLACEHOLDER", readme)


if __name__ == "__main__":
    unittest.main()
