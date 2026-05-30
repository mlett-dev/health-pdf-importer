from __future__ import annotations

import argparse
import json
from pathlib import Path

from health_importer.commands.common import list_email_drafts
from health_importer.config import ConfigError, load_config


def drafts(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        config = load_config(Path(args.config))
    except ConfigError as exc:
        parser.error(str(exc))
    drafts = list_email_drafts(config)
    print(
        json.dumps(
            {"ok": True, "count": len(drafts), "drafts": drafts},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def send(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    print(
        json.dumps(
            {
                "ok": False,
                "error": "SMTP sending is not implemented. "
                "IMAP drafts are available in your email client's Drafts folder. "
                "Please send from there.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1


def send_all(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not args.yes:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "email-send-all requires --yes. SMTP sending is not implemented. "
                    "Please send drafts from your email client.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "ok": False,
                "error": "SMTP sending is not implemented. "
                "Please send drafts from your email client.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1
