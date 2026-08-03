#!/usr/bin/env python3
"""Bounded, non-executing attestation of public statement-audit release bytes."""

from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import sys
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from build_release_archive import build_archive_bytes  # noqa: E402


TITLE = "Lifted Payments Payment Statement Audit Model"
CANONICAL_URL = "https://liftedpayments.com/payment-processing-statement-audit/"
SOURCE_REPOSITORY = "https://github.com/Lifted-Holdings/payment-processing-resources"
HUGGINGFACE_REPOSITORY = "Liftedholdings/payment-statement-audit-model"
KAGGLE_REPOSITORY = "liftedpayments/payment-statement-audit-model"
HTTP_TIMEOUT_SECONDS = 5
MAX_JSON_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024
MAX_RELEASE_FILE_COUNT = 256
MAX_RELEASE_FILE_BYTES = 5 * 1024 * 1024
MAX_RELEASE_TOTAL_BYTES = 8 * 1024 * 1024
DOI_PATTERN = re.compile(r"^10\.5281/zenodo\.(\d+)$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
OBJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
EXACT_HOSTS = {
    "api.github.com",
    "api.kaggle.com",
    "archive.softwareheritage.org",
    "doi.org",
    "github.com",
    "huggingface.co",
    "storage.googleapis.com",
    "www.kaggle.com",
    "zenodo.org",
}
TRUSTED_HOST_SUFFIXES = (
    ".githubusercontent.com",
    ".hf.co",
    ".huggingface.co",
    ".xethub.hf.co",
)


@dataclass(frozen=True)
class AttestationResult:
    verified: bool
    failure_codes: tuple[str, ...]
    archive_sha256: str | None
    github_release_url: str | None
    zenodo_record_url: str | None
    huggingface_commit: str | None
    kaggle_version: int | None
    software_heritage_snapshot: str | None


def _validate_url(url: str) -> str:
    if not isinstance(url, str):
        raise ValueError("url_invalid")
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").casefold()
    trusted = hostname in EXACT_HOSTS or any(
        hostname.endswith(suffix) for suffix in TRUSTED_HOST_SUFFIXES
    )
    if (
        parsed.scheme != "https"
        or not trusted
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.fragment
    ):
        raise ValueError("url_untrusted")
    return url


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpTransport:
    """HTTPS-only transport with redirect revalidation and response byte caps."""

    def __init__(self):
        self._opener = build_opener(_SafeRedirectHandler())

    def _open(
        self,
        url: str,
        *,
        max_bytes: int,
        accept: str = "application/json, application/octet-stream;q=0.9, */*;q=0.1",
        data: bytes | None = None,
        content_type: str | None = None,
    ) -> tuple[bytes, str]:
        _validate_url(url)
        if not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("response_limit_invalid")
        headers = {
                "Accept": accept,
                "User-Agent": "LiftedPayments-release-attestation/1.0",
            }
        if content_type is not None:
            headers["Content-Type"] = content_type
        request = Request(url, data=data, headers=headers)
        with self._opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            final_url = _validate_url(response.geturl())
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > max_bytes:
                raise ValueError("response_too_large")
            payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError("response_too_large")
        return payload, final_url

    def get_bytes(self, url: str, *, max_bytes: int) -> bytes:
        return self._open(url, max_bytes=max_bytes)[0]

    def get_json(self, url: str, *, max_bytes: int) -> dict[str, Any]:
        document = self.get_json_value(url, max_bytes=max_bytes)
        if not isinstance(document, dict):
            raise ValueError("json_root_invalid")
        return document

    def get_json_value(self, url: str, *, max_bytes: int) -> Any:
        payload = self.get_bytes(url, max_bytes=max_bytes)
        return json.loads(payload.decode("utf-8", errors="strict"))

    def post_bytes(
        self, url: str, document: dict[str, Any], *, max_bytes: int
    ) -> bytes:
        if not isinstance(document, dict):
            raise ValueError("json_request_invalid")
        payload = json.dumps(
            document, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return self._open(
            url,
            max_bytes=max_bytes,
            data=payload,
            content_type="application/json",
        )[0]

    def resolve(self, url: str, *, max_bytes: int) -> str:
        return self._open(
            url,
            max_bytes=max_bytes,
            accept="text/html, application/xhtml+xml",
        )[1]


def _valid_member_name(name: str, prefix: str) -> str | None:
    if not isinstance(name, str) or "\\" in name or "\x00" in name:
        return None
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not name.startswith(prefix):
        return None
    relative = name[len(prefix) :]
    if not relative or relative.endswith("/"):
        return None
    relative_path = PurePosixPath(relative)
    if relative_path.as_posix() != relative or ".." in relative_path.parts:
        return None
    return relative


def _archive_matches_release(
    root: Path, manifest: dict[str, Any], archive_bytes: bytes
) -> bool:
    names = manifest.get("files")
    version = manifest.get("version")
    if (
        not isinstance(names, list)
        or not all(isinstance(name, str) and name for name in names)
        or len(names) != len(set(names))
        or not isinstance(version, str)
    ):
        return False
    prefix = f"payment-processing-resources-{version}/"
    observed: dict[str, zipfile.ZipInfo] = {}
    folded: set[str] = set()
    total_bytes = 0
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            if len(archive.infolist()) > MAX_RELEASE_FILE_COUNT + 32:
                return False
            for info in archive.infolist():
                if info.is_dir():
                    continue
                relative = _valid_member_name(info.filename, prefix)
                if relative is None or relative in observed or relative.casefold() in folded:
                    return False
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    return False
                if info.file_size > MAX_RELEASE_FILE_BYTES:
                    return False
                total_bytes += info.file_size
                if total_bytes > MAX_RELEASE_TOTAL_BYTES:
                    return False
                observed[relative] = info
                folded.add(relative.casefold())
            if set(observed) != set(names):
                return False
            root_resolved = root.resolve()
            for name, info in observed.items():
                candidate = (root / name).resolve()
                candidate.relative_to(root_resolved)
                if (
                    not candidate.is_file()
                    or candidate.is_symlink()
                    or archive.read(info) != candidate.read_bytes()
                ):
                    return False
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, zlib.error):
        return False
    return True


def _md5(value: bytes) -> str:
    return hashlib.md5(value, usedforsecurity=False).hexdigest()


def _kaggle_bundle_matches(
    bundle: bytes, archive: bytes, sidecar: bytes, zip_name: str, sidecar_name: str
) -> bool:
    if (
        PurePosixPath(zip_name).name != zip_name
        or not zip_name.endswith(".zip")
        or PurePosixPath(sidecar_name).name != sidecar_name
        or len(archive) > MAX_ARCHIVE_BYTES
        or len(sidecar) > MAX_JSON_BYTES
    ):
        return False
    expected_container = {zip_name: archive, sidecar_name: sidecar}
    try:
        with zipfile.ZipFile(io.BytesIO(bundle)) as candidate:
            infos = candidate.infolist()
            if len(infos) > MAX_RELEASE_FILE_COUNT + 32:
                return False
            observed: dict[str, bytes] = {}
            folded: set[str] = set()
            total_bytes = 0
            for info in infos:
                name = info.filename
                if not isinstance(name, str) or "\\" in name or "\x00" in name:
                    return False
                path = PurePosixPath(name)
                mode = info.external_attr >> 16
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or stat.S_ISLNK(mode)
                ):
                    return False
                if info.is_dir():
                    return False
                if (
                    path.as_posix() != name
                    or name in observed
                    or name.casefold() in folded
                    or info.file_size > MAX_RELEASE_FILE_BYTES
                ):
                    return False
                total_bytes += info.file_size
                if total_bytes > MAX_RELEASE_TOTAL_BYTES + MAX_JSON_BYTES:
                    return False
                observed[name] = candidate.read(info)
                folded.add(name.casefold())
            if observed == expected_container:
                return True

        expanded_prefix = f"{PurePosixPath(zip_name).stem}/"
        expanded_expected = {sidecar_name: sidecar}
        expanded_folded = {sidecar_name.casefold()}
        with zipfile.ZipFile(io.BytesIO(archive)) as release_archive:
            release_infos = release_archive.infolist()
            if len(release_infos) > MAX_RELEASE_FILE_COUNT + 32:
                return False
            release_total = 0
            for info in release_infos:
                if info.is_dir():
                    return False
                name = info.filename
                path = PurePosixPath(name)
                mode = info.external_attr >> 16
                expanded_name = expanded_prefix + name
                if (
                    not isinstance(name, str)
                    or "\\" in name
                    or "\x00" in name
                    or path.is_absolute()
                    or ".." in path.parts
                    or path.as_posix() != name
                    or stat.S_ISLNK(mode)
                    or info.file_size > MAX_RELEASE_FILE_BYTES
                    or expanded_name in expanded_expected
                    or expanded_name.casefold() in expanded_folded
                ):
                    return False
                release_total += info.file_size
                if release_total > MAX_RELEASE_TOTAL_BYTES:
                    return False
                expanded_expected[expanded_name] = release_archive.read(info)
                expanded_folded.add(expanded_name.casefold())
        return observed == expanded_expected
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, zlib.error):
        return False


