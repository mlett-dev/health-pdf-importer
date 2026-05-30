from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from health_importer import __version__
from health_importer.commands.cleanup import run as cleanup_run
from health_importer.commands.common import add_dry_run_flags
from health_importer.commands.config_check import run as config_check_run
from health_importer.commands.doctor import run as doctor_run
from health_importer.commands.email import drafts as email_drafts_run
from health_importer.commands.email import send as email_send_run
from health_importer.commands.email import send_all as email_send_all_run
from health_importer.commands.goldstandard import run as goldstandard_run
from health_importer.commands.retry import run as retry_run
from health_importer.commands.review_list import run as review_list_run
from health_importer.commands.run_once import run as run_once_run
from health_importer.commands.scan import run as scan_run
from health_importer.commands.show import run as show_run
from health_importer.commands.status import run as status_run
from health_importer.commands.watch import run as watch_run

_COMMANDS: dict[str, Callable] = {
    "config-check": config_check_run,
    "doctor": doctor_run,
    "cleanup": cleanup_run,
    "goldstandard": goldstandard_run,
    "review-list": review_list_run,
    "retry": retry_run,
    "status": status_run,
    "show": show_run,
    "run-once": run_once_run,
    "scan-inbox": scan_run,
    "watch": watch_run,
    "email-drafts": email_drafts_run,
    "email-send": email_send_run,
    "email-send-all": email_send_all_run,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="health-importer",
        description="Local PDF importer for Wahlarzt invoices into Anytype.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--config",
        default="config/app.yaml",
        help="Path to the YAML configuration file.",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("config-check", help="Load and validate the configuration.")
    subparsers.add_parser("doctor", help="Check local runtime dependencies and configuration.")
    cleanup_parser = subparsers.add_parser("cleanup", help="Remove old temporary OCR/Vision files.")
    cleanup_parser.add_argument(
        "--older-than-hours",
        type=int,
        default=24,
        help="Remove temporary artifacts older than this many hours.",
    )
    goldstandard_parser = subparsers.add_parser(
        "goldstandard",
        help="Evaluate fixture PDFs against expected extraction JSON files.",
    )
    goldstandard_parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=Path("tests/fixtures/pdfs"),
        help="Directory containing fixture PDFs.",
    )
    goldstandard_parser.add_argument(
        "--expected-dir",
        type=Path,
        default=Path("tests/fixtures/expected_json"),
        help="Directory containing expected JSON files named like the PDFs.",
    )
    add_dry_run_flags(goldstandard_parser)
    subparsers.add_parser("review-list", help="List files currently waiting for review.")
    retry_parser = subparsers.add_parser("retry", help="Retry a file from the state database.")
    retry_parser.add_argument("file_id", type=int, help="State database file id to retry.")
    retry_parser.add_argument(
        "--correction",
        type=Path,
        help="Optional correction YAML file with manual field overrides.",
    )
    add_dry_run_flags(retry_parser)
    status_parser = subparsers.add_parser("status", help="Show recent file processing status.")
    status_parser.add_argument("--limit", type=int, default=10, help="Maximum records to show.")
    show_parser = subparsers.add_parser("show", help="Show one file record and its events.")
    show_parser.add_argument("file_id", type=int, help="State database file id to inspect.")
    run_once_parser = subparsers.add_parser("run-once", help="Run the import graph for one PDF.")
    run_once_parser.add_argument("pdf_path", help="Path to the PDF file to process.")
    add_dry_run_flags(run_once_parser)
    scan_parser = subparsers.add_parser("scan-inbox", help="Process stable PDFs already in Inbox.")
    scan_parser.add_argument(
        "--wait-seconds",
        type=float,
        default=2.0,
        help="Seconds to wait while checking whether a file is stable.",
    )
    add_dry_run_flags(scan_parser)
    watch_parser = subparsers.add_parser("watch", help="Continuously scan Inbox for stable PDFs.")
    watch_parser.add_argument(
        "--wait-seconds",
        type=float,
        default=2.0,
        help="Seconds to wait while checking whether a file is stable.",
    )
    watch_parser.add_argument(
        "--interval-seconds",
        type=float,
        default=30.0,
        help="Seconds to wait between inbox scans.",
    )
    watch_parser.add_argument(
        "--max-iterations",
        type=int,
        default=0,
        help="Stop after this many scan loops; 0 means run until interrupted.",
    )
    add_dry_run_flags(watch_parser)

    subparsers.add_parser("email-drafts", help="List created email drafts.")
    send_parser = subparsers.add_parser("email-send", help="Send a specific email draft.")
    send_parser.add_argument("draft_id", help="Draft ID to send (local path or imap:folder:uid).")
    sendall_parser = subparsers.add_parser("email-send-all", help="Send all pending email drafts.")
    sendall_parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    handler = _COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        return 0

    return handler(args, parser)


if __name__ == "__main__":
    raise SystemExit(main())
