"""
Security primitives: password hashing and signed session tokens.

Deliberate choices worth knowing about:

* Passwords are pre-hashed with SHA-256 before bcrypt. bcrypt silently
  truncates input at 72 bytes, which means two distinct long passwords can
  collide. Pre-hashing to a fixed-width digest removes that footgun. The
  digest is base64-encoded (not raw bytes) because bcrypt also truncates at
  the first NUL byte.
* Tokens are stateless JWTs carrying only identifiers, never capabilities.
  Capabilities are resolved from the database on every request, so a role
  change or revoked membership takes effect immediately instead of lingering
  until the token expires.
"""

import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

# Rounds is a deliberate cost/latency trade-off. 12 is the common default and
# keeps a single hash near ~250ms on typical hardware.
_BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))

_JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(hours=int(os.getenv("ACCESS_TOKEN_TTL_HOURS", "12")))


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired, or fails signature checks."""


def _jwt_secret() -> str:
    """Return the signing secret, refusing to start insecurely in production.

    Read at call time rather than import time so tests and local runs can set
    it after the module is imported.
    """
    secret = os.getenv("JWT_SECRET", "").strip()
    if secret:
        return secret

    if os.getenv("APP_ENV", "development").strip().lower() == "production":
        raise RuntimeError(
            "JWT_SECRET must be set when APP_ENV=production. Refusing to sign "
            "tokens with a development fallback secret."
        )
    # Dev-only fallback. Stable across a single process so local logins survive
    # a hot reload, but regenerated on restart so it can never become a real key.
    global _DEV_SECRET
    if _DEV_SECRET is None:
        _DEV_SECRET = secrets.token_urlsafe(48)
    return _DEV_SECRET


_DEV_SECRET: Optional[str] = None


# ── Passwords ────────────────────────────────────────────────────────


def _prehash(password: str) -> bytes:
    """SHA-256 then base64, so bcrypt never sees >72 bytes or an embedded NUL."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    """Hash a plaintext password for storage."""
    if not password:
        raise ValueError("Password cannot be empty.")
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored hash.

    Returns False rather than raising on a malformed stored hash, so a corrupt
    row denies access instead of 500-ing the login endpoint.
    """
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── Tokens ───────────────────────────────────────────────────────────


def create_access_token(user_id: int, *, ttl: Optional[timedelta] = None) -> str:
    """Issue a signed access token identifying a user.

    The token intentionally carries no org or capability claims — those are
    resolved per-request so that revocation is immediate.
    """
    return create_access_token_with_provenance(user_id, ttl=ttl)


def create_access_token_with_provenance(
    user_id: int,
    *,
    ttl: Optional[timedelta] = None,
    impersonated_by: Optional[int] = None,
) -> str:
    """Issue a token and optionally preserve the real actor behind impersonation."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + (ttl or ACCESS_TOKEN_TTL)).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    if impersonated_by is not None:
        payload["impersonated_by"] = str(impersonated_by)
    return jwt.encode(payload, _jwt_secret(), algorithm=_JWT_ALGORITHM)


def decode_access_token_details(token: str) -> tuple[int, Optional[int]]:
    """Return the user and optional impersonating admin IDs from a token."""
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid.") from exc

    subject = payload.get("sub")
    if subject is None:
        raise TokenError("Token is missing a subject claim.")
    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise TokenError("Token subject is not a valid user ID.") from exc

    impersonated_by = payload.get("impersonated_by")
    if impersonated_by is not None:
        try:
            impersonated_by = int(impersonated_by)
        except (TypeError, ValueError) as exc:
            raise TokenError("Token impersonation claim is invalid.") from exc
    return user_id, impersonated_by


def decode_access_token(token: str) -> int:
    """Return the user ID carried by a valid token, or raise TokenError."""
    return decode_access_token_details(token)[0]


def generate_invite_token() -> str:
    """Opaque, high-entropy token for invitation links."""
    return secrets.token_urlsafe(32)


def hash_invite_token(token: str) -> str:
    """Store invitation tokens hashed, so a database leak does not grant access."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_evaluation_access_token() -> str:
    """Create the opaque bearer token used by the anonymous sandbox."""
    return secrets.token_urlsafe(32)


def hash_evaluation_access_token(token: str) -> str:
    """Hash a sandbox token before it is persisted or compared."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
