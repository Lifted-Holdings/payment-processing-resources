import hashlib
import importlib.util
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ATTESTATION_PATH = ROOT / "tools/public_release_attestation.py"
TITLE = "Lifted Payments Payment Statement Audit Model"
CANONICAL_URL = "https://liftedpayments.com/payment-processing-statement-audit/"
SOURCE_REPOSITORY = "https://github.com/Lifted-Holdings/payment-processing-resources"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeTransport:
    def __init__(self, *, json_values, byte_values, final_urls):
        self.json_values = json_values
        self.byte_values = byte_values
        self.final_urls = final_urls

    def get_json(self, url, *, max_bytes):
        del max_bytes
        return self.json_values[url]

    def get_json_value(self, url, *, max_bytes):
        del max_bytes
        return self.json_values[url]

    def get_bytes(self, url, *, max_bytes):
        value = self.byte_values[url]
        if len(value) > max_bytes:
            raise ValueError("response_too_large")
        return value

    def post_bytes(self, url, document, *, max_bytes):
        value = self.byte_values[(url, tuple(sorted(document.items())))]
        if len(value) > max_bytes:
            raise ValueError("response_too_large")
        return value

    def resolve(self, url, *, max_bytes):
        del max_bytes
        return self.final_urls[url]


class PublicReleaseAttestationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ATTESTATION_PATH.is_file():
            raise AssertionError("tools/public_release_attestation.py is required")
        cls.attestation = load_module(ATTESTATION_PATH, "public_release_attestation")

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "README.md").write_text("verified release\n", encoding="utf-8")
        huggingface_readme = self.root / "distribution/huggingface/README.md"
        huggingface_readme.parent.mkdir(parents=True)
        huggingface_readme.write_bytes(
            (ROOT / "distribution/huggingface/README.md").read_bytes()
        )
        self.manifest = {
            "title": TITLE,
            "version": "1.1.6",
            "release_date": "2026-08-02",
            "version_doi": "10.5281/zenodo.99999999",
            "concept_doi": "10.5281/zenodo.21761714",
            "canonical_url": CANONICAL_URL,
            "source_release": f"{SOURCE_REPOSITORY}/releases/tag/v1.1.6",
            "license": "CC-BY-4.0",
            "files": ["README.md"],
        }

    def tearDown(self):
        self.temporary_directory.cleanup()

    def make_zip(self, members=None):
        if members is None:
            return self.attestation.build_archive_bytes(self.root, self.manifest)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, value in members.items():
                archive.writestr(f"payment-processing-resources-1.1.6/{name}", value)
        return output.getvalue()

    def make_transport(self, archive=None):
        archive = archive or self.make_zip()
        digest = hashlib.sha256(archive).hexdigest()
        zip_name = "lifted-payments-statement-audit-model-v1.1.6.zip"
        sidecar_name = "release-archive.sha256"
        github_zip = (
            f"https://github.com/Lifted-Holdings/payment-processing-resources/"
            f"releases/download/v1.1.6/{zip_name}"
        )
        github_sidecar = (
            "https://github.com/Lifted-Holdings/payment-processing-resources/"
            f"releases/download/v1.1.6/{sidecar_name}"
        )
        zenodo_zip = (
            f"https://zenodo.org/api/records/99999999/files/{zip_name}/content"
        )
        zenodo_sidecar = (
            f"https://zenodo.org/api/records/99999999/files/{sidecar_name}/content"
        )
        huggingface_prefix = (
            "https://huggingface.co/datasets/Liftedholdings/"
            f"payment-statement-audit-model/resolve/{'a' * 40}/"
        )
        huggingface_zip = huggingface_prefix + zip_name
        huggingface_sidecar = huggingface_prefix + sidecar_name
        huggingface_readme = huggingface_prefix + "README.md"
        kaggle_download = (
            "https://api.kaggle.com/v1/"
            "datasets.DatasetApiService/DownloadDataset"
        )
        kaggle_view = (
            "https://www.kaggle.com/api/v1/datasets/view/"
            "liftedpayments/payment-statement-audit-model"
        )
        kaggle_version = 3
        sidecar = f"{digest}  {zip_name}\n".encode()
        kaggle_bundle_buffer = io.BytesIO()
        with zipfile.ZipFile(
            kaggle_bundle_buffer, "w", compression=zipfile.ZIP_STORED
        ) as kaggle_bundle:
            kaggle_bundle.writestr(sidecar_name, sidecar)
            with zipfile.ZipFile(io.BytesIO(archive)) as release_archive:
                for member in release_archive.infolist():
                    if member.is_dir():
                        continue
                    kaggle_bundle.writestr(
                        f"{zip_name.removesuffix('.zip')}/{member.filename}",
                        release_archive.read(member),
                    )
        kaggle_bundle = kaggle_bundle_buffer.getvalue()
        github = {
            "tag_name": "v1.1.6",
            "draft": False,
            "prerelease": False,
            "html_url": self.manifest["source_release"],
            "assets": [
                {
                    "name": zip_name,
                    "size": len(archive),
                    "digest": f"sha256:{digest}",
                    "browser_download_url": github_zip,
                },
                {
                    "name": sidecar_name,
                    "size": len(sidecar),
                    "digest": f"sha256:{hashlib.sha256(sidecar).hexdigest()}",
                    "browser_download_url": github_sidecar,
                },
            ],
        }
        zenodo = {
            "id": 99999999,
            "doi": self.manifest["version_doi"],
            "conceptdoi": self.manifest["concept_doi"],
            "metadata": {
                "title": TITLE,
                "publication_date": "2026-08-02",
                "version": "1.1.6",
                "license": {"id": "cc-by-4.0"},
                "related_identifiers": [
                    {"identifier": CANONICAL_URL, "relation": "isDocumentedBy"},
                    {
                        "identifier": self.manifest["source_release"],
                        "relation": "isSourceOf",
                    },
                ],
            },
            "files": [
                {
                    "key": zip_name,
                    "size": len(archive),
                    "checksum": f"md5:{hashlib.md5(archive).hexdigest()}",
                    "links": {"self": zenodo_zip},
                },
                {
                    "key": sidecar_name,
                    "size": len(sidecar),
                    "checksum": f"md5:{hashlib.md5(sidecar).hexdigest()}",
                    "links": {"self": zenodo_sidecar},
                },
            ],
        }
        huggingface = {
            "id": "Liftedholdings/payment-statement-audit-model",
            "sha": "a" * 40,
            "private": False,
            "disabled": False,
            "gated": False,
            "siblings": [
                {"rfilename": "README.md"},
                {"rfilename": zip_name},
                {"rfilename": sidecar_name},
            ],
        }
        snapshot_id = "c" * 40
        release_id = "d" * 40
        expected_commit = "b" * 40
        software_heritage_visit = (
            "https://archive.softwareheritage.org/api/1/origin/"
            "https%3A%2F%2Fgithub.com%2FLifted-Holdings%2F"
            "payment-processing-resources/visit/latest/?require_snapshot=true"
        )
        software_heritage_snapshot = (
            f"https://archive.softwareheritage.org/api/1/snapshot/{snapshot_id}/"
        )
        software_heritage_release = (
            f"https://archive.softwareheritage.org/api/1/release/{release_id}/"
        )
        transport = FakeTransport(
            json_values={
                "https://api.github.com/repos/Lifted-Holdings/payment-processing-resources/releases/tags/v1.1.6": github,
                "https://zenodo.org/api/records/99999999": zenodo,
                "https://huggingface.co/api/datasets/Liftedholdings/payment-statement-audit-model": huggingface,
                kaggle_view: {
                    "ref": "liftedpayments/payment-statement-audit-model",
                    "title": TITLE,
                    "subtitle": "A processor-neutral statement-audit model with reproducible validation",
                    "licenseName": "Attribution 4.0 International (CC BY 4.0)",
                    "isPrivate": False,
                    "currentVersionNumber": kaggle_version,
                    "description": (
                        "Version 1.1.6. "
                        f"{self.manifest['version_doi']} "
                        f"{self.manifest['source_release']} "
                        f"{digest}"
                    ),
                },
                software_heritage_visit: {
                    "origin": SOURCE_REPOSITORY,
                    "status": "full",
                    "snapshot": snapshot_id,
                },
                software_heritage_snapshot: {
                    "id": snapshot_id,
                    "branches": {
                        "refs/heads/main": {
                            "target": expected_commit,
                            "target_type": "revision",
                        },
                        "refs/tags/v1.1.6": {
                            "target": release_id,
                            "target_type": "release",
                        },
                    },
                },
                software_heritage_release: {
                    "id": release_id,
                    "name": "v1.1.6",
                    "target": expected_commit,
                    "target_type": "revision",
                },
            },
            byte_values={
                github_zip: archive,
                github_sidecar: sidecar,
                zenodo_zip: archive,
                zenodo_sidecar: sidecar,
                huggingface_zip: archive,
                huggingface_sidecar: sidecar,
                huggingface_readme: (ROOT / "distribution/huggingface/README.md").read_bytes(),
                (
                    kaggle_download,
                    tuple(
                        sorted(
                            {
                                "ownerSlug": "liftedpayments",
                                "datasetSlug": "payment-statement-audit-model",
                                "datasetVersionNumber": kaggle_version,
                            }.items()
                        )
                    ),
                ): kaggle_bundle,
            },
            final_urls={
                "https://doi.org/10.5281/zenodo.99999999": "https://zenodo.org/records/99999999"
            },
        )
        return transport, digest, expected_commit, snapshot_id

    def test_matching_public_archives_and_catalogs_verify(self):
        transport, digest, expected_commit, snapshot_id = self.make_transport()

        result = self.attestation.attest_public_release(
            self.root,
            self.manifest,
            transport=transport,
            expected_commit=expected_commit,
        )

        self.assertTrue(result.verified, result.failure_codes)
        self.assertEqual((), result.failure_codes)
        self.assertEqual(digest, result.archive_sha256)
        self.assertEqual(snapshot_id, result.software_heritage_snapshot)
        self.assertEqual(3, result.kaggle_version)

    def test_stale_kaggle_view_blocks_attestation(self):
        transport, _, expected_commit, _ = self.make_transport()
        kaggle_view = next(
            url for url in transport.json_values if "kaggle.com/api/v1/datasets/view" in url
        )
        transport.json_values[kaggle_view]["description"] = "Version 1.1.1"

        result = self.attestation.attest_public_release(
            self.root,
            self.manifest,
            transport=transport,
            expected_commit=expected_commit,
        )

        self.assertFalse(result.verified)
        self.assertIn("kaggle_release_invalid", result.failure_codes)

    def test_extra_zenodo_or_huggingface_files_block_attestation(self):
        for provider in ("zenodo", "huggingface"):
            with self.subTest(provider=provider):
                transport, _, expected_commit, _ = self.make_transport()
                if provider == "zenodo":
                    record = transport.json_values[
                        "https://zenodo.org/api/records/99999999"
                    ]
                    record["files"].append({"key": "untracked.exe"})
                    expected_failure = "zenodo_release_invalid"
                else:
                    dataset = transport.json_values[
                        "https://huggingface.co/api/datasets/"
                        "Liftedholdings/payment-statement-audit-model"
                    ]
                    dataset["siblings"].append({"rfilename": "untracked.exe"})
                    expected_failure = "huggingface_release_invalid"

                result = self.attestation.attest_public_release(
                    self.root,
                    self.manifest,
                    transport=transport,
                    expected_commit=expected_commit,
                )
                self.assertFalse(result.verified)
                self.assertIn(expected_failure, result.failure_codes)

    def test_corrupt_deflated_kaggle_bundle_fails_closed(self):
        zip_name = "lifted-payments-statement-audit-model-v1.1.6.zip"
        sidecar_name = "release-archive.sha256"
        archive = self.make_zip()
        sidecar = b"0" * 64 + b"  " + zip_name.encode() + b"\n"
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(zip_name, archive)
            bundle.writestr(sidecar_name, sidecar)
        corrupted = bytearray(output.getvalue())
        with zipfile.ZipFile(io.BytesIO(corrupted)) as bundle:
            first = bundle.infolist()[0]
            offset = first.header_offset + 30 + len(first.filename.encode()) + len(first.extra)
        corrupted[offset + 2] ^= 0xFF

        self.assertFalse(
            self.attestation._kaggle_bundle_matches(
                bytes(corrupted), archive, sidecar, zip_name, sidecar_name
            )
        )

    def test_intact_kaggle_archive_and_sidecar_are_accepted(self):
        zip_name = "lifted-payments-statement-audit-model-v1.1.6.zip"
        sidecar_name = "release-archive.sha256"
        archive = self.make_zip()
        sidecar = f"{hashlib.sha256(archive).hexdigest()}  {zip_name}\n".encode()
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as bundle:
            bundle.writestr(zip_name, archive)
            bundle.writestr(sidecar_name, sidecar)

        self.assertTrue(
            self.attestation._kaggle_bundle_matches(
                output.getvalue(), archive, sidecar, zip_name, sidecar_name
            )
        )

    def test_kaggle_platform_expansion_rejects_tree_drift(self):
        zip_name = "lifted-payments-statement-audit-model-v1.1.6.zip"
        sidecar_name = "release-archive.sha256"
        archive = self.make_zip()
        sidecar = f"{hashlib.sha256(archive).hexdigest()}  {zip_name}\n".encode()
        prefix = zip_name.removesuffix(".zip") + "/"
        with zipfile.ZipFile(io.BytesIO(archive)) as release:
            expanded = {
                prefix + info.filename: release.read(info)
                for info in release.infolist()
                if not info.is_dir()
            }
        expanded[sidecar_name] = sidecar
        first_release_name = next(name for name in expanded if name != sidecar_name)
        cases = {
            "extra": {**expanded, prefix + "unexpected.txt": b"unexpected"},
            "missing": {
                name: value
                for name, value in expanded.items()
                if name != first_release_name
            },
            "changed": {**expanded, first_release_name: b"changed"},
            "case_alias": {
                **expanded,
                first_release_name.upper(): expanded[first_release_name],
            },
            "traversal": {**expanded, prefix + "../outside.txt": b"outside"},
            "backslash": {**expanded, prefix + "bad\\path.txt": b"bad"},
            "directory": {**expanded, prefix + "unexpected/": b""},
        }
        for label, members in cases.items():
            with self.subTest(label=label):
                output = io.BytesIO()
                with zipfile.ZipFile(
                    output, "w", compression=zipfile.ZIP_DEFLATED
                ) as bundle:
                    for name, value in members.items():
                        bundle.writestr(name, value)
                self.assertFalse(
                    self.attestation._kaggle_bundle_matches(
                        output.getvalue(), archive, sidecar, zip_name, sidecar_name
                    )
                )

    def test_digest_mismatch_blocks_attestation(self):
        transport, _, expected_commit, _ = self.make_transport()
        github_url = next(
            url for url in transport.byte_values if url.startswith("https://github.com")
            and url.endswith(".zip")
        )
        transport.byte_values[github_url] += b"tampered"

        result = self.attestation.attest_public_release(
            self.root,
            self.manifest,
            transport=transport,
            expected_commit=expected_commit,
        )

        self.assertFalse(result.verified)
        self.assertIn("github_archive_digest_mismatch", result.failure_codes)

    def test_zip_traversal_and_duplicate_aliases_are_rejected(self):
        cases = {
            "traversal": {
                "README.md": b"verified release\n",
                "../outside.txt": b"outside",
            },
            "case_alias": {
                "README.md": b"verified release\n",
                "readme.md": b"alias",
            },
        }
        for name, members in cases.items():
            with self.subTest(name=name):
                archive = self.make_zip(members)
                transport, _, expected_commit, _ = self.make_transport(archive)
                result = self.attestation.attest_public_release(
                    self.root,
                    self.manifest,
                    transport=transport,
                    expected_commit=expected_commit,
                )
                self.assertFalse(result.verified)
                self.assertIn("release_archive_invalid", result.failure_codes)

    def test_http_transport_rejects_untrusted_or_insecure_hosts_before_request(self):
        transport = self.attestation.HttpTransport()
        for url in (
            "http://github.com/Lifted-Holdings/example",
            "https://github.com.evil.invalid/payload",
            "https://evil.invalid/payload",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    transport.get_bytes(url, max_bytes=1024)

    def test_doi_resolution_requests_the_human_html_landing_page(self):
        observed = {}

        class Response:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def geturl(self):
                return "https://zenodo.org/records/99999999"

            def read(self, size):
                del size
                return b""

        class Opener:
            def open(self, request, timeout):
                del timeout
                observed["accept"] = request.headers["Accept"]
                return Response()

        transport = self.attestation.HttpTransport()
        transport._opener = Opener()

        resolved = transport.resolve(
            "https://doi.org/10.5281/zenodo.99999999", max_bytes=1024
        )

        self.assertEqual("https://zenodo.org/records/99999999", resolved)
        self.assertEqual("text/html, application/xhtml+xml", observed["accept"])


if __name__ == "__main__":
    unittest.main()
