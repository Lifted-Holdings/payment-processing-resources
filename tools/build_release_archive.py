#!/usr/bin/env python3
"""Build the statement-audit release archive with deterministic bytes."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import stat
import zipfile
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_COUNT = 256
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024


def _safe_inventory(root: Path, manifest: dict[str, Any]) -> tuple[str, list[str], tuple[int, int, int, int, int, int]]:
    version = manifest.get("version")
    names = manifest.get("files")
    release_date = manifest.get("release_date")
    if (
        not isinstance(version, str)
        or not isinstance(names, list)
        or not names
        or len(names) > MAX_FILE_COUNT
        or not all(isinstance(name, str) and name for name in names)
        or len(names) != len(set(names))
        or not isinstance(release_date, str)
    ):
        raise ValueError("release_manifest_invalid")
    parsed_date = date.fromisoformat(release_date)
    timestamp = (parsed_date.year, parsed_date.month, parsed_date.day, 0, 0, 0)
    root_resolved = root.resolve()
    total = 0
    for name in names:
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != name:
            raise ValueError("release_path_invalid")
        candidate = root.joinpath(*relative.parts)
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError("release_file_invalid")
        resolved = candidate.resolve()
        resolved.relative_to(root_resolved)
        size = resolved.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ValueError("release_file_too_large")
        total += size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("release_total_too_large")
    return version, sorted(names, key=str.casefold), timestamp


def build_archive_bytes(root: Path | str, manifest: dict[str, Any]) -> bytes:
    """Return a byte-reproducible, uncompressed ZIP of declared release files."""

    root = Path(root).resolve()
    version, names, timestamp = _safe_inventory(root, manifest)
    prefix = f"payment-processing-resources-{version}/"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in names:
            info = zipfile.ZipInfo(prefix + name, date_time=timestamp)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, (root / name).read_bytes())
    return output.getvalue()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.root.resolve()
    manifest = json.loads((root / "RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
    archive = build_archive_bytes(root, manifest)
    output = args.output or (
        root.parent / f"lifted-payments-statement-audit-model-v{manifest['version']}.zip"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(archive)
    digest = hashlib.sha256(archive).hexdigest()
    output.with_name("release-archive.sha256").write_text(
        f"{digest}  {output.name}\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({"archive": str(output), "sha256": digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
