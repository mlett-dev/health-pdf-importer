"""Tests for IMAP email provider."""

from email import message_from_bytes
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from health_importer.email import DraftMessage, FileOnlyProvider, build_provider
from health_importer.email.imap_provider import (
    EmailProviderError,
    IMAPProvider,
    _build_mime_message,
)


def test_build_mime_message_basic() -> None:
    from email.header import decode_header

    draft = DraftMessage(
        to="pkv-service@example.invalid",
        subject="Einreichung — Max",
        body_text="Sehr geehrte Damen und Herren,\n\nhier die Rechnung.",
    )
    msg_bytes = _build_mime_message(draft, from_addr="sender@example.invalid")
    msg = message_from_bytes(msg_bytes)
    assert msg["To"] == "pkv-service@example.invalid"
    assert msg["From"] == "sender@example.invalid"
    decoded_subject = decode_header(msg["Subject"])[0][0]
    if isinstance(decoded_subject, bytes):
        decoded_subject = decoded_subject.decode("utf-8")
    assert decoded_subject == "Einreichung — Max"
    assert msg.get_content_type() == "multipart/mixed"
    body_part = msg.get_payload(0)
    assert isinstance(body_part, Message)
    payload = body_part.get_payload(decode=True)
    assert isinstance(payload, bytes)
    assert payload.decode("utf-8") == draft.body_text


def test_build_mime_message_with_attachment(tmp_path: Path) -> None:
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"PDF data")
    draft = DraftMessage(
        to="pkv-service@example.invalid",
        subject="Einreichung",
        body_text="Body text",
        attachments=[pdf],
    )
    msg_bytes = _build_mime_message(draft, from_addr="sender@example.invalid")
    msg = message_from_bytes(msg_bytes)
    assert msg["From"] == "sender@example.invalid"
    assert msg.get_content_type() == "multipart/mixed"
    parts = msg.get_payload()
    assert isinstance(parts, list)
    assert len(parts) == 2
    attachment = parts[1]
    assert isinstance(attachment, Message)
    assert attachment.get_content_type() == "application/pdf"
    payload = attachment.get_payload(decode=True)
    assert isinstance(payload, bytes)
    assert payload == b"PDF data"


