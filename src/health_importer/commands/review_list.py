from __future__ import annotations

import argparse
import json
from pathlib import Path

from health_importer.commands.common import record_to_json
from health_importer.config import ConfigError, load_config
from health_importer.state_db import StateDb


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        config = load_config(Path(args.config))
    except ConfigError as exc:
        parser.error(str(exc))
    db = StateDb(config.state_db.path)
    db.initialize()
    records = db.list_files(status="REVIEW")
    print(
        json.dumps(
            {
                "ok": True,
                "count": len(records),
                "results": [record_to_json(record) for record in records],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0
