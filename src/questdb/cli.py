from __future__ import annotations

import argparse
import json
from pathlib import Path

from questdb.inventory import run_inventory
from questdb.delivery import (
    create_release,
    finalize_release_audit,
    install_views,
    validate_query_interfaces,
    verify_deterministic_rebuild,
)
from questdb.extended import (
    generate_quality_report,
    load_groups,
    load_locations,
    load_mappings,
    load_relations,
    load_special_configs,
    load_unresolved_references,
    strict_p0_validation,
)
from questdb.normalized import (
    init_database,
    load_character_calls,
    load_items_and_rewards,
    load_npc_and_targets,
    load_objects,
    load_quest,
    load_text_and_categories,
    validate_database,
)
from questdb.profile import run_profile
from questdb.raw_store import load_raw
from questdb.schema_inference import write_schema_outputs
from questdb.sample_pack import generate_g02_sample_pack


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="questdb")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser(
        "inventory",
        help="Create a read-only inventory and hash snapshot of input files.",
    )
    inventory.add_argument("--root", type=Path, default=Path("original_data"))
    inventory.add_argument("--output", type=Path)
    inventory.add_argument("--run-id")
    inventory.add_argument("--strict", action="store_true")

    profile = subparsers.add_parser(
        "profile",
        help="Profile row shapes, header likelihood, index candidates and arrays.",
    )
    profile.add_argument("--inventory", type=Path, required=True)
    profile.add_argument("--output", type=Path, required=True)
    profile.add_argument("--check", action="store_true")

    load = subparsers.add_parser(
        "load-raw",
        help="Load every physical row and cell into an immutable raw SQLite DB.",
    )
    load.add_argument("--inventory", type=Path, required=True)
    load.add_argument("--profiles", type=Path, required=True)
    load.add_argument("--output-db", type=Path, required=True)
    load.add_argument("--manifest", type=Path, required=True)
    load.add_argument("--check", action="store_true")

    schema = subparsers.add_parser(
        "validate-schema",
        help="Infer and validate the 106-column quest_info schema draft.",
    )
    schema.add_argument(
        "--quest-info",
        type=Path,
        default=Path("original_data/mb/quest/quest_info.txt"),
    )
    schema.add_argument(
        "--index-list",
        type=Path,
        default=Path("original_data/index_list.txt"),
    )
    schema.add_argument(
        "--quest-dir",
        type=Path,
        default=Path("original_data/mb/quest"),
    )
    schema.add_argument("--output-dir", type=Path, default=Path("docs"))

    init_db = subparsers.add_parser("init-db", help="Create a normalized quest database.")
    init_db.add_argument("--db", type=Path, required=True)
    init_db.add_argument("--run-id", required=True)

    load_quest_parser = subparsers.add_parser("load-quest", help="Load quest_info.")
    load_quest_parser.add_argument("--root", type=Path, default=Path("original_data"))
    load_quest_parser.add_argument("--db", type=Path, required=True)
    load_quest_parser.add_argument("--report", type=Path, required=True)
    load_quest_parser.add_argument("--run-id", required=True)

    load_text_parser = subparsers.add_parser(
        "load-text-category", help="Load quest text and categories."
    )
    load_text_parser.add_argument("--root", type=Path, default=Path("original_data"))
    load_text_parser.add_argument("--db", type=Path, required=True)
    load_text_parser.add_argument("--report", type=Path, required=True)
    load_text_parser.add_argument("--run-id", required=True)

    load_calls_parser = subparsers.add_parser(
        "load-character-calls", help="Load dynamic player-address profiles."
    )
    load_calls_parser.add_argument("--root", type=Path, default=Path("original_data"))
    load_calls_parser.add_argument("--db", type=Path, required=True)
    load_calls_parser.add_argument("--report", type=Path, required=True)
    load_calls_parser.add_argument("--run-id", required=True)

    load_objects_parser = subparsers.add_parser(
        "load-objects", help="Load object type routes and core object tables."
    )
    load_objects_parser.add_argument("--root", type=Path, default=Path("original_data"))
    load_objects_parser.add_argument("--db", type=Path, required=True)
    load_objects_parser.add_argument("--report", type=Path, required=True)
    load_objects_parser.add_argument("--run-id", required=True)

    load_npc_parser = subparsers.add_parser(
        "load-npc-target", help="Load NPCs, targets and quest endpoints."
    )
    load_npc_parser.add_argument("--root", type=Path, default=Path("original_data"))
    load_npc_parser.add_argument("--db", type=Path, required=True)
    load_npc_parser.add_argument("--report", type=Path, required=True)
    load_npc_parser.add_argument("--run-id", required=True)

    load_items_parser = subparsers.add_parser(
        "load-items-rewards", help="Load canonical items and reward slots."
    )
    load_items_parser.add_argument("--root", type=Path, default=Path("original_data"))
    load_items_parser.add_argument("--db", type=Path, required=True)
    load_items_parser.add_argument("--report", type=Path, required=True)
    load_items_parser.add_argument("--run-id", required=True)

    validate = subparsers.add_parser("validate", help="Validate normalized data.")
    validate.add_argument("--db", type=Path, required=True)
    validate.add_argument(
        "--scope",
        choices=["quest", "text", "objects", "npc-target", "items", "all"],
    )
    validate.add_argument("--all", action="store_true", dest="validate_all")
    validate.add_argument("--strict-p0", action="store_true")
    validate.add_argument("--reports-dir", type=Path, default=Path("reports"))

    sample_pack = subparsers.add_parser(
        "sample-pack", help="Generate the G02 MVP sample review pack."
    )
    sample_pack.add_argument("--db", type=Path, required=True)
    sample_pack.add_argument("--html", type=Path, required=True)
    sample_pack.add_argument("--json", type=Path, required=True)
    sample_pack.add_argument("--run-id", required=True)

    for command, help_text in [
        ("load-relations", "Load task chain, task-object and conflict relations."),
        ("load-groups", "Load condition, required-object and objective groups."),
        ("load-mappings", "Load extended objects and explicit mappings."),
        ("load-locations", "Load area, province, scene and target locations."),
        ("load-unresolved", "Capture unresolved flag references and dependencies."),
    ]:
        command_parser = subparsers.add_parser(command, help=help_text)
        command_parser.add_argument("--root", type=Path, default=Path("original_data"))
        command_parser.add_argument("--db", type=Path, required=True)
        command_parser.add_argument("--report", type=Path, required=True)
        command_parser.add_argument("--run-id", required=True)

    special = subparsers.add_parser(
        "load-special", help="Load all remaining quest configuration files."
    )
    special.add_argument("--root", type=Path, default=Path("original_data"))
    special.add_argument("--db", type=Path, required=True)
    special.add_argument("--report", type=Path, required=True)
    special.add_argument("--run-id", required=True)

    quality = subparsers.add_parser(
        "quality-report", help="Generate the full P0/P1/P2 quality report."
    )
    quality.add_argument("--db", type=Path, required=True)
    quality.add_argument("--reports-dir", type=Path, default=Path("reports"))
    quality.add_argument("--json", type=Path, required=True)
    quality.add_argument("--html", type=Path, required=True)
    quality.add_argument("--csv", type=Path, required=True)
    quality.add_argument("--run-id", required=True)

    views = subparsers.add_parser(
        "install-views", help="Install aggregate and detail query views."
    )
    views.add_argument("--db", type=Path, required=True)

    rebuild = subparsers.add_parser(
        "rebuild", help="Rebuild twice and verify deterministic normalized content."
    )
    rebuild.add_argument("--root", type=Path, default=Path("original_data"))
    rebuild.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/quest_database/reproducibility/manual"),
    )
    rebuild.add_argument(
        "--report", type=Path, default=Path("reports/reproducibility.json")
    )
    rebuild.add_argument(
        "--html", type=Path, default=Path("reports/regression.html")
    )
    rebuild.add_argument("--run-id", default="deterministic-check")
    rebuild.add_argument("--verify-deterministic", action="store_true")

    release = subparsers.add_parser("release", help="Create a versioned release package.")
    release.add_argument("--workspace", type=Path, default=Path("."))
    release.add_argument("--db", type=Path, required=True)
    release.add_argument("--release-dir", type=Path, required=True)
    release.add_argument("--version", required=True)
    release.add_argument("--run-id", required=True)

    finalize_release = subparsers.add_parser(
        "finalize-release", help="Refresh final execution audit and release checksums."
    )
    finalize_release.add_argument("--workspace", type=Path, default=Path("."))
    finalize_release.add_argument("--release-dir", type=Path, required=True)
    finalize_release.add_argument("--version", required=True)
    finalize_release.add_argument("--run-id", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "inventory":
        summary = run_inventory(
            root=args.root,
            output_dir=args.output,
            run_id=args.run_id,
            strict=args.strict,
        )
        print(
            f"inventory ok: files={summary['file_count']} "
            f"text_files={summary['text_file_count']} run_id={summary['run_id']}"
        )
        return 0
    if args.command == "init-db":
        summary = init_database(args.db, run_id=args.run_id)
        print(
            f"database initialized: tables={summary['table_count']} "
            f"integrity={summary['integrity_check']}"
        )
        return 0
    if args.command == "load-quest":
        summary = load_quest(
            root=args.root,
            db_path=args.db,
            report_path=args.report,
            run_id=args.run_id,
        )
        print(
            f"quest load ok: rows={summary['quest_rows']} "
            f"unique={summary['unique_quest_ids']} "
            f"duplicates={len(summary['duplicate_quest_ids'])}"
        )
        return 0
    if args.command == "load-text-category":
        summary = load_text_and_categories(
            root=args.root,
            db_path=args.db,
            report_path=args.report,
            run_id=args.run_id,
        )
        print(
            f"text/category load ok: matched={summary['matched_quest_ids']} "
            f"missing={summary['missing_text_quest_ids']} "
            f"extra={summary['extra_text_ids']} "
            f"categories={summary['matched_in_use_category_ids']}"
        )
        return 0
    if args.command == "load-character-calls":
        summary = load_character_calls(
            root=args.root,
            db_path=args.db,
            report_path=args.report,
            run_id=args.run_id,
        )
        print(
            f"character calls ok: profiles={summary['profile_count']} "
            f"variants={summary['variant_count']}"
        )
        return 0
    if args.command == "load-objects":
        summary = load_objects(
            root=args.root,
            db_path=args.db,
            report_path=args.report,
            run_id=args.run_id,
        )
        print(
            f"object load ok: types={summary['counts']['object_type']} "
            f"required_routes={summary['required_routes_ok']} "
            f"unknown={len(summary['unknown_route_types'])}"
        )
        return 0
    if args.command == "load-npc-target":
        summary = load_npc_and_targets(
            root=args.root,
            db_path=args.db,
            report_path=args.report,
            run_id=args.run_id,
        )
        print(
            f"npc/target load ok: npc_refs={summary['unique_referenced_npc_ids']} "
            f"npc_missing={len(summary['missing_referenced_npc_ids'])} "
            f"targets={summary['unique_referenced_target_ids']} "
            f"target_missing={len(summary['missing_referenced_target_ids'])}"
        )
        return 0
    if args.command == "load-items-rewards":
        summary = load_items_and_rewards(
            root=args.root,
            db_path=args.db,
            report_path=args.report,
            run_id=args.run_id,
        )
        print(
            f"item/reward load ok: items={summary['canonical_item_rows']} "
            f"reward_items={summary['unique_reward_item_ids']} "
            f"missing={len(summary['missing_reward_item_ids'])}"
        )
        return 0
    if args.command == "validate":
        scope = "all" if args.validate_all else args.scope
        if scope is None:
            raise SystemExit("validate requires --scope <name> or --all")
        summary = (
            strict_p0_validation(args.db, args.reports_dir)
            if args.strict_p0
            else validate_database(args.db, scope=scope)
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["status"] == "ok" else 1
    if args.command == "sample-pack":
        summary = generate_g02_sample_pack(
            db_path=args.db,
            html_path=args.html,
            json_path=args.json,
            run_id=args.run_id,
        )
        print(
            f"sample pack ok: quests={len(summary['sample_quest_ids'])} "
            f"versions={summary['sample_version_count']} "
            f"fk={summary['metrics']['foreign_key_violations']}"
        )
        return 0
    if args.command == "load-relations":
        summary = load_relations(
            root=args.root, db_path=args.db, report_path=args.report, run_id=args.run_id
        )
        print(
            f"relations ok: next={summary['unique_next_quest_refs']} "
            f"task_refs={summary['unique_task_object_refs']} "
            f"cycles={len(summary['next_relation_cycles'])}"
        )
        return 0
    if args.command == "load-groups":
        summary = load_groups(
            root=args.root, db_path=args.db, report_path=args.report, run_id=args.run_id
        )
        print(
            f"groups ok: conditions="
            f"{summary['counts'].get('precondition',0)+summary['counts'].get('required_object',0)} "
            f"objectives={summary['counts'].get('objective',0)} "
            f"anomalies={summary['anomaly_count']}"
        )
        return 0
    if args.command == "load-mappings":
        summary = load_mappings(
            root=args.root, db_path=args.db, report_path=args.report, run_id=args.run_id
        )
        print(
            f"mappings ok: npc_rows={summary['counts'].get('npc_mapping',0)} "
            f"missing_actual={summary['npc_mapping_missing_actual_count']} "
            f"missing_quest_npc={summary['npc_mapping_missing_quest_npc_count']}"
        )
        return 0
    if args.command == "load-locations":
        summary = load_locations(
            root=args.root, db_path=args.db, report_path=args.report, run_id=args.run_id
        )
        print(
            f"locations ok: areas={summary['counts'].get('area',0)} "
            f"referenced={summary['unique_referenced_area_ids']} "
            f"missing={len(summary['missing_referenced_area_ids'])}"
        )
        return 0
    if args.command == "load-special":
        summary = load_special_configs(
            root=args.root, db_path=args.db, report_path=args.report, run_id=args.run_id
        )
        print(
            f"special configs ok: files={summary['file_count']} "
            f"quest_rows={summary['quest_count_before']}->{summary['quest_count_after']}"
        )
        return 0
    if args.command == "load-unresolved":
        summary = load_unresolved_references(
            root=args.root, db_path=args.db, report_path=args.report, run_id=args.run_id
        )
        print(
            f"unresolved refs ok: rows={summary['unresolved_reference_rows']} "
            f"dependencies={len(summary['dependencies'])}"
        )
        return 0
    if args.command == "quality-report":
        summary = generate_quality_report(
            db_path=args.db,
            reports_dir=args.reports_dir,
            json_path=args.json,
            html_path=args.html,
            csv_path=args.csv,
            run_id=args.run_id,
        )
        print(
            f"quality report: status={summary['status']} "
            f"p0_failures={len(summary['p0_failures'])} "
            f"issues={len(summary['issues'])}"
        )
        return 0 if summary["status"] == "p0_passed" else 1
    if args.command == "install-views":
        summary = install_views(args.db)
        query_summary = validate_query_interfaces(args.db)
        print(
            f"views installed: count={summary['view_count']} "
            f"integrity={summary['integrity_check']} queries={query_summary['status']}"
        )
        return 0 if query_summary["status"] == "ok" else 1
    if args.command == "rebuild":
        if not args.verify_deterministic:
            raise SystemExit("rebuild requires --verify-deterministic")
        summary = verify_deterministic_rebuild(
            root=args.root,
            output_dir=args.output_dir,
            report_path=args.report,
            html_path=args.html,
            run_id=args.run_id,
        )
        print(
            f"rebuild verification: status={summary['status']} "
            f"schema_equal={summary['comparisons']['schema_hash_equal']} "
            f"content_equal={summary['comparisons']['logical_content_hash_equal']}"
        )
        return 0 if summary["status"] == "ok" else 1
    if args.command == "release":
        summary = create_release(
            workspace=args.workspace.resolve(),
            db_path=args.db.resolve(),
            release_dir=args.release_dir.resolve(),
            version=args.version,
            run_id=args.run_id,
        )
        print(
            f"release ok: version={summary['version']} "
            f"artifacts={summary['artifact_count']} "
            f"checksums={summary['checksums_ok']} "
            f"p0={summary['strict_p0_status']}"
        )
        return 0
    if args.command == "finalize-release":
        summary = finalize_release_audit(
            workspace=args.workspace.resolve(),
            release_dir=args.release_dir.resolve(),
            version=args.version,
            run_id=args.run_id,
        )
        print(
            f"release audit finalized: version={summary['version']} "
            f"artifacts={summary['artifact_count']} "
            f"checksums={summary['checksums_ok']} "
            f"p0={summary['strict_p0_status']}"
        )
        return 0 if summary["checksums_ok"] and summary["strict_p0_status"] == "ok" else 1
    if args.command == "validate-schema":
        summary = write_schema_outputs(
            quest_info=args.quest_info,
            index_list=args.index_list,
            quest_dir=args.quest_dir,
            output_dir=args.output_dir,
        )
        print(
            f"schema ok: columns={summary['column_count']} "
            f"rows={summary['data_row_count']} "
            f"unique_ids={summary['unique_quest_id_count']} "
            f"duplicates={len(summary['duplicate_quest_ids'])}"
        )
        return 0
    if args.command == "load-raw":
        summary = load_raw(
            inventory_path=args.inventory,
            profiles_path=args.profiles,
            output_db=args.output_db,
            manifest_path=args.manifest,
            check=args.check,
        )
        print(
            f"raw load ok: files={summary['file_count']} "
            f"rows={summary['row_count']} cells={summary['cell_count']} "
            f"quest_info={summary['validation']['quest_info_data_rows']}"
        )
        return 0
    if args.command == "profile":
        summary = run_profile(
            inventory_path=args.inventory,
            output_dir=args.output,
            check=args.check,
        )
        print(
            f"profile ok: files={summary['profile_count']} "
            f"errors={summary['error_count']} "
            f"star_files={summary['files_with_star_delimited_columns']}"
        )
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")
