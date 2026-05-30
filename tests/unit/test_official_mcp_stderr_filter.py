import io

from health_importer.anytype.official_mcp_stderr_filter import _forward_filtered_stderr


def test_official_mcp_stderr_filter_suppresses_debug_blocks(monkeypatch) -> None:
    captured = io.StringIO()
    monkeypatch.setattr("sys.stderr", captured)
    stderr = io.BytesIO(
        b"Initializing Anytype MCP Server...\n"
        b"calling tool {\n"
        b"  name: 'API-add-list-objects',\n"
        b"  arguments: { objects: [ 'id' ] }\n"
        b"}\n"
        b"operations {\n"
        b"  'API-create-object': { description: '...' }\n"
        b"}\n"
        b"operation finished\n"
        b"Error in tool call Error: boom\n"
    )

    _forward_filtered_stderr(stderr)

    assert captured.getvalue() == "Error in tool call Error: boom\n"
