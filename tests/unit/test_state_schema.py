"""Every STATE_* key must be declared in GraphState.

LangGraph filters the state to the TypedDict schema, so an undeclared key is
silently dropped between nodes. That is how the Befund flow lost its uploaded
file id and its file-naming config: the nodes ran, wrote the keys, and the next
node saw nothing -- no error anywhere, just a document that never got attached.
"""

import re
from pathlib import Path

from health_importer.graph.state import GraphState

_CONSTANT = re.compile(r'^(STATE_[A-Z0-9_]+) = "([a-z0-9_]+)"', re.MULTILINE)


def test_every_state_constant_is_declared_in_graphstate() -> None:
    source = Path("src/health_importer/graph/state.py").read_text(encoding="utf-8")
    constants = dict(_CONSTANT.findall(source))
    assert constants, "no STATE_* constants found -- has the file moved?"

    declared = set(GraphState.__annotations__)
    undeclared = {name: key for name, key in constants.items() if key not in declared}
    assert not undeclared, (
        "These STATE_* keys are missing from the GraphState TypedDict and will be "
        f"dropped between graph nodes: {undeclared}"
    )
