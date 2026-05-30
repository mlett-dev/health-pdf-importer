from __future__ import annotations

import argparse
import time
from pathlib import Path

from health_importer.commands.common import effective_anytype_dry_run, safe_json_dumps, scan_once
from health_importer.config import ConfigError, load_config


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        config = load_config(Path(args.config))
        anytype_dry_run = effective_anytype_dry_run(config.anytype.dry_run, args)
    except ConfigError as exc:
        parser.error(str(exc))
    iterations = 0
    try:
        while True:
            results = scan_once(
                config,
                wait_seconds=args.wait_seconds,
                anytype_dry_run=anytype_dry_run,
            )
            print(
                safe_json_dumps({"ok": True, "count": len(results), "results": results}),
                flush=True,
            )
            iterations += 1
            if args.max_iterations and iterations >= args.max_iterations:
                return 0
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        return 0
