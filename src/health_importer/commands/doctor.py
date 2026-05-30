from __future__ import annotations

import argparse
from pathlib import Path

from health_importer.commands.common import doctor_report, safe_json_dumps
from health_importer.config import ConfigError, load_config


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        config = load_config(Path(args.config))
    except ConfigError as exc:
        parser.error(str(exc))
    report = doctor_report(config)
    print(safe_json_dumps(report))
    return 0 if report["ok"] else 1
