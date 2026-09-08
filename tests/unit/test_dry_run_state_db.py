"""A dry run must not write into the productive state database.

--dry-run only suppresses Anytype writes; registration and status are persisted
either way. With a shared database a dry run marks the document DONE, and the
productive run that follows skips it as a duplicate -- so the document can never
be imported. That happened to a real invoice, which is why the paths diverge.
"""

import types
from pathlib import Path

from health_importer.commands.common import state_db_path_for


def _config(path: str):
    return types.SimpleNamespace(state_db=types.SimpleNamespace(path=Path(path)))


def test_productive_run_uses_the_configured_database() -> None:
    config = _config("/data/state_filestorage.sqlite")
    assert state_db_path_for(config, False) == Path("/data/state_filestorage.sqlite")


def test_dry_run_uses_a_separate_database_beside_it() -> None:
    config = _config("/data/state_filestorage.sqlite")
    assert state_db_path_for(config, True) == Path("/data/state_filestorage.dryrun.sqlite")


def test_dry_run_path_differs_from_the_productive_one() -> None:
    config = _config("/data/state.sqlite")
    assert state_db_path_for(config, True) != state_db_path_for(config, False)


def test_suffixless_database_path_still_diverges() -> None:
    config = _config("/data/statedb")
    assert state_db_path_for(config, True) == Path("/data/statedb.dryrun")
