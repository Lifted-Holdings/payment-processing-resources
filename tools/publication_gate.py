#!/usr/bin/env python3
"""Fail-closed publication gate for the statement-audit release package."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "RELEASE-MANIFEST.json"
CHECKSUMS_PATH = ROOT / "checksums.txt"
VERSION_DOI_PATTERN = re.compile(r"^10\.5281/zenodo\.\d+$")
SECRET_PATTERN = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:sk|ghp|github_pat|hf)_[A-Za-z0-9_-]{12,}\b)",
    re.I,
)


def _load_validator_module():
    path = ROOT / "tools/validate_audit.py"
    spec = importlib.util.spec_from_file_location("release_audit_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("validator_import_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class GateCheck:
    code: str
    status: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _check(code: str, passed: bool, success: str, failure: str) -> GateCheck:
    return GateCheck(code, "pass" if passed else "fail", success if passed else failure)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest(root: Path) -> dict[str, Any]:
    return json.loads((root / "RELEASE-MANIFEST.json").read_text(encoding="utf-8"))


def _safe_file_paths(root: Path, names: list[str]) -> tuple[list[Path], bool]:
    root_resolved = root.resolve()
    paths: list[Path] = []
    safe = True
    for name in names:
        candidate = (root / name).resolve()
        try:
            candidate.relative_to(root_resolved)
        except ValueError:
            safe = False
        if Path(name).is_absolute() or ".." in Path(name).parts:
            safe = False
        paths.append(candidate)
    return paths, safe


def _parse_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    if not path.is_file():
        return checksums
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            return {}
        if parts[1] in checksums:
            return {}
        checksums[parts[1]] = parts[0]
    return checksums


def _pinned_dependencies(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return pins
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("==", maxsplit=1)
        if len(parts) != 2 or not all(parts):
            return {}
        pins[parts[0]] = parts[1]
    return pins


def _identity_matches(root: Path, manifest: dict[str, Any]) -> bool:
    version = manifest.get("version")
    doi = manifest.get("version_doi")
    if not isinstance(version, str) or not isinstance(doi, str):
        return False
    doi_url = f"https://doi.org/{doi}"
    release_url = manifest.get("source_release")

    try:
        zenodo = json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))
        codemeta = json.loads((root / "codemeta.json").read_text(encoding="utf-8"))
        citation = (root / "CITATION.cff").read_text(encoding="utf-8")
        schema = json.loads(
            (root / "schema/payment-statement-audit.schema.json").read_text(
                encoding="utf-8"
            )
        )
        example = json.loads(
            (root / "examples/payment-statement-audit-example.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False

    if not (
        zenodo.get("version") == version
        and codemeta.get("version") == version
        and codemeta.get("identifier") == doi_url
        and example.get("schema_version") == version
        and schema.get("properties", {}).get("schema_version", {}).get("const")
        == version
        and re.search(rf"(?m)^version: {re.escape(version)}$", citation)
        and re.search(rf'(?m)^doi: "{re.escape(doi)}"$', citation)
    ):
        return False

    identity_files = (
        "README.md",
        "llms.txt",
        "distribution/huggingface/README.md",
        "distribution/kaggle/README.md",
    )
    for name in identity_files:
        text = (root / name).read_text(encoding="utf-8")
        if version not in text or doi_url not in text or release_url not in text:
            return False
    return True


def build_publication_report(root: Path | str = ROOT) -> dict[str, Any]:
    root = Path(root)
    manifest = _load_manifest(root)
    names = manifest.get("files", [])
    paths, safe_paths = _safe_file_paths(root, names if isinstance(names, list) else [])
    checks: list[GateCheck] = []

    checks.append(
        _check(
            "manifest_inventory",
            isinstance(names, list)
            and len(names) == len(set(names))
            and len(names) >= 20
            and safe_paths
            and all(path.is_file() and not path.is_symlink() for path in paths),
            "Release inventory is explicit, unique, contained, and complete.",
            "Release inventory is missing, duplicated, unsafe, or incomplete.",
        )
    )

    version_doi = manifest.get("version_doi")
    checks.append(
        _check(
            "version_doi_reserved",
            isinstance(version_doi, str)
            and bool(VERSION_DOI_PATTERN.fullmatch(version_doi))
            and version_doi != "10.5281/zenodo.21761715",
            "A distinct Zenodo v1.1.0 DOI is reserved.",
            "A distinct Zenodo v1.1.0 DOI has not been reserved.",
        )
    )

    try:
        audit_validator = _load_validator_module()
        corpus_report = audit_validator.build_corpus_report(root)
        corpus_ready = corpus_report.get("status") == "pass"
    except (OSError, UnicodeError, ValueError, RuntimeError, json.JSONDecodeError):
        corpus_report = {"status": "fail"}
        corpus_ready = False
    checks.append(
        _check(
            "corpus_validation",
            corpus_ready,
            "All valid and invalid synthetic vectors produce expected results.",
            "The synthetic validation corpus does not reproduce expected results.",
        )
    )

    dependency_lock = _pinned_dependencies(root / "requirements-validation.txt")
    checks.append(
        _check(
            "dependency_lock",
            corpus_ready
            and dependency_lock == corpus_report.get("dependency_versions"),
            "Validation runtime and all transitive dependencies are exactly pinned.",
            "Validation dependency pins are incomplete or differ from the tested runtime.",
        )
    )

    checks.append(
        _check(
            "release_identity",
            _identity_matches(root, manifest),
            "Version, DOI, schema, citation, and source-release identities agree.",
            "Version, DOI, schema, citation, or source-release identities disagree.",
        )
    )

    checksums = _parse_checksums(root / "checksums.txt")
    expected_checksum_files = set(names) - {"checksums.txt"}
    checksum_valid = set(checksums) == expected_checksum_files
    if checksum_valid:
        checksum_valid = all(
            (root / name).is_file() and _sha256(root / name) == digest
            for name, digest in checksums.items()
        )
    checks.append(
        _check(
            "release_checksums",
            checksum_valid,
            "SHA-256 manifest exactly covers and matches every release file.",
            "SHA-256 manifest is incomplete, stale, malformed, or mismatched.",
        )
    )

    lf_only = all(b"\r\n" not in path.read_bytes() for path in paths if path.is_file())
    checks.append(
        _check(
            "lf_portability",
            lf_only,
            "All release text assets use reproducible LF line endings.",
            "One or more release assets contain noncanonical CRLF line endings.",
        )
    )

    utf8_assets = True
    for path in paths:
        try:
            path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError):
            utf8_assets = False
    checks.append(
        _check(
            "utf8_text_assets",
            utf8_assets,
            "Every declared release asset is strict UTF-8 text.",
            "One or more declared release assets is unreadable as strict UTF-8 text.",
        )
    )

    public_text_names = (
        ".zenodo.json",
        "CITATION.cff",
        "codemeta.json",
        "DATA_DICTIONARY.md",
        "distribution/huggingface/README.md",
        "distribution/kaggle/README.md",
        "distribution/kaggle/dataset-metadata.json",
        "examples/payment-statement-audit-example.json",
        "llms.txt",
        "METHODOLOGY.md",
        "payment-statement-audit-template.csv",
        "README.md",
        "schema/payment-statement-audit.schema.json",
    )
    try:
        public_text = "\n".join(
            (root / name).read_text(encoding="utf-8") for name in public_text_names
        )
        safe_public_text = not SECRET_PATTERN.search(public_text)
    except (UnicodeError, OSError):
        safe_public_text = False
    checks.append(
        _check(
            "public_content_safety",
            safe_public_text,
            "Public files contain no credential signatures.",
            "Public files contain a credential signature.",
        )
    )

    validation_report_path = root / "validation-report.json"
    validation_report_matches = False
    if validation_report_path.is_file() and corpus_ready:
        try:
            published_report = json.loads(
                validation_report_path.read_text(encoding="utf-8")
            )
            validation_report_matches = published_report == corpus_report
        except (UnicodeError, OSError, json.JSONDecodeError):
            pass
    checks.append(
        _check(
            "validation_report",
            validation_report_matches,
            "Published validation report exactly matches a fresh corpus run.",
            "Published validation report is missing, stale, or inconsistent.",
        )
    )

    serialized = [check.to_dict() for check in checks]
    failed = sum(check["status"] == "fail" for check in serialized)
    return {
        "gate_version": "1.0.0",
        "release_version": manifest.get("version"),
        "status": "ready" if failed == 0 else "blocked",
        "check_count": len(serialized),
        "failed_check_count": failed,
        "checks": serialized,
        "manifest_sha256": _sha256(root / "RELEASE-MANIFEST.json"),
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that the statement-audit package is safe to publish."
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_publication_report(ROOT)
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"PUBLICATION {report['status'].upper()}: {report['failed_check_count']} failed check(s)")
        for check in report["checks"]:
            print(f"- {check['status'].upper()} {check['code']}: {check['message']}")
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
