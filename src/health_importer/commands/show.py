from __future__ import annotations

import argparse
from pathlib import Path

from health_importer.commands.common import record_to_json, safe_json_dumps
from health_importer.config import ConfigError, load_config
from health_importer.state_db import StateDb


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        config = load_config(Path(args.config))
    except ConfigError as exc:
        parser.error(str(exc))
    db = StateDb(config.state_db.path)
    db.initialize()
    try:
        record = db.get_file(args.file_id)
    except KeyError as exc:
        parser.error(str(exc))
    print(
        safe_json_dumps(
            {
                "ok": True,
                "record": record_to_json(record),
                "events": db.list_events(record.id),
            }
        )
    )
    return 0
