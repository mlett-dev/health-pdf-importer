from __future__ import annotations

import argparse
from pathlib import Path

from health_importer.commands.common import effective_anytype_dry_run, run_once_with_config, safe_json_dumps
from health_importer.config import ConfigError, load_config
from health_importer.workflow.goldstandard import run_goldstandard_evaluation


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        config = load_config(Path(args.config))
        anytype_dry_run = effective_anytype_dry_run(config.anytype.dry_run, args)
        report = run_goldstandard_evaluation(
            args.pdf_dir,
            args.expected_dir,
            lambda pdf_path: run_once_with_config(
                pdf_path,
                config,
                anytype_dry_run=anytype_dry_run,
            ),
        )
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    report["anytype_dry_run"] = anytype_dry_run
    print(safe_json_dumps(report))
    return 0
