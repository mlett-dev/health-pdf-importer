from __future__ import annotations

import subprocess
import sys
import threading
from collections.abc import Iterable

_BLOCK_LOG_PREFIXES = (
    "calling tool {",
    "operations {",
    "prepareFileUpload {",
    "calling operation {",
    "extracting ",
)
_LINE_LOG_PREFIXES = (
    "Initializing Anytype MCP Server...",
    "Using base URL from ANYTYPE_API_BASE_URL:",
    "Anytype MCP Server running on stdio",
    "operation finished",
)


def main(argv: Iterable[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        print("Usage: official_mcp_stderr_filter <command> [args...]", file=sys.stderr)
        return 2

    process = subprocess.Popen(
        args,
        stdin=sys.stdin.buffer,
        stdout=sys.stdout.buffer,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    assert process.stderr is not None

    stderr_thread = threading.Thread(
        target=_forward_filtered_stderr,
        args=(process.stderr,),
        daemon=True,
    )
    stderr_thread.start()
    return_code = process.wait()
    stderr_thread.join(timeout=1)
    return return_code


def _forward_filtered_stderr(stderr) -> None:
    suppressed_brace_depth = 0
    for raw_line in stderr:
        line = raw_line.decode(errors="replace")
        stripped = line.strip()
        if suppressed_brace_depth > 0:
            suppressed_brace_depth += _brace_delta(stripped)
            if suppressed_brace_depth <= 0:
                suppressed_brace_depth = 0
            continue
        if _is_single_line_noise(stripped):
            continue
        if _is_block_noise_start(stripped):
            suppressed_brace_depth = max(1, _brace_delta(stripped))
            continue
        sys.stderr.write(line)
        sys.stderr.flush()


def _is_single_line_noise(line: str) -> bool:
    return any(line.startswith(prefix) for prefix in _LINE_LOG_PREFIXES)


def _is_block_noise_start(line: str) -> bool:
    return any(line.startswith(prefix) for prefix in _BLOCK_LOG_PREFIXES)


def _brace_delta(line: str) -> int:
    return line.count("{") - line.count("}")


if __name__ == "__main__":
    raise SystemExit(main())
