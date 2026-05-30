"""Test helpers for creating typed GraphState fixtures."""

from __future__ import annotations

from typing import cast

from health_importer.graph.state import GraphState


def make_test_state(**kwargs) -> GraphState:
    """Return a GraphState with required keys and any overrides."""
    return cast(
        GraphState,
        {
            "file_path": "/tmp/test.pdf",
            "status": "NEW",
            "events": [],
            **kwargs,
        },
    )
