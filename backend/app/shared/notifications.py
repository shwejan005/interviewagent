"""Best-effort outbound notifications for user-facing workflow events."""

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def send_referral_email(candidate_email: str, recruiter_name: str, posting_title: str, org_name: str, note: str) -> str:
    """Send a referral invitation without making database creation depend on SMTP."""
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip()
    if not host or not sender:
        return "not_configured"

    message = EmailMessage()
    message["Subject"] = f"You were referred for {posting_title} at {org_name}"
    message["From"] = sender
    message["To"] = candidate_email
    message.set_content(
        f"{recruiter_name} referred you for {posting_title} at {org_name}.\n\n"
        f"{note or 'Sign in to Evalia to review the role and respond to the referral.'}"
    )

    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=10) as client:
            if os.getenv("SMTP_USE_TLS", "true").strip().lower() != "false":
                client.starttls()
            username = os.getenv("SMTP_USERNAME", "").strip()
            password = os.getenv("SMTP_PASSWORD", "")
            if username:
                client.login(username, password)
            client.send_message(message)
        return "sent"
    except (OSError, smtplib.SMTPException):
        logger.exception("Referral email delivery failed")
        return "failed"


def send_organization_invitation_email(
    email: str,
    organization_name: str,
    role_name: str,
    invite_url: str,
) -> str:
    """Send an organization invitation without making admission depend on SMTP."""
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip()
    if not host or not sender:
        return "not_configured"

    message = EmailMessage()
    message["Subject"] = f"Invitation to join {organization_name} on Evalia"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        f"You have been invited to join {organization_name} as {role_name}.\n\n"
        f"Accept the invitation: {invite_url}\n"
    )

    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=10) as client:
            if os.getenv("SMTP_USE_TLS", "true").strip().lower() != "false":
                client.starttls()
            username = os.getenv("SMTP_USERNAME", "").strip()
            password = os.getenv("SMTP_PASSWORD", "")
            if username:
                client.login(username, password)
            client.send_message(message)
        return "sent"
    except (OSError, smtplib.SMTPException):
        logger.exception("Organization invitation email delivery failed")
        return "failed"