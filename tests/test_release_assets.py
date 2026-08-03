import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TITLE = "Lifted Payments Payment Statement Audit Model"
CANONICAL_URL = "https://liftedpayments.com/payment-processing-statement-audit/"
REPOSITORY_URL = "https://github.com/Lifted-Holdings/payment-processing-resources"
VERSION = "1.1.7"
SCHEMA_VERSION = "1.1.0"
RELEASE_DATE = "2026-08-03"
DOI = "10.5281/zenodo.21766038"
DOI_URL = f"https://doi.org/{DOI}"
CONCEPT_DOI_URL = "https://doi.org/10.5281/zenodo.21761714"
RELEASE_URL = (
    "https://github.com/Lifted-Holdings/payment-processing-resources/"
    "releases/tag/v1.1.7"
)
HUGGING_FACE_REPO_ID = "Liftedholdings/payment-statement-audit-model"
KAGGLE_DATASET_ID = "liftedpayments/payment-statement-audit-model"
RUNTIME_ONLY_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "venv",
}


def git_metadata_is_available():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def portable_release_inventory():
    files = set()
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in RUNTIME_ONLY_DIRECTORIES for part in relative.parts):
            continue
        if path.is_file() or path.is_symlink():
            files.add(relative.as_posix())
    return files


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

        manifest = json.loads(
            (ROOT / "RELEASE-MANIFEST.json").read_text(encoding="utf-8")
        )
        self.assertEqual(RELEASE_DATE, manifest["release_date"])

        related = {
            (item["identifier"], item["relation"])
            for item in metadata["related_identifiers"]
        }
        self.assertIn((CANONICAL_URL, "isDocumentedBy"), related)
        self.assertIn((RELEASE_URL, "isSourceOf"), related)

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
        self.assertEqual(metadata["identifier"], DOI_URL)
        self.assertIn(DOI_URL, metadata["sameAs"])

    def test_citation_metadata_matches_release(self):
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")

        self.assertRegex(citation, rf'(?m)^title: "{re.escape(TITLE)}"$')
        self.assertRegex(citation, rf"(?m)^version: {re.escape(VERSION)}$")
        self.assertRegex(citation, rf"(?m)^date-released: {re.escape(RELEASE_DATE)}$")
        self.assertIn(f'url: "{CANONICAL_URL}"', citation)
        self.assertIn(f'repository-code: "{REPOSITORY_URL}"', citation)
        self.assertRegex(citation, r"(?m)^type: dataset$")
        self.assertRegex(citation, r"(?m)^license: CC-BY-4\.0$")
        self.assertRegex(citation, rf'(?m)^doi: "{re.escape(DOI)}"$')

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
        self.assertEqual(SCHEMA_VERSION, example["schema_version"])

    def test_checksums_cover_every_declared_release_file(self):
        manifest = json.loads(
            (ROOT / "RELEASE-MANIFEST.json").read_text(encoding="utf-8")
        )
        expected_files = set(manifest["files"]) - {"checksums.txt"}
        checksum_lines = (ROOT / "checksums.txt").read_text(encoding="utf-8").splitlines()
        checksums = {}
        for line in checksum_lines:
            digest, filename = re.split(r"\s+", line.strip(), maxsplit=1)
            checksums[filename] = digest

        self.assertEqual(set(checksums), expected_files)
        for filename, expected_digest in checksums.items():
            actual_digest = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
            self.assertEqual(expected_digest, actual_digest)

    def test_release_manifest_covers_every_repository_asset(self):
        manifest = json.loads(
            (ROOT / "RELEASE-MANIFEST.json").read_text(encoding="utf-8")
        )
        if git_metadata_is_available():
            result = subprocess.run(
                [
                    "git",
                    "ls-files",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            repository_files = {
                line.replace("\\", "/")
                for line in result.stdout.splitlines()
                if line
            }
        else:
            repository_files = portable_release_inventory()
        self.assertEqual(repository_files, set(manifest["files"]))

    def test_release_files_are_pinned_to_lf_by_git(self):
        manifest = json.loads(
            (ROOT / "RELEASE-MANIFEST.json").read_text(encoding="utf-8")
        )
        release_files = manifest["files"]
        if git_metadata_is_available():
            result = subprocess.run(
                ["git", "check-attr", "eol", "--", *release_files],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            observed = {
                line.split(": ", maxsplit=2)[0]: line.split(": ", maxsplit=2)[2]
                for line in result.stdout.splitlines()
            }
            self.assertEqual(observed, {filename: "lf" for filename in release_files})
        else:
            for filename in release_files:
                with self.subTest(filename=filename):
                    self.assertNotIn(b"\r\n", (ROOT / filename).read_bytes())

    def test_readme_presents_the_versioned_release_and_canonical_citation(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("## Versioned release", readme)
        self.assertIn("v1.1.7", readme)
        self.assertIn("August 3, 2026", readme)
        self.assertIn(CANONICAL_URL, readme)
        self.assertIn("CITATION.cff", readme)
        self.assertIn(DOI_URL, readme)
        self.assertNotIn("DOI_PLACEHOLDER", readme)

    def test_ai_summary_exposes_the_persistent_identifier(self):
        llms = (ROOT / "llms.txt").read_text(encoding="utf-8")

        self.assertIn(DOI_URL, llms)
        self.assertIn(
            "https://github.com/Lifted-Holdings/payment-processing-resources/releases/tag/v1.1.7",
            llms,
        )

    def test_huggingface_dataset_card_matches_release_identity(self):
        card_path = ROOT / "distribution/huggingface/README.md"
        self.assertTrue(card_path.is_file(), "Hugging Face dataset card is missing")
        card = card_path.read_text(encoding="utf-8")
        self.assertTrue(card.startswith("---\n"))
        _, frontmatter, body = card.split("---", maxsplit=2)

        self.assertRegex(frontmatter, r"(?m)^license: cc-by-4\.0$")
        self.assertRegex(
            frontmatter, rf'(?m)^pretty_name: "{re.escape(TITLE)}"$'
        )
        self.assertRegex(frontmatter, r"(?m)^- en$")
        for tag in ("tabular", "finance", "payments", "merchant-services"):
            self.assertRegex(frontmatter, rf"(?m)^- {re.escape(tag)}$")

        for identity_url in (CANONICAL_URL, DOI_URL, CONCEPT_DOI_URL, RELEASE_URL):
            self.assertIn(identity_url, body)
        self.assertIn(VERSION, body)
        self.assertIn("synthetic", body.lower())
        self.assertIn("no real merchant", body.lower())

    def test_kaggle_distribution_metadata_matches_release_identity(self):
        metadata_path = ROOT / "distribution/kaggle/dataset-metadata.json"
        description_path = ROOT / "distribution/kaggle/README.md"
        self.assertTrue(metadata_path.is_file(), "Kaggle metadata is missing")
        self.assertTrue(description_path.is_file(), "Kaggle description is missing")
        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )
        description = description_path.read_text(encoding="utf-8")

        self.assertEqual(metadata["id"], KAGGLE_DATASET_ID)
        self.assertEqual(metadata["title"], TITLE)
        self.assertIn("merchant statement", metadata["subtitle"].lower())
        self.assertIn({"name": "CC-BY-4.0"}, metadata["licenses"])
        self.assertEqual("not specified", metadata["expectedUpdateFrequency"])
        self.assertIn(DOI_URL, metadata["userSpecifiedSources"])
        self.assertIn(RELEASE_URL, metadata["userSpecifiedSources"])
        for identity_url in (CANONICAL_URL, DOI_URL, CONCEPT_DOI_URL, RELEASE_URL):
            self.assertIn(identity_url, description)
        self.assertIn(VERSION, description)
        self.assertIn("synthetic", description.lower())
        self.assertIn("no real merchant", description.lower())


if __name__ == "__main__":
    unittest.main()
