"""IMAP email provider for creating drafts in mailboxes (GMX, Gmail, etc.)."""

from __future__ import annotations

import logging
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import imapclient

from health_importer.email import DraftMessage, EmailProvider

logger = logging.getLogger(__name__)


class EmailProviderError(Exception):
    """Raised when an email provider operation fails."""


_DRAFT_FOLDER_FALLBACKS = [
    "Drafts",
    "Entwürfe",
    "[Gmail]/Drafts",
    "[Gmail]/Entwürfe",
    "[Google Mail]/Entwürfe",
    "Draft",
    "Entwurf",
]


class IMAPProvider(EmailProvider):
    """Create drafts via IMAP using imapclient."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        draft_folder_name: str | None = None,
        from_addr: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.draft_folder_name = draft_folder_name
        self.from_addr = from_addr or username

    def create_draft(self, draft: DraftMessage) -> str:
        try:
            client = imapclient.IMAPClient(self.host, port=self.port, ssl=True)
            client.login(self.username, self.password)
        except Exception as exc:
            raise EmailProviderError(f"IMAP login failed for {self.host}: {exc}") from exc

        try:
            folder = self._resolve_draft_folder(client)
            msg_bytes = _build_mime_message(draft, from_addr=self.from_addr)
            uid = client.append(folder, msg_bytes, flags=[b"\\Draft"])
            draft_id = f"imap:{folder}:{uid}"
            logger.info("IMAP draft created: %s", draft_id)
            return draft_id
        finally:
            client.logout()

    def health_check(self) -> bool:
        try:
            client = imapclient.IMAPClient(self.host, port=self.port, ssl=True)
            client.login(self.username, self.password)
            client.logout()
            return True
        except Exception:
            return False

    def _resolve_draft_folder(self, client) -> str:
        folders = client.list_folders()
        folder_names = [f[2] for f in folders]

        if self.draft_folder_name and self.draft_folder_name in folder_names:
            return self.draft_folder_name

        for candidate in _DRAFT_FOLDER_FALLBACKS:
            if candidate in folder_names:
                logger.info(
                    "Draft folder resolved to fallback '%s' (requested '%s')",
                    candidate,
                    self.draft_folder_name,
                )
                return candidate

        raise EmailProviderError(f"No drafts folder found. Available: {folder_names}")


def _build_mime_message(draft: DraftMessage, from_addr: str) -> bytes:
    msg = MIMEMultipart("mixed")
    msg["Subject"] = draft.subject
    msg["To"] = draft.to
    msg["From"] = from_addr

    text_part = MIMEText(draft.body_text, "plain", "utf-8")
    msg.attach(text_part)

    for att_path in draft.attachments:
        if att_path.exists():
            data = att_path.read_bytes()
            part = MIMEApplication(data, _subtype="pdf")
            part.add_header(
                "Content-Disposition",
                "attachment",
                filename=att_path.name,
            )
            msg.attach(part)

    return msg.as_bytes()


def _get_password(password_env_key: str) -> str:
    password = os.environ.get(password_env_key)
    if not password:
        raise EmailProviderError(f"Environment variable {password_env_key} is not set")
    return password