def attest_public_release(
    root: Path | str,
    manifest: dict[str, Any],
    *,
    expected_commit: str,
    transport: HttpTransport | Any | None = None,
) -> AttestationResult:
    """Verify public source, archive, DOI, and catalog bytes without executing them."""

    root = Path(root).resolve()
    transport = transport or HttpTransport()
    failures: list[str] = []
    archive_sha256: str | None = None
    github_release_url: str | None = None
    zenodo_record_url: str | None = None
    huggingface_commit: str | None = None
    kaggle_version: int | None = None
    software_heritage_snapshot: str | None = None

    try:
        version = manifest["version"]
        version_doi = manifest["version_doi"]
        concept_doi = manifest["concept_doi"]
        release_date = manifest["release_date"]
        source_release = manifest["source_release"]
        doi_match = DOI_PATTERN.fullmatch(version_doi)
        if not (
            manifest.get("title") == TITLE
            and isinstance(version, str)
            and doi_match
            and DOI_PATTERN.fullmatch(concept_doi)
            and manifest.get("canonical_url") == CANONICAL_URL
            and source_release == f"{SOURCE_REPOSITORY}/releases/tag/v{version}"
            and manifest.get("license") == "CC-BY-4.0"
            and isinstance(release_date, str)
        ):
            raise ValueError("identity")
        record_id = doi_match.group(1)
    except (KeyError, TypeError, ValueError):
        return AttestationResult(
            False, ("manifest_identity_invalid",), None, None, None, None, None, None
        )
    if not isinstance(expected_commit, str) or not OBJECT_ID_PATTERN.fullmatch(
        expected_commit
    ):
        return AttestationResult(
            False, ("expected_commit_invalid",), None, None, None, None, None, None
        )

    zip_name = f"lifted-payments-statement-audit-model-v{version}.zip"
    sidecar_name = "release-archive.sha256"
    github_api = (
        "https://api.github.com/repos/Lifted-Holdings/"
        f"payment-processing-resources/releases/tags/v{version}"
    )
    github_prefix = (
        "https://github.com/Lifted-Holdings/payment-processing-resources/"
        f"releases/download/v{version}/"
    )
    zenodo_api = f"https://zenodo.org/api/records/{record_id}"
    doi_url = f"https://doi.org/{version_doi}"
    zenodo_record_url = f"https://zenodo.org/records/{record_id}"
    huggingface_api = (
        f"https://huggingface.co/api/datasets/{HUGGINGFACE_REPOSITORY}"
    )
    encoded_origin = quote(SOURCE_REPOSITORY, safe="")
    software_heritage_visit = (
        "https://archive.softwareheritage.org/api/1/origin/"
        f"{encoded_origin}/visit/latest/?require_snapshot=true"
    )

    archive_bytes: bytes | None = None
    sidecar_bytes: bytes | None = None
    try:
        github = transport.get_json(github_api, max_bytes=MAX_JSON_BYTES)
        assets = github.get("assets")
        if not (
            github.get("tag_name") == f"v{version}"
            and github.get("draft") is False
            and github.get("prerelease") is False
            and github.get("html_url") == source_release
            and isinstance(assets, list)
        ):
            raise ValueError("identity")
        by_name = {
            item.get("name"): item for item in assets if isinstance(item, dict)
        }
        if set(by_name) != {zip_name, sidecar_name}:
            raise ValueError("assets")
        zip_asset = by_name[zip_name]
        sidecar_asset = by_name[sidecar_name]
        if zip_asset.get("browser_download_url") != github_prefix + zip_name:
            raise ValueError("zip_url")
        if sidecar_asset.get("browser_download_url") != github_prefix + sidecar_name:
            raise ValueError("sidecar_url")
        archive_bytes = transport.get_bytes(
            github_prefix + zip_name, max_bytes=MAX_ARCHIVE_BYTES
        )
        sidecar_bytes = transport.get_bytes(
            github_prefix + sidecar_name, max_bytes=1024
        )
        archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
        sidecar_sha256 = hashlib.sha256(sidecar_bytes).hexdigest()
        if not (
            zip_asset.get("size") == len(archive_bytes)
            and zip_asset.get("digest") == f"sha256:{archive_sha256}"
            and sidecar_asset.get("size") == len(sidecar_bytes)
            and sidecar_asset.get("digest") == f"sha256:{sidecar_sha256}"
            and sidecar_bytes
            == f"{archive_sha256}  {zip_name}\n".encode("utf-8")
        ):
            failures.append("github_archive_digest_mismatch")
        github_release_url = source_release
    except (KeyError, OSError, TypeError, UnicodeError, ValueError, json.JSONDecodeError):
        failures.append("github_release_invalid")

    try:
        reproducible_archive = build_archive_bytes(root, manifest)
    except (OSError, TypeError, ValueError):
        reproducible_archive = None
    if (
        archive_bytes is None
        or archive_bytes != reproducible_archive
        or not _archive_matches_release(root, manifest, archive_bytes)
    ):
        failures.append("release_archive_invalid")

    try:
        zenodo = transport.get_json(zenodo_api, max_bytes=MAX_JSON_BYTES)
        metadata = zenodo.get("metadata")
        zenodo_files = zenodo.get("files")
        if not isinstance(metadata, dict) or not isinstance(zenodo_files, list):
            raise ValueError("shape")
        related = {
            (item.get("identifier"), item.get("relation"))
            for item in metadata.get("related_identifiers", [])
            if isinstance(item, dict)
        }
        license_value = metadata.get("license")
        if not (
            str(zenodo.get("id")) == record_id
            and zenodo.get("doi") == version_doi
            and zenodo.get("conceptdoi") == concept_doi
            and metadata.get("title") == TITLE
            and metadata.get("publication_date") == release_date
            and metadata.get("version") == version
            and isinstance(license_value, dict)
            and str(license_value.get("id", "")).casefold() == "cc-by-4.0"
            and (CANONICAL_URL, "isDocumentedBy") in related
            and (source_release, "isSourceOf") in related
        ):
            raise ValueError("identity")
        zenodo_by_name = {
            item.get("key"): item for item in zenodo_files if isinstance(item, dict)
        }
        if set(zenodo_by_name) != {zip_name, sidecar_name}:
            raise ValueError("file_inventory")
        for name, expected_bytes, byte_limit in (
            (zip_name, archive_bytes, MAX_ARCHIVE_BYTES),
            (sidecar_name, sidecar_bytes, 1024),
        ):
            item = zenodo_by_name[name]
            expected_url = (
                f"https://zenodo.org/api/records/{record_id}/files/"
                f"{quote(name)}/content"
            )
            if item.get("links", {}).get("self") != expected_url:
                raise ValueError("file_url")
            downloaded = transport.get_bytes(expected_url, max_bytes=byte_limit)
            if not (
                expected_bytes is not None
                and downloaded == expected_bytes
                and item.get("size") == len(downloaded)
                and item.get("checksum") == f"md5:{_md5(downloaded)}"
            ):
                raise ValueError("file_digest")
    except (KeyError, OSError, TypeError, UnicodeError, ValueError, json.JSONDecodeError):
        failures.append("zenodo_release_invalid")

    try:
        resolved = transport.resolve(doi_url, max_bytes=MAX_JSON_BYTES)
        if resolved.rstrip("/") != zenodo_record_url:
            raise ValueError("doi_target")
    except (OSError, TypeError, ValueError):
        failures.append("doi_resolution_invalid")

    try:
        huggingface = transport.get_json(huggingface_api, max_bytes=MAX_JSON_BYTES)
        siblings = huggingface.get("siblings")
        sibling_names = {
            item.get("rfilename") for item in siblings if isinstance(item, dict)
        }
        huggingface_commit = huggingface.get("sha")
        expected_siblings = {"README.md", zip_name, sidecar_name}
        if not (
            huggingface.get("id") == HUGGINGFACE_REPOSITORY
            and huggingface.get("private") is False
            and huggingface.get("disabled") is False
            and huggingface.get("gated") is False
            and isinstance(huggingface_commit, str)
            and OBJECT_ID_PATTERN.fullmatch(huggingface_commit)
            and sibling_names == expected_siblings
            and archive_bytes is not None
            and sidecar_bytes is not None
            and transport.get_bytes(
                f"https://huggingface.co/datasets/{HUGGINGFACE_REPOSITORY}/"
                f"resolve/{huggingface_commit}/{quote(zip_name)}",
                max_bytes=MAX_ARCHIVE_BYTES,
            )
            == archive_bytes
            and transport.get_bytes(
                f"https://huggingface.co/datasets/{HUGGINGFACE_REPOSITORY}/"
                f"resolve/{huggingface_commit}/{sidecar_name}",
                max_bytes=1024,
            )
            == sidecar_bytes
            and transport.get_bytes(
                f"https://huggingface.co/datasets/{HUGGINGFACE_REPOSITORY}/"
                f"resolve/{huggingface_commit}/README.md",
                max_bytes=MAX_JSON_BYTES,
            )
            == (root / "distribution/huggingface/README.md").read_bytes()
        ):
            raise ValueError("huggingface")
    except (OSError, TypeError, ValueError):
        failures.append("huggingface_release_invalid")

    try:
        kaggle_view_url = (
            "https://www.kaggle.com/api/v1/datasets/view/"
            "liftedpayments/payment-statement-audit-model"
        )
        item = transport.get_json(kaggle_view_url, max_bytes=MAX_JSON_BYTES)
        kaggle_version = item.get("currentVersionNumber")
        description = item.get("description")
        if not (
            item.get("ref") == KAGGLE_REPOSITORY
            and item.get("title") == TITLE
            and item.get("isPrivate") is False
            and item.get("licenseName")
            == "Attribution 4.0 International (CC BY 4.0)"
            and isinstance(kaggle_version, int)
            and kaggle_version > 0
            and isinstance(description, str)
            and f"Version {version}" in description
            and version_doi in description
            and source_release in description
            and archive_sha256 in description
            and archive_bytes is not None
            and sidecar_bytes is not None
        ):
            raise ValueError("catalog_metadata")
        kaggle_bundle = transport.post_bytes(
            "https://api.kaggle.com/v1/"
            "datasets.DatasetApiService/DownloadDataset",
            {
                "ownerSlug": "liftedpayments",
                "datasetSlug": "payment-statement-audit-model",
                "datasetVersionNumber": kaggle_version,
            },
            max_bytes=MAX_ARCHIVE_BYTES * 2,
        )
        if not _kaggle_bundle_matches(
            kaggle_bundle, archive_bytes, sidecar_bytes, zip_name, sidecar_name
        ):
            raise ValueError("catalog_bundle")
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        failures.append("kaggle_release_invalid")

    try:
        visit = transport.get_json(
            software_heritage_visit, max_bytes=MAX_JSON_BYTES
        )
        software_heritage_snapshot = visit.get("snapshot")
        if not (
            visit.get("origin") == SOURCE_REPOSITORY
            and visit.get("status") == "full"
            and isinstance(software_heritage_snapshot, str)
            and OBJECT_ID_PATTERN.fullmatch(software_heritage_snapshot)
        ):
            raise ValueError("visit")
        snapshot_url = (
            "https://archive.softwareheritage.org/api/1/snapshot/"
            f"{software_heritage_snapshot}/"
        )
        snapshot = transport.get_json(snapshot_url, max_bytes=MAX_JSON_BYTES)
        branches = snapshot.get("branches")
        if not (
            snapshot.get("id") == software_heritage_snapshot
            and isinstance(branches, dict)
        ):
            raise ValueError("snapshot")
        main_branch = branches.get("refs/heads/main")
        release_branch = branches.get(f"refs/tags/v{version}")
        if not (
            isinstance(main_branch, dict)
            and main_branch.get("target_type") == "revision"
            and main_branch.get("target") == expected_commit
            and isinstance(release_branch, dict)
        ):
            raise ValueError("branches")
        if release_branch.get("target_type") == "revision":
            release_commit = release_branch.get("target")
        elif release_branch.get("target_type") == "release":
            release_id = release_branch.get("target")
            if not isinstance(release_id, str) or not OBJECT_ID_PATTERN.fullmatch(
                release_id
            ):
                raise ValueError("release_id")
            release = transport.get_json(
                "https://archive.softwareheritage.org/api/1/release/"
                f"{release_id}/",
                max_bytes=MAX_JSON_BYTES,
            )
            if not (
                release.get("id") == release_id
                and release.get("name") == f"v{version}"
                and release.get("target_type") == "revision"
            ):
                raise ValueError("release")
            release_commit = release.get("target")
        else:
            raise ValueError("release_type")
        if release_commit != expected_commit:
            raise ValueError("release_commit")
    except (OSError, TypeError, ValueError):
        failures.append("software_heritage_release_invalid")

    unique_failures = tuple(dict.fromkeys(failures))
    return AttestationResult(
        verified=not unique_failures,
        failure_codes=unique_failures,
        archive_sha256=archive_sha256,
        github_release_url=github_release_url,
        zenodo_record_url=zenodo_record_url,
        huggingface_commit=huggingface_commit,
        kaggle_version=kaggle_version,
        software_heritage_snapshot=software_heritage_snapshot,
    )
