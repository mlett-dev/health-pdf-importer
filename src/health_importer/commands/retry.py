from __future__ import annotations

import argparse
from pathlib import Path

from health_importer.commands.common import (
    effective_anytype_dry_run,
    move_to_final_folder,
    run_once_with_config,
    safe_json_dumps,
)
from health_importer.config import ConfigError, load_config
from health_importer.state_db import StateDb
from health_importer.workflow.corrections import load_correction_file


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        config = load_config(Path(args.config))
        anytype_dry_run = effective_anytype_dry_run(config.anytype.dry_run, args)
        corrections = load_correction_file(args.correction) if args.correction else {}
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    db = StateDb(config.state_db.path)
    db.initialize()
    try:
        record = db.get_file(args.file_id)
    except KeyError as exc:
        parser.error(str(exc))
    if corrections:
        db.add_event(record.id, "manual_correction_applied", {"keys": sorted(corrections)})
    result = run_once_with_config(
        Path(record.current_path),
        config,
        anytype_dry_run=anytype_dry_run,
        correction_overrides=corrections,
    )
    result = move_to_final_folder(Path(record.current_path), config, result)
    result["anytype_dry_run"] = anytype_dry_run
    result["retried_file_id"] = record.id
    print(safe_json_dumps(result))
    return 0 if result["ok"] else 1
