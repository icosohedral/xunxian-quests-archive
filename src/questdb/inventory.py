from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


IGNORED_NAMES = {".DS_Store"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _column_counts(text: str) -> dict[str, int]:
    counts = Counter(
        len(line.split("\t"))
        for line in text.splitlines()
        if line.strip()
    )
    return {str(width): count for width, count in sorted(counts.items())}


def _snapshot_metadata(paths: list[Path]) -> dict[Path, tuple[int, int]]:
    return {
        path: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in paths
    }


def run_inventory(
    *,
    root: Path,
    output_dir: Path | None = None,
    run_id: str | None = None,
    strict: bool = False,
) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Input root does not exist: {root}")

    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (
        output_dir
        or Path("outputs") / "quest_database" / "runs" / run_id
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name not in IGNORED_NAMES
    )
    before = _snapshot_metadata(paths)
    files: list[dict[str, object]] = []
    hashes: dict[str, str] = {}
    decoding_errors: list[dict[str, str]] = []

    for path in paths:
        raw = path.read_bytes()
        relative = path.relative_to(root.parent).as_posix()
        digest = _sha256(raw)
        hashes[relative] = digest
        record: dict[str, object] = {
            "path": relative,
            "size_bytes": len(raw),
            "sha256": digest,
            "suffix": path.suffix,
        }
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            record["encoding"] = "unknown"
            record["decode_error"] = str(exc)
            decoding_errors.append({"path": relative, "error": str(exc)})
        else:
            record.update(
                {
                    "encoding": "utf-8",
                    "line_count": len(text.splitlines()),
                    "nonempty_line_count": sum(
                        1 for line in text.splitlines() if line.strip()
                    ),
                    "column_count_distribution": _column_counts(text),
                }
            )
        files.append(record)

    after = _snapshot_metadata(paths)
    changed_during_scan = [
        path.relative_to(root.parent).as_posix()
        for path in paths
        if before[path] != after[path]
    ]
    if changed_during_scan:
        raise RuntimeError(
            "Input files changed during scan: "
            + ", ".join(changed_during_scan[:10])
        )
    if strict and decoding_errors:
        raise UnicodeError(
            f"{len(decoding_errors)} input files are not valid UTF-8; "
            f"first={decoding_errors[0]['path']}"
        )

    scanned_at = datetime.now(timezone.utc).isoformat()
    inventory = {
        "schema_version": 1,
        "run_id": run_id,
        "scanned_at": scanned_at,
        "input_root": root.as_posix(),
        "file_count": len(files),
        "text_file_count": sum(
            1 for record in files if record.get("encoding") == "utf-8"
        ),
        "ignored_names": sorted(IGNORED_NAMES),
        "decode_error_count": len(decoding_errors),
        "changed_during_scan": changed_during_scan,
        "files": files,
    }
    hash_manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "scanned_at": scanned_at,
        "input_root": root.as_posix(),
        "algorithm": "sha256",
        "file_count": len(hashes),
        "files": hashes,
    }

    (output_dir / "inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "input_hashes.json").write_text(
        json.dumps(hash_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return inventory

