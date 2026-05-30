"""Email providers for Pkv draft generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DraftMessage:
    to: str
    subject: str
    body_text: str
    body_html: str | None = None
    attachments: list[Path] = field(default_factory=list)
    draft_id: str | None = None
    from_addr: str | None = None


class EmailProvider:
    """Base class for email providers."""

    def create_draft(self, draft: DraftMessage) -> str:
        """Create a draft email. Returns draft_id or local path."""
        raise NotImplementedError

    def health_check(self) -> bool:
        """Verify provider connectivity."""
        return True


class FileOnlyProvider(EmailProvider):
    """Save drafts as local markdown files. Always available."""

    def __init__(self, draft_folder: Path) -> None:
        self.draft_folder = draft_folder

    def create_draft(self, draft: DraftMessage) -> str:
        self.draft_folder.mkdir(parents=True, exist_ok=True)
        filename = _safe_filename(draft.subject) + ".md"
        path = self.draft_folder / filename
        counter = 1
        while path.exists():
            path = self.draft_folder / f"{_safe_filename(draft.subject)}_{counter}.md"
            counter += 1

        lines = [
            f"# E-Mail Entwurf: {draft.subject}",
            "",
            f"**An:** {draft.to}",
            f"**Betreff:** {draft.subject}",
            "",
            "---",
            "",
        ]
        if draft.attachments:
            lines.extend(["**Anhänge:**", ""])
            for att in draft.attachments:
                lines.append(f"- `{att.name}`")
            lines.extend(["", "---", ""])
        lines.extend([draft.body_text, ""])

        path.write_text("\n".join(lines), encoding="utf-8")
        return str(path)


def _safe_filename(value: str) -> str:
    """Create a safe filename from a string."""
    import re

    safe = re.sub(r"[^\w\s-]", "", value).strip()
    safe = re.sub(r"[-\s]+", "_", safe)
    return safe[:80] or "draft"


def build_provider(config) -> EmailProvider:
    """Build an email provider from config."""
    import logging
    from pathlib import Path

    from health_importer.config import EmailConfig
    from health_importer.email.imap_provider import IMAPProvider

    logger = logging.getLogger(__name__)

    if isinstance(config, dict):
        _default_body = (
            "Sehr geehrte Damen und Herren,\n\n"
            "hiermit reiche ich die Wahlarztrechnung für {patient} ein.\n\n"
            "{details}\n\n"
            "Mit freundlichen Grüßen,\n\n"
        )
        config = EmailConfig(
            enabled=config.get("enabled", False),
            provider=config.get("provider", "file_only"),
            draft_folder=Path(config.get("draft_folder", "review/drafts")),
            pkv_recipient=config.get("pkv_recipient", "pkv-service@example.invalid"),
            pkv_subject_template=config.get(
                "pkv_subject_template", "Einreichung Wahlarztrechnung — {patient} — {date}"
            ),
            pkv_body_template=config.get("pkv_body_template", _default_body),
            pkv_sender_name=config.get("pkv_sender_name", ""),
            pkv_sender_policy_number=config.get("pkv_sender_policy_number", ""),
            smtp_config=config.get("smtp_config"),
        )
    elif not isinstance(config, EmailConfig):
        raise TypeError(f"Expected EmailConfig or dict, got {type(config).__name__}")
    if not config.enabled:
        return FileOnlyProvider(config.draft_folder)
    if config.provider == "file_only":
        return FileOnlyProvider(config.draft_folder)

    imap_cfg = config.smtp_config or {}
    password_env_key = imap_cfg.get("password_env_key", "EMAIL_PASSWORD")
    password = _env_or_none(password_env_key)
    username = imap_cfg.get("username", "")

    if config.provider == "gmx":
        if not password:
            logger.warning(
                "GMX password not set in env %s, falling back to FileOnlyProvider", password_env_key
            )
            return FileOnlyProvider(config.draft_folder)
        return IMAPProvider(
            host=imap_cfg.get("host", "imap.gmx.net"),
            port=imap_cfg.get("port", 993),
            username=username,
            password=password,
            draft_folder_name=imap_cfg.get("draft_folder_name") or "Entwürfe",
            from_addr=imap_cfg.get("from_addr"),
        )

    if config.provider == "gmail":
        if not password:
            logger.warning(
                "Gmail password not set in env %s, falling back to FileOnlyProvider",
                password_env_key,
            )
            return FileOnlyProvider(config.draft_folder)
        return IMAPProvider(
            host=imap_cfg.get("host", "imap.gmail.com"),
            port=imap_cfg.get("port", 993),
            username=username,
            password=password,
            draft_folder_name=imap_cfg.get("draft_folder_name") or "[Gmail]/Drafts",
            from_addr=imap_cfg.get("from_addr"),
        )

    if config.provider == "imap":
        if not password:
            logger.warning(
                "IMAP password not set in env %s, falling back to FileOnlyProvider",
                password_env_key,
            )
            return FileOnlyProvider(config.draft_folder)
        return IMAPProvider(
            host=imap_cfg.get("host", ""),
            port=imap_cfg.get("port", 993),
            username=username,
            password=password,
            draft_folder_name=imap_cfg.get("draft_folder_name"),
            from_addr=imap_cfg.get("from_addr"),
        )

    # Fallback for unknown providers
    logger.warning("Unknown email provider '%s', falling back to FileOnlyProvider", config.provider)
    return FileOnlyProvider(config.draft_folder)


def _env_or_none(key: str) -> str | None:
    import os

    return os.environ.get(key)