def test_imap_provider_health_check_success() -> None:
    provider = IMAPProvider("imap.example.com", 993, "user", "pass")
    with patch("health_importer.email.imap_provider.imapclient.IMAPClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        assert provider.health_check() is True
        MockClient.assert_called_once_with("imap.example.com", port=993, ssl=True)
        mock_client.login.assert_called_once_with("user", "pass")
        mock_client.logout.assert_called_once()


def test_imap_provider_health_check_failure() -> None:
    provider = IMAPProvider("imap.example.com", 993, "user", "pass")
    with patch("health_importer.email.imap_provider.imapclient.IMAPClient") as MockClient:
        MockClient.side_effect = Exception("Connection refused")
        assert provider.health_check() is False


def test_imap_provider_create_draft_finds_folder_and_appends() -> None:
    provider = IMAPProvider("imap.example.com", 993, "user", "pass")
    draft = DraftMessage(
        to="pkv-service@example.invalid",
        subject="Einreichung",
        body_text="Body text",
    )

    with patch("health_importer.email.imap_provider.imapclient.IMAPClient") as MockClient:
        mock_client = MagicMock()
        mock_client.list_folders.return_value = [
            ("\\HasNoChildren", "/", "INBOX"),
            ("\\Drafts", "/", "Entwürfe"),
        ]
        mock_client.append.return_value = 42
        MockClient.return_value = mock_client

        result = provider.create_draft(draft)

        assert result == "imap:Entwürfe:42"
        mock_client.login.assert_called_once_with("user", "pass")
        mock_client.append.assert_called_once()
        call_args = mock_client.append.call_args
        assert call_args[0][0] == "Entwürfe"
        # Verify the MIME message has the correct From header
        appended_bytes = call_args[0][1]
        msg = message_from_bytes(appended_bytes)
        assert msg["From"] == "user"
        assert msg["To"] == "pkv-service@example.invalid"
        mock_client.logout.assert_called_once()


def test_imap_provider_create_draft_with_explicit_folder() -> None:
    provider = IMAPProvider(
        "imap.gmail.com", 993, "user", "pass", draft_folder_name="[Gmail]/Drafts"
    )
    draft = DraftMessage(
        to="pkv-service@example.invalid",
        subject="Einreichung",
        body_text="Body text",
    )

    with patch("health_importer.email.imap_provider.imapclient.IMAPClient") as MockClient:
        mock_client = MagicMock()
        mock_client.list_folders.return_value = [
            ("\\HasNoChildren", "/", "INBOX"),
            ("\\Drafts", "/", "[Gmail]/Drafts"),
        ]
        mock_client.append.return_value = 99
        MockClient.return_value = mock_client

        result = provider.create_draft(draft)

        assert result == "imap:[Gmail]/Drafts:99"
        mock_client.list_folders.assert_called_once()
        mock_client.append.assert_called_once()
        assert mock_client.append.call_args[0][0] == "[Gmail]/Drafts"
        appended_bytes = mock_client.append.call_args[0][1]
        msg = message_from_bytes(appended_bytes)
        assert msg["From"] == "user"


def test_imap_provider_login_failure_raises() -> None:
    provider = IMAPProvider("imap.example.com", 993, "user", "wrong")
    draft = DraftMessage(to="a@example.invalid", subject="S", body_text="B")

    with patch("health_importer.email.imap_provider.imapclient.IMAPClient") as MockClient:
        mock_client = MagicMock()
        mock_client.login.side_effect = Exception("AUTHENTICATIONFAILED")
        MockClient.return_value = mock_client

        with pytest.raises(EmailProviderError) as exc_info:
            provider.create_draft(draft)
        assert "login failed" in str(exc_info.value)


def test_build_provider_gmx() -> None:
    from health_importer.config import EmailConfig

    config = EmailConfig(
        enabled=True,
        provider="gmx",
        draft_folder=Path("review/drafts"),
        pkv_recipient="pkv-service@example.invalid",
        pkv_subject_template="Test",
        pkv_body_template="Body",
        pkv_sender_name="",
        pkv_sender_policy_number="",
        smtp_config={
            "username": "test@example.invalid",
            "password_env_key": "TEST_GMX_PASSWORD",
        },
    )
    with patch.dict("os.environ", {"TEST_GMX_PASSWORD": "secret"}):
        provider = build_provider(config)

    assert isinstance(provider, IMAPProvider)
    assert provider.host == "imap.gmx.net"
    assert provider.port == 993
    assert provider.draft_folder_name == "Entwürfe"


def test_build_provider_gmail() -> None:
    from health_importer.config import EmailConfig

    config = EmailConfig(
        enabled=True,
        provider="gmail",
        draft_folder=Path("review/drafts"),
        pkv_recipient="pkv-service@example.invalid",
        pkv_subject_template="Test",
        pkv_body_template="Body",
        pkv_sender_name="",
        pkv_sender_policy_number="",
        smtp_config={
            "username": "test@example.invalid",
            "password_env_key": "TEST_GMAIL_PASSWORD",
        },
    )
    with patch.dict("os.environ", {"TEST_GMAIL_PASSWORD": "secret"}):
        provider = build_provider(config)

    assert isinstance(provider, IMAPProvider)
    assert provider.host == "imap.gmail.com"
    assert provider.draft_folder_name == "[Gmail]/Drafts"


def test_build_provider_gmx_explicit_draft_folder() -> None:
    from health_importer.config import EmailConfig

    config = EmailConfig(
        enabled=True,
        provider="gmx",
        draft_folder=Path("review/drafts"),
        pkv_recipient="pkv-service@example.invalid",
        pkv_subject_template="Test",
        pkv_body_template="Body",
        pkv_sender_name="",
        pkv_sender_policy_number="",
        smtp_config={
            "username": "test@example.invalid",
            "password_env_key": "TEST_GMX_PASSWORD",
            "draft_folder_name": "MeineEntwuerfe",
        },
    )
    with patch.dict("os.environ", {"TEST_GMX_PASSWORD": "secret"}):
        provider = build_provider(config)

    assert isinstance(provider, IMAPProvider)
    assert provider.draft_folder_name == "MeineEntwuerfe"


def test_build_provider_gmail_explicit_draft_folder() -> None:
    from health_importer.config import EmailConfig

    config = EmailConfig(
        enabled=True,
        provider="gmail",
        draft_folder=Path("review/drafts"),
        pkv_recipient="pkv-service@example.invalid",
        pkv_subject_template="Test",
        pkv_body_template="Body",
        pkv_sender_name="",
        pkv_sender_policy_number="",
        smtp_config={
            "username": "test@example.invalid",
            "password_env_key": "TEST_GMAIL_PASSWORD",
            "draft_folder_name": "[Gmail]/Entwürfe",
        },
    )
    with patch.dict("os.environ", {"TEST_GMAIL_PASSWORD": "secret"}):
        provider = build_provider(config)

    assert isinstance(provider, IMAPProvider)
    assert provider.draft_folder_name == "[Gmail]/Entwürfe"


def test_imap_provider_explicit_folder_fallback_when_missing() -> None:
    provider = IMAPProvider(
        "imap.example.com", 993, "user", "pass", draft_folder_name="MissingFolder"
    )
    draft = DraftMessage(
        to="pkv-service@example.invalid",
        subject="Einreichung",
        body_text="Body text",
    )

    with patch("health_importer.email.imap_provider.imapclient.IMAPClient") as MockClient:
        mock_client = MagicMock()
        mock_client.list_folders.return_value = [
            ("\\HasNoChildren", "/", "INBOX"),
            ("\\Drafts", "/", "Drafts"),
        ]
        mock_client.append.return_value = 77
        MockClient.return_value = mock_client

        result = provider.create_draft(draft)

        assert result == "imap:Drafts:77"
        mock_client.list_folders.assert_called_once()
        mock_client.append.assert_called_once()
        assert mock_client.append.call_args[0][0] == "Drafts"
        appended_bytes = mock_client.append.call_args[0][1]
        msg = message_from_bytes(appended_bytes)
        assert msg["From"] == "user"


def test_build_provider_gmx_missing_password_fallback() -> None:
    from health_importer.config import EmailConfig

    config = EmailConfig(
        enabled=True,
        provider="gmx",
        draft_folder=Path("review/drafts"),
        pkv_recipient="pkv-service@example.invalid",
        pkv_subject_template="Test",
        pkv_body_template="Body",
        pkv_sender_name="",
        pkv_sender_policy_number="",
        smtp_config={"username": "test@example.invalid", "password_env_key": "MISSING"},
    )
    provider = build_provider(config)
    assert isinstance(provider, FileOnlyProvider)


def test_imap_provider_uses_explicit_from_addr() -> None:
    provider = IMAPProvider("imap.example.com", 993, "user", "pass", from_addr="me@example.invalid")
    draft = DraftMessage(
        to="pkv-service@example.invalid",
        subject="Einreichung",
        body_text="Body text",
    )

    with patch("health_importer.email.imap_provider.imapclient.IMAPClient") as MockClient:
        mock_client = MagicMock()
        mock_client.list_folders.return_value = [
            ("\\HasNoChildren", "/", "INBOX"),
            ("\\Drafts", "/", "Drafts"),
        ]
        mock_client.append.return_value = 1
        MockClient.return_value = mock_client

        provider.create_draft(draft)

        appended_bytes = mock_client.append.call_args[0][1]
        msg = message_from_bytes(appended_bytes)
        assert msg["From"] == "me@example.invalid"
        assert msg["To"] == "pkv-service@example.invalid"


def test_build_provider_gmx_with_from_addr() -> None:
    from health_importer.config import EmailConfig

    config = EmailConfig(
        enabled=True,
        provider="gmx",
        draft_folder=Path("review/drafts"),
        pkv_recipient="pkv-service@example.invalid",
        pkv_subject_template="Test",
        pkv_body_template="Body",
        pkv_sender_name="",
        pkv_sender_policy_number="",
        smtp_config={
            "username": "user",
            "password_env_key": "TEST_GMX_PASSWORD",
            "from_addr": "doctor@example.invalid",
        },
    )
    with patch.dict("os.environ", {"TEST_GMX_PASSWORD": "secret"}):
        provider = build_provider(config)

    assert isinstance(provider, IMAPProvider)
    assert provider.from_addr == "doctor@example.invalid"
