from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def _is_int(value: str) -> bool:
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


def _truncate(value: str, limit: int = 160) -> str:
    value = value.replace("\r", "\\r").replace("\n", "\\n")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _detect_header(rows: list[list[str]], dominant_width: int) -> dict[str, str]:
    if not rows:
        return {
            "classification": "no_data",
            "confidence": "high",
            "evidence": "no non-empty rows",
        }
    first = rows[0]
    if len(rows) > 1 and len(first) != dominant_width:
        return {
            "classification": "yes",
            "confidence": "high",
            "evidence": (
                f"first row width {len(first)} differs from dominant "
                f"data width {dominant_width}"
            ),
        }
    if len(rows) > 1:
        second = rows[1]
        candidate_columns: list[int] = []
        for index in range(min(len(first), len(second), dominant_width)):
            later = [
                row[index]
                for row in rows[1:101]
                if len(row) > index and row[index] != ""
            ]
            integer_ratio = (
                sum(_is_int(value) for value in later) / len(later)
                if later
                else 0.0
            )
            if (
                first[index] != ""
                and not _is_int(first[index])
                and integer_ratio >= 0.9
            ):
                candidate_columns.append(index + 1)
        if candidate_columns:
            return {
                "classification": "yes",
                "confidence": "medium",
                "evidence": (
                    "first row is non-numeric while later rows are numeric "
                    f"in likely index columns {candidate_columns}"
                ),
            }
    return {
        "classification": "no_or_uncertain",
        "confidence": "low",
        "evidence": "first row follows the dominant row shape",
    }


def _index_candidates(
    rows: list[list[str]], dominant_width: int
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    sample_rows = [row for row in rows[:5000] if len(row) == dominant_width]
    if not sample_rows:
        return candidates
    for index in range(dominant_width):
        values = [row[index] for row in sample_rows if row[index] != ""]
        if not values:
            continue
        integer_count = sum(_is_int(value) for value in values)
        unique_ratio = len(set(values)) / len(values)
        integer_ratio = integer_count / len(values)
        if unique_ratio >= 0.98 and (integer_ratio >= 0.9 or index < 2):
            candidates.append(
                {
                    "column": index + 1,
                    "nonempty_count": len(values),
                    "unique_ratio": round(unique_ratio, 6),
                    "integer_ratio": round(integer_ratio, 6),
                }
            )
    return candidates


def _star_columns(
    rows: list[list[str]], dominant_width: int
) -> list[dict[str, object]]:
    counts: Counter[int] = Counter()
    samples: dict[int, str] = {}
    for row in rows:
        for index, value in enumerate(row[:dominant_width]):
            if "*" in value:
                counts[index] += 1
                samples.setdefault(index, _truncate(value))
    return [
        {
            "column": index + 1,
            "row_count": count,
            "sample": samples[index],
        }
        for index, count in sorted(counts.items())
    ]


def profile_file(path: Path, *, relative_path: str) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    physical_lines = text.splitlines()
    nonempty_lines = [line for line in physical_lines if line.strip()]
    rows = [line.split("\t") for line in nonempty_lines]
    widths = Counter(len(row) for row in rows)
    dominant_width = widths.most_common(1)[0][0] if widths else 0
    header = _detect_header(rows, dominant_width)
    return {
        "path": relative_path,
        "physical_line_count": len(physical_lines),
        "nonempty_line_count": len(rows),
        "column_count_distribution": {
            str(width): count for width, count in sorted(widths.items())
        },
        "dominant_column_count": dominant_width,
        "first_row_column_count": len(rows[0]) if rows else 0,
        "first_row_sample": _truncate(nonempty_lines[0]) if nonempty_lines else "",
        "header": header,
        "index_candidates": _index_candidates(rows, dominant_width),
        "star_delimited_columns": _star_columns(rows, dominant_width),
    }


def run_profile(
    *,
    inventory_path: Path,
    output_dir: Path,
    check: bool = False,
) -> dict[str, object]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    input_root = Path(inventory["input_root"])
    source_root = input_root.parent
    profiles: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []

    for record in inventory["files"]:
        relative_path = record["path"]
        path = source_root / relative_path
        try:
            profile = profile_file(path, relative_path=relative_path)
        except Exception as exc:  # keep a complete diagnostic set
            errors.append({"path": relative_path, "error": repr(exc)})
        else:
            profiles.append(profile)

    if check and (errors or len(profiles) != inventory["file_count"]):
        raise RuntimeError(
            f"profile check failed: profiles={len(profiles)} "
            f"expected={inventory['file_count']} errors={len(errors)}"
        )

    header_counts = Counter(
        profile["header"]["classification"] for profile in profiles
    )
    star_file_count = sum(
        bool(profile["star_delimited_columns"]) for profile in profiles
    )
    result = {
        "schema_version": 1,
        "run_id": inventory["run_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inventory_path": inventory_path.as_posix(),
        "profile_count": len(profiles),
        "error_count": len(errors),
        "header_classification_counts": dict(sorted(header_counts.items())),
        "files_with_star_delimited_columns": star_file_count,
        "errors": errors,
        "profiles": profiles,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "schema_profiles.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report_lines = [
        "# Input Structure Profile",
        "",
        f"- Run ID: `{inventory['run_id']}`",
        f"- Profiled files: {len(profiles)}",
        f"- Errors: {len(errors)}",
        f"- Files with star-delimited columns: {star_file_count}",
        f"- Header classifications: `{dict(sorted(header_counts.items()))}`",
        "",
        "## Quest Core Tables",
        "",
        "| File | Rows | Dominant columns | Header | Index candidates | Star columns |",
        "|---|---:|---:|---|---|---|",
    ]
    for profile in profiles:
        if "/quest/" not in profile["path"]:
            continue
        index_columns = ", ".join(
            str(item["column"]) for item in profile["index_candidates"]
        ) or "—"
        star_columns = ", ".join(
            str(item["column"]) for item in profile["star_delimited_columns"]
        ) or "—"
        report_lines.append(
            f"| `{profile['path']}` | {profile['nonempty_line_count']} | "
            f"{profile['dominant_column_count']} | "
            f"{profile['header']['classification']} "
            f"({profile['header']['confidence']}) | "
            f"{index_columns} | {star_columns} |"
        )
    if errors:
        report_lines.extend(["", "## Errors", ""])
        report_lines.extend(
            f"- `{item['path']}`: {item['error']}" for item in errors
        )
    (output_dir / "profile_report.md").write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )
    return result
