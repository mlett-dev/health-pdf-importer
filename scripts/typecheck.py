#!/usr/bin/env python3
"""Run pyright on the currently whitelisted modules and report results."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    print("Running pyright on whitelisted modules...")
    result = subprocess.run(
        [sys.executable, "-m", "pyright"],
        capture_output=False,
        text=True,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
