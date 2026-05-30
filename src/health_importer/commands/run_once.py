from __future__ import annotations

import argparse
from pathlib import Path

from health_importer.commands.common import effective_anytype_dry_run, run_once_with_config, safe_json_dumps
from health_importer.config import ConfigError, load_config


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        config = load_config(Path(args.config))
        anytype_dry_run = effective_anytype_dry_run(config.anytype.dry_run, args)
    except ConfigError as exc:
        parser.error(str(exc))
    result = run_once_with_config(
        Path(args.pdf_path),
        config,
        anytype_dry_run=anytype_dry_run,
    )
    result["anytype_dry_run"] = anytype_dry_run
    print(safe_json_dumps(result))
    return 0 if result["ok"] else 1
