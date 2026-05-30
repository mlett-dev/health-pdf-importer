from __future__ import annotations

import argparse
import json
from pathlib import Path

from health_importer.config import (
    ConfigError,
    check_placeholder_values,
    check_production_warnings,
    load_config,
)


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        config = load_config(Path(args.config), raise_on_placeholder=False)
    except ConfigError as exc:
        parser.error(str(exc))

    placeholder_errors = check_placeholder_values(config)
    if placeholder_errors:
        print(
            json.dumps(
                {
                    "ok": False,
                    "errors": placeholder_errors,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    warnings = check_production_warnings(config)
    if warnings:
        print(
            json.dumps(
                {
                    "ok": True,
                    "collection_name": config.anytype.collection_name,
                    "warnings": warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"Configuration OK: {config.anytype.collection_name}")
    return 0
