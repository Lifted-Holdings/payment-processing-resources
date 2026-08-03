#!/usr/bin/env python3
"""Stage the exact release archive and digest for a Kaggle dataset version."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from build_release_archive import build_archive_bytes  # noqa: E402


DIGEST_PLACEHOLDER = "{{RELEASE_ARCHIVE_SHA256}}"


def build_distribution(root: Path | str, output: Path | str) -> dict[str, Any]:
    root = Path(root).resolve()
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("output_directory_not_empty")
    output.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((root / "RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
    version = manifest.get("version")
    if not isinstance(version, str):
        raise ValueError("release_version_invalid")
    archive = build_archive_bytes(root, manifest)
    digest = hashlib.sha256(archive).hexdigest()
    archive_name = f"lifted-payments-statement-audit-model-v{version}.zip"
    sidecar_name = "release-archive.sha256"
    sidecar = f"{digest}  {archive_name}\n"

    metadata_path = root / "distribution/kaggle/dataset-metadata.json"
    metadata_source = metadata_path.read_text(encoding="utf-8")
    if metadata_source.count(DIGEST_PLACEHOLDER) != 1:
        raise ValueError("kaggle_digest_token_invalid")
    metadata = json.loads(metadata_source.replace(DIGEST_PLACEHOLDER, digest))
    resources = metadata.get("resources")
    if not (
        metadata.get("id") == "liftedpayments/payment-statement-audit-model"
        and isinstance(resources, list)
        and {item.get("path") for item in resources if isinstance(item, dict)}
        == {archive_name, sidecar_name}
        and digest in metadata.get("description", "")
    ):
        raise ValueError("kaggle_metadata_invalid")

    (output / archive_name).write_bytes(archive)
    (output / sidecar_name).write_text(sidecar, encoding="utf-8", newline="\n")
    (output / "dataset-metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {
        "archive": archive_name,
        "archive_sha256": digest,
        "files": sorted(path.name for path in output.iterdir()),
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    print(json.dumps(build_distribution(args.root, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
