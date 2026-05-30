"""Tests for email CLI commands."""

from pathlib import Path

from health_importer.cli import build_parser, main
from health_importer.commands.common import list_email_drafts


def test_email_drafts_lists_local_markdown(tmp_path: Path) -> None:
    draft_dir = tmp_path / "review" / "drafts"
    draft_dir.mkdir(parents=True)
    (draft_dir / "draft_1.md").write_text("Draft 1")
    (draft_dir / "draft_2.md").write_text("Draft 2")
    (draft_dir / "other.txt").write_text("Not a draft")

    class FakeConfig:
        class email:
            draft_folder = draft_dir

    drafts = list_email_drafts(FakeConfig())
    assert len(drafts) == 2
    assert drafts[0]["name"] == "draft_1.md"
    assert drafts[1]["name"] == "draft_2.md"
    assert all(d["type"] == "local_markdown" for d in drafts)


def test_email_drafts_empty_folder() -> None:
    class FakeConfig:
        class email:
            draft_folder = Path("/nonexistent")

    drafts = list_email_drafts(FakeConfig())
    assert drafts == []


def test_email_send_returns_not_implemented() -> None:
    result = main(["email-send", "some-draft-id"])
    assert result == 1


def test_email_send_all_requires_yes() -> None:
    result = main(["email-send-all"])
    assert result == 1


def test_email_send_all_with_yes_returns_not_implemented() -> None:
    result = main(["email-send-all", "--yes"])
    assert result == 1


def test_parser_has_email_commands() -> None:
    parser = build_parser()
    args = parser.parse_args(["email-drafts"])
    assert args.command == "email-drafts"

    args = parser.parse_args(["email-send", "draft-123"])
    assert args.command == "email-send"
    assert args.draft_id == "draft-123"

    args = parser.parse_args(["email-send-all"])
    assert args.command == "email-send-all"
    assert args.yes is False

    args = parser.parse_args(["email-send-all", "--yes"])
    assert args.yes is True
