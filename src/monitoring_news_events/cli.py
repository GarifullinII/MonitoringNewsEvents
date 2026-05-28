from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_project_config
from .pipeline import MonitoringPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="news-monitor",
        description="AI-monitoring of info reasons and report generation by GEO.",
    )
    parser.add_argument(
        "--config",
        default="configs/project.example.toml",
        help="Path to TOML config file.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-geos", help="Show configured GEO ids.")
    list_parser.set_defaults(command="list-geos")

    run_parser = subparsers.add_parser("run", help="Generate a report for one GEO.")
    run_parser.add_argument("--geo", required=True, help="GEO id from config.")
    run_parser.add_argument("--notify", action="store_true", help="Send Slack/Telegram notifications if configured.")
    run_parser.add_argument("--disable-llm", action="store_true", help="Force heuristic-only mode.")
    run_parser.set_defaults(command="run")

    run_all_parser = subparsers.add_parser("run-all", help="Generate reports for all configured GEOs.")
    run_all_parser.add_argument("--notify", action="store_true", help="Send Slack/Telegram notifications if configured.")
    run_all_parser.add_argument("--disable-llm", action="store_true", help="Force heuristic-only mode.")
    run_all_parser.set_defaults(command="run-all")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_project_config(Path(args.config))
    pipeline = MonitoringPipeline(config)

    if args.command == "list-geos":
        for geo in config.geos:
            print(f"{geo.id}\t{geo.name}")
        return 0

    if args.command == "run":
        artifact = pipeline.run(args.geo, notify=args.notify, force_disable_llm=args.disable_llm)
        print(f"GEO: {artifact.report.geo_name}")
        print(f"Signals: {len(artifact.report.raw_signals)}")
        print(f"Ideas: {len(artifact.report.angles)}")
        print(f"Headlines: {len(artifact.report.headlines)}")
        print(f"Markdown: {artifact.markdown_path}")
        print(f"JSON: {artifact.json_path}")
        if artifact.airtable_report_id:
            print(f"Airtable record: {artifact.airtable_report_id}")
        if artifact.airtable_report_url:
            print(f"Airtable link: {artifact.airtable_report_url}")
        return 0

    if args.command == "run-all":
        for geo in config.geos:
            artifact = pipeline.run(geo.id, notify=args.notify, force_disable_llm=args.disable_llm)
            destination = artifact.airtable_report_url or str(artifact.markdown_path)
            print(f"{geo.id}\t{destination}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 1
