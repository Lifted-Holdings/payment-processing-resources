import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "tools/build_kaggle_distribution.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class KaggleDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load_module(BUILDER_PATH, "build_kaggle_distribution")

    def test_distribution_contains_exact_archive_sidecar_and_generated_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "kaggle"
            report = self.builder.build_distribution(ROOT, output)
            self.assertEqual(
                [
                    "dataset-metadata.json",
                    report["archive"],
                    "release-archive.sha256",
                ],
                report["files"],
            )
            archive = (output / report["archive"]).read_bytes()
            digest = hashlib.sha256(archive).hexdigest()
            self.assertEqual(digest, report["archive_sha256"])
            self.assertEqual(
                f"{digest}  {report['archive']}\n",
                (output / "release-archive.sha256").read_text(encoding="utf-8"),
            )
            metadata = json.loads(
                (output / "dataset-metadata.json").read_text(encoding="utf-8")
            )
            self.assertIn(digest, metadata["description"])
            self.assertNotIn(self.builder.DIGEST_PLACEHOLDER, metadata["description"])
            with zipfile.ZipFile(output / report["archive"]) as release:
                self.assertGreater(len(release.infolist()), 20)

    def test_nonempty_output_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "kaggle"
            output.mkdir()
            (output / "unexpected.txt").write_text("do not overwrite\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "output_directory_not_empty"):
                self.builder.build_distribution(ROOT, output)


if __name__ == "__main__":
    unittest.main()
