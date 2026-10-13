"""Google sign-in for the login page (Google Identity Services button).

The browser gets a Google ID token (a JWT signed by Google) and posts it to
/api/auth/google (frontend.py). This verifies it with Google's official
library: signature against Google's public keys, expiry, issuer, and that it
was issued for OUR client ID (audience). Then it only lets in a verified
email that is allowed here (ALLOWED_LOGIN_EMAILS when set) and that already
has an account. Google sign-in never creates an account.

Note: GOOGLE_CLIENT_SECRET is not used. ID tokens are verified with Google's
public keys plus the client ID; the secret is only for the server-side OAuth
code flow, which this is not.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User
from app.services import auth_service

logger = logging.getLogger(__name__)

NOT_ALLOWED_ERROR = "This Google account can't sign in here."
_request = google_requests.Request()


def client_id() -> str:
    return (settings.google_client_id or "").strip()


def verify_and_login(credential: str) -> auth_service.AuthResult:
    """AuthResult for a Google ID token: ok + the account, or a safe error."""
    cid = client_id()
    if not cid:
        return auth_service.AuthResult(False, "Google sign-in isn't set up on this site.")
    if not credential or len(credential) > 8192:
        return auth_service.AuthResult(False, "Google sign-in failed. Please try again.")
    try:
        # Signature, exp/iat, issuer (accounts.google.com) and audience == our client ID.
        info = id_token.verify_oauth2_token(credential, _request, cid, clock_skew_in_seconds=10)
    except Exception as exc:  # noqa: BLE001 - invalid/expired/foreign token: same safe message
        logger.warning("Google ID token rejected: %s", exc)
        return auth_service.AuthResult(False, "Google sign-in failed. Please try again.")
    email = (info.get("email") or "").strip().lower()
    if not email or not info.get("email_verified"):
        return auth_service.AuthResult(False, NOT_ALLOWED_ERROR)
    if not auth_service.is_allowed(email):
        return auth_service.AuthResult(False, NOT_ALLOWED_ERROR)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            return auth_service.AuthResult(False, NOT_ALLOWED_ERROR)  # no sign-up through Google
        user.last_login_at = datetime.now(timezone.utc)
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()
        return auth_service.AuthResult(True, user_id=user.id, user_name=user.full_name, user_email=user.email)
    finally:
        db.close()
