import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "tools/build_release_archive.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReproducibleReleaseArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BUILDER_PATH.is_file():
            raise AssertionError("tools/build_release_archive.py is required")
        cls.builder = load_module(BUILDER_PATH, "build_release_archive")

    def test_archive_is_byte_reproducible_and_contains_only_manifest_files(self):
        manifest = json.loads(
            (ROOT / "RELEASE-MANIFEST.json").read_text(encoding="utf-8")
        )
        first = self.builder.build_archive_bytes(ROOT, manifest)
        second = self.builder.build_archive_bytes(ROOT, manifest)

        self.assertEqual(first, second)
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())

        prefix = f"payment-processing-resources-{manifest['version']}/"
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            self.assertEqual(
                [prefix + name for name in sorted(manifest["files"], key=str.casefold)],
                [item.filename for item in members],
            )
            self.assertTrue(all(item.compress_type == zipfile.ZIP_STORED for item in members))
            self.assertEqual(1, len({item.date_time for item in members}))
            self.assertTrue(all((item.external_attr >> 16) == 0o100644 for item in members))
            for item in members:
                relative = item.filename.removeprefix(prefix)
                self.assertEqual((ROOT / relative).read_bytes(), archive.read(item))

    def test_cli_writes_archive_and_sha256_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release.zip"
            result = self.builder.main(["--output", str(output)])
            self.assertEqual(0, result)
            self.assertTrue(output.is_file())
            sidecar = output.with_name("release-archive.sha256")
            self.assertEqual(
                f"{hashlib.sha256(output.read_bytes()).hexdigest()}  {output.name}\n",
                sidecar.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
