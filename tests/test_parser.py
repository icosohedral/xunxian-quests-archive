from __future__ import annotations

import unittest
from pathlib import Path

from questdb.parser import iter_nonempty, parse_text_file, split_star


WORKSPACE = Path(__file__).resolve().parents[1]
INPUT_ROOT = WORKSPACE / "original_data"
RUN_ID = "parser-test"


class ParserTests(unittest.TestCase):
    def test_all_input_files_decode_strictly(self) -> None:
        paths = sorted(
            path
            for path in INPUT_ROOT.rglob("*")
            if path.is_file() and path.name != ".DS_Store"
        )
        self.assertEqual(len(paths), 830)
        for path in paths:
            rows = parse_text_file(
                path,
                run_id=RUN_ID,
                source_root=WORKSPACE,
            )
            self.assertTrue(all("\ufffd" not in row.raw_value for row in rows))

    def test_quest_info_header_and_data_shape(self) -> None:
        rows = parse_text_file(
            INPUT_ROOT / "mb/quest/quest_info.txt",
            run_id=RUN_ID,
            source_root=WORKSPACE,
        )
        nonempty = list(iter_nonempty(rows))
        self.assertEqual(len(nonempty), 8830)
        self.assertEqual(len(nonempty[0].values), 1)
        self.assertEqual(len(nonempty[1].values), 106)
        self.assertEqual(nonempty[1].values[1], "1")
        self.assertEqual(nonempty[-1].source_row, 8830)

    def test_line_endings_are_preserved(self) -> None:
        rows = parse_text_file(
            INPUT_ROOT / "mb/avatar_cupboard/avatar_cupboard.txt",
            run_id=RUN_ID,
            source_root=WORKSPACE,
        )
        endings = {row.line_ending for row in rows}
        self.assertIn("\r\n", endings)
        self.assertIn("\n", endings)

    def test_literal_escaped_newlines_are_not_expanded(self) -> None:
        rows = parse_text_file(
            INPUT_ROOT / "mb/quest/quest_text.txt",
            run_id=RUN_ID,
            source_root=WORKSPACE,
        )
        row_two = next(row for row in rows if row.values[0] == "2")
        self.assertIn("\\n", row_two.raw_value)
        self.assertNotIn("\n", row_two.raw_value)

    def test_empty_physical_rows_are_retained(self) -> None:
        rows = parse_text_file(
            INPUT_ROOT / "mb/quest/quest_text.txt",
            run_id=RUN_ID,
            source_root=WORKSPACE,
        )
        self.assertTrue(rows[0].is_empty)
        self.assertEqual(rows[0].source_row, 1)
        self.assertEqual(rows[0].values, ("",))

    def test_star_split_preserves_position(self) -> None:
        self.assertEqual(split_star("5*25307*6*25308"), ("5", "25307", "6", "25308"))
        self.assertEqual(split_star("a**b"), ("a", "", "b"))
        self.assertEqual(split_star("a**b", keep_empty=False), ("a", "b"))


if __name__ == "__main__":
    unittest.main()
