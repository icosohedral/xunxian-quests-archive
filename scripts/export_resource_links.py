#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from questdb.resource_links import export_resource_links


def main() -> None:
    parser = argparse.ArgumentParser(description="导出任务与外部资源的轻量关系文件")
    parser.add_argument(
        "--database",
        type=Path,
        default=PROJECT_ROOT
        / "outputs/quest_database/releases/1.0.1/quest.db",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "outputs/resource_exchange/quest_resource_links.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT
        / "outputs/resource_exchange/quest_resource_links.report.json",
    )
    args = parser.parse_args()
    report = export_resource_links(
        database_path=args.database,
        output_path=args.output,
        report_path=args.report,
    )
    print(
        f"已导出 {report['link_count']} 条资源关系；"
        f"合并 {report['duplicate_candidate_count']} 条重复候选"
    )


if __name__ == "__main__":
    main()
