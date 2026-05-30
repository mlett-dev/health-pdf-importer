from __future__ import annotations

import argparse
from pathlib import Path

from health_importer.commands.common import effective_anytype_dry_run, safe_json_dumps, scan_once
from health_importer.config import ConfigError, load_config


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        config = load_config(Path(args.config))
        anytype_dry_run = effective_anytype_dry_run(config.anytype.dry_run, args)
    except ConfigError as exc:
        parser.error(str(exc))
    results = scan_once(
        config, wait_seconds=args.wait_seconds, anytype_dry_run=anytype_dry_run
    )
    print(safe_json_dumps({"ok": True, "count": len(results), "results": results}))
    return 0
