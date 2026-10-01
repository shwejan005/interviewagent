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


def send_application_interview_ready_email(
    email: str,
    posting_title: str,
    organization_name: str,
    application_id: int,
) -> str:
    """Notify a candidate that their application passed screening.

    The candidate application tracker is the durable notification surface;
    missing/broken SMTP never changes the screening or interview state.
    """
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip()
    if not host or not sender:
        return "not_configured"

    base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").strip().rstrip("/")
    if not base_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        logger.error("AI interview notification skipped because FRONTEND_BASE_URL is not a safe HTTP(S) origin")
        return "invalid_frontend_url"

    message = EmailMessage()
    message["Subject"] = f"Your AI interview is ready: {posting_title}"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        f"Your application for {posting_title} at {organization_name} has passed the initial "
        "automated screening stage. The next assessment is ready when you are.\n\n"
        f"Review your application and start the AI interview: {base_url}/applications\n\n"
        "The application tracker is the source of truth if this email arrives late. "
        "The interview will identify itself as AI and explain the available format before it starts."
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
        logger.exception("AI interview ready notification delivery failed")
        return "failed"