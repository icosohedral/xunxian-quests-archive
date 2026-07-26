from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True, slots=True)
class ParsedRow:
    source_file: str
    source_row: int
    raw_value: str
    values: tuple[str, ...]
    line_ending: str
    run_id: str

    @property
    def is_empty(self) -> bool:
        return not self.raw_value.strip()


def _split_content_and_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    if line.endswith("\r"):
        return line[:-1], "\r"
    return line, ""


def parse_text_file(
    path: Path,
    *,
    run_id: str,
    source_root: Path | None = None,
) -> list[ParsedRow]:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="strict")
    if "\ufffd" in text:
        raise UnicodeError(f"Replacement character U+FFFD found in {path}")

    if source_root is None:
        source_file = path.as_posix()
    else:
        source_file = path.resolve().relative_to(source_root.resolve()).as_posix()

    parsed: list[ParsedRow] = []
    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        content, line_ending = _split_content_and_ending(line)
        parsed.append(
            ParsedRow(
                source_file=source_file,
                source_row=line_number,
                raw_value=content,
                values=tuple(content.split("\t")),
                line_ending=line_ending,
                run_id=run_id,
            )
        )
    if text and not parsed:
        parsed.append(
            ParsedRow(
                source_file=source_file,
                source_row=1,
                raw_value=text,
                values=tuple(text.split("\t")),
                line_ending="",
                run_id=run_id,
            )
        )
    return parsed


def iter_nonempty(rows: list[ParsedRow]) -> Iterator[ParsedRow]:
    return (row for row in rows if not row.is_empty)


def split_star(value: str, *, keep_empty: bool = True) -> tuple[str, ...]:
    parts = tuple(value.split("*"))
    if keep_empty:
        return parts
    return tuple(part for part in parts if part != "")

