from __future__ import annotations

import argparse
import json
from pathlib import Path

from health_importer.config import ConfigError, load_config
from health_importer.workflow.filesystem import cleanup_temporary_artifacts


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        config = load_config(Path(args.config))
        removed = cleanup_temporary_artifacts(
            config.folders.processing,
            older_than_hours=args.older_than_hours,
        )
    except (ConfigError, ValueError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {"ok": True, "count": len(removed), "removed": [str(path) for path in removed]},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0
