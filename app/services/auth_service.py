"""Sign-up / log-in logic: strict server-side validation, Argon2id password hashing,
account lockout, and reCAPTCHA verification. The UI validation is only a convenience;
everything is re-checked here, so a forged request can't skip it."""
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from email_validator import EmailNotValidError, validate_email
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)

_hasher = PasswordHasher()  # Argon2id with the library's current safe defaults.
# Verified against when an email isn't registered, so a login for a missing account
# takes about as long as one for a real account (no account-enumeration timing leak).
_DUMMY_HASH = _hasher.hash("not-a-real-password-for-timing-only")

MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
_NAME_MAX = 80
_EMAIL_MAX = 254
_PASSWORD_MIN = 8
_PASSWORD_MAX = 128
# Letters (any language), spaces, apostrophes, hyphens and dots only. Never < > & quotes etc.
_NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '.\-][^\W\d_]+)*\.?$", re.UNICODE)

GENERIC_LOGIN_ERROR = "Invalid email or password."
GENERIC_SIGNUP_ERROR = "We couldn't create that account. If you already have one, try logging in."


@dataclass
class AuthResult:
    ok: bool
    error: str = ""
    user_id: int = 0
    user_name: str = ""
    user_email: str = ""


def _has_control_chars(value: str) -> bool:
    return any(unicodedata.category(c).startswith("C") for c in value)


def validate_name(raw: str) -> tuple[str, str]:
    name = unicodedata.normalize("NFKC", (raw or "").strip())
    name = re.sub(r"\s+", " ", name)
    if not name:
        return "", "Full name is required."
    if len(name) < 2 or len(name) > _NAME_MAX:
        return "", f"Full name must be 2–{_NAME_MAX} characters."
    if _has_control_chars(name) or not _NAME_RE.match(name):
        return "", "Full name can only contain letters, spaces, apostrophes, hyphens and dots."
    return name, ""


def validate_email_address(raw: str) -> tuple[str, str]:
    email = (raw or "").strip()
    if not email:
        return "", "Email is required."
    if len(email) > _EMAIL_MAX or _has_control_chars(email) or re.search(r"[<>\"'`;\\\s]", email):
        return "", "Enter a valid email address."
    try:
        result = validate_email(email, check_deliverability=False)
    except EmailNotValidError:
        return "", "Enter a valid email address."
    return result.normalized.lower(), ""


def validate_password(raw: str) -> str:
    """Returns an error message, or '' if the password is acceptable."""
    if not raw:
        return "Password is required."
    if len(raw) < _PASSWORD_MIN or len(raw) > _PASSWORD_MAX:
        return f"Password must be {_PASSWORD_MIN}–{_PASSWORD_MAX} characters."
    if _has_control_chars(raw):
        return "Password contains invalid characters."
    if not (re.search(r"[a-z]", raw) and re.search(r"[A-Z]", raw) and re.search(r"\d", raw) and re.search(r"[^A-Za-z0-9]", raw)):
        return "Password needs an uppercase letter, a lowercase letter, a number and a symbol."
    return ""


RECAPTCHA_MIN_SCORE = 0.5


def verify_recaptcha(token: str, action: str) -> bool:
    """Server-side check of a reCAPTCHA v3 token: Google must accept it, the token must
    have been issued for this exact action, and the bot-likelihood score must be high
    enough. Fails closed on any problem."""
    if not token or len(token) > 4096:
        return False
    try:
        resp = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": settings.recaptcha_secret_key, "response": token},
            timeout=8,
        )
        data = resp.json()
    except Exception:
        logger.warning("reCAPTCHA verification request failed", exc_info=True)
        return False
    if not data.get("success"):
        logger.info("reCAPTCHA rejected: %s", data.get("error-codes"))
        return False
    if data.get("action") != action:
        return False
    return float(data.get("score", 0)) >= RECAPTCHA_MIN_SCORE


def register_user(full_name: str, email: str, password: str, repeat_password: str) -> AuthResult:
    name, err = validate_name(full_name)
    if err:
        return AuthResult(False, err)
    addr, err = validate_email_address(email)
    if err:
        return AuthResult(False, err)
    err = validate_password(password)
    if err:
        return AuthResult(False, err)
    if not repeat_password:
        return AuthResult(False, "Repeat your password.")
    if password != repeat_password:
        return AuthResult(False, "Passwords do not match.")

    password_hash = _hasher.hash(password)
    db = SessionLocal()
    try:
        if db.query(User.id).filter(User.email == addr).first():
            return AuthResult(False, GENERIC_SIGNUP_ERROR)
        user = User(full_name=name, email=addr, password_hash=password_hash)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:  # lost a race with another sign-up for the same email
            db.rollback()
            return AuthResult(False, GENERIC_SIGNUP_ERROR)
        return AuthResult(True, user_id=user.id, user_name=user.full_name, user_email=user.email)
    finally:
        db.close()


def login_user(email: str, password: str) -> AuthResult:
    addr, err = validate_email_address(email)
    if err or not password or len(password) > _PASSWORD_MAX:
        # Still do the hashing work so timing doesn't reveal which check failed.
        try:
            _hasher.verify(_DUMMY_HASH, password[:_PASSWORD_MAX] or "x")
        except Exception:
            pass
        return AuthResult(False, GENERIC_LOGIN_ERROR)

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == addr).first()
        if user is None:
            try:
                _hasher.verify(_DUMMY_HASH, password)
            except Exception:
                pass
            return AuthResult(False, GENERIC_LOGIN_ERROR)
        if user.locked_until and user.locked_until > now:
            return AuthResult(False, "Too many failed attempts. Try again in a few minutes.")
        try:
            _hasher.verify(user.password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                user.failed_login_attempts = 0
            db.commit()
            return AuthResult(False, GENERIC_LOGIN_ERROR)
        if _hasher.check_needs_rehash(user.password_hash):
            user.password_hash = _hasher.hash(password)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        db.commit()
        return AuthResult(True, user_id=user.id, user_name=user.full_name, user_email=user.email)
    finally:
        db.close()
