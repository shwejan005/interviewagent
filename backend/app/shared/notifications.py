"""Best-effort outbound notifications for user-facing workflow events."""

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)
_HTTPS_SCHEME = "https://"


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
    if not base_url.startswith((_HTTPS_SCHEME, "http://localhost", "http://127.0.0.1")):
        logger.error("AI interview notification skipped because FRONTEND_BASE_URL is not a safe HTTP(S) origin")
        return "invalid_frontend_url"

    message = EmailMessage()
    message["Subject"] = f"Your AI interview is ready: {posting_title}"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        f"Your application for {posting_title} at {organization_name} has passed the initial "
        "automated screening stage. The next assessment is ready when you are.\n\n"
        f"Join your AI interview from the interview agenda: {base_url}/interviews\n\n"
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

# ── Account emails (verification, password reset) ───────────────────


def smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST", "").strip() and os.getenv("SMTP_FROM", "").strip())


def email_verification_required() -> bool:
    """Require verification in production; allow frictionless local development.

    Set REQUIRE_EMAIL_VERIFICATION=true/false to override the environment-based default.
    """
    override = os.getenv("REQUIRE_EMAIL_VERIFICATION", "").strip().lower()
    if override in {"true", "1", "yes"}:
        return True
    if override in {"false", "0", "no"}:
        return False
    return os.getenv("APP_ENV", "development").strip().lower() == "production" or smtp_configured()


def _frontend_base_url() -> str | None:
    production = os.getenv("APP_ENV", "development").strip().lower() == "production"
    default_url = "" if production else "http://localhost:3000"
    base_url = os.getenv("FRONTEND_BASE_URL", default_url).strip().rstrip("/")
    allowed = base_url.startswith(_HTTPS_SCHEME) if production else base_url.startswith(
        (_HTTPS_SCHEME, "http://localhost", "http://127.0.0.1")
    )
    if not allowed:
        logger.error("Account email skipped because FRONTEND_BASE_URL is not a safe origin")
        return None
    return base_url


def _send_account_email(to: str, subject: str, body: str) -> str:
    if not smtp_configured():
        if os.getenv("APP_ENV", "development").strip().lower() != "production":
            logger.warning("SMTP not configured; account email was not sent")
        return "not_configured"

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.getenv("SMTP_FROM", "").strip()
    message["To"] = to
    message.set_content(body)
    try:
        with smtplib.SMTP(os.getenv("SMTP_HOST", "").strip(), int(os.getenv("SMTP_PORT", "587")), timeout=10) as client:
            if os.getenv("SMTP_USE_TLS", "true").strip().lower() != "false":
                client.starttls()
            username = os.getenv("SMTP_USERNAME", "").strip()
            if username:
                client.login(username, os.getenv("SMTP_PASSWORD", ""))
            client.send_message(message)
        return "sent"
    except (OSError, smtplib.SMTPException):
        logger.exception("Account email delivery failed")
        return "failed"


def send_email_verification_email(email: str, token: str) -> str:
    base_url = _frontend_base_url()
    if base_url is None:
        return "invalid_frontend_url"
    link = f"{base_url}/verify-email?token={token}"
    return _send_account_email(
        email,
        "Verify your Evalia email address",
        f"Confirm your email address to finish setting up your account:\n\n{link}\n\n"
        "This link expires in 48 hours. If you did not create an account, ignore this message.",
    )


def send_password_reset_email(email: str, token: str) -> str:
    base_url = _frontend_base_url()
    if base_url is None:
        return "invalid_frontend_url"
    link = f"{base_url}/reset-password?token={token}"
    return _send_account_email(
        email,
        "Reset your Evalia password",
        f"Use this link to choose a new password:\n\n{link}\n\n"
        "This link expires in 1 hour and can be used once. If you did not request it, ignore this message.",
    )
