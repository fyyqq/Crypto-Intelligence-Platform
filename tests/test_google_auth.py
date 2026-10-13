"""Google sign-in: token verification is delegated to google-auth (mocked
here); then only a verified, allowed email with an existing account gets in."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.services import auth_service as auth
from app.services import google_auth_service as g

PW = "Correct-Horse-9!"


@pytest.fixture
def setup(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(auth, "SessionLocal", maker)
    monkeypatch.setattr(g, "SessionLocal", maker)
    monkeypatch.setattr(auth.settings, "allowed_login_emails", "")
    monkeypatch.setattr(g.settings, "google_client_id", "my-client.apps.googleusercontent.com")
    assert auth.register_user("Owner", "owner@gmail.com", PW, PW).ok
    assert auth.register_user("Other", "other@gmail.com", PW, PW).ok
    seen = {}

    def fake_verify(token, request, audience, clock_skew_in_seconds=0):
        seen["audience"] = audience
        if token == "bad":
            raise ValueError("Token used too late")
        return {"email": token.split("|")[0], "email_verified": token.split("|")[1] == "1"}

    monkeypatch.setattr(g.id_token, "verify_oauth2_token", fake_verify)
    yield seen
    engine.dispose()


def test_valid_token_for_an_allowed_existing_account(setup, monkeypatch):
    monkeypatch.setattr(auth.settings, "allowed_login_emails", "owner@gmail.com")
    r = g.verify_and_login("Owner@Gmail.com|1")
    assert r.ok and r.user_email == "owner@gmail.com"
    assert setup["audience"] == "my-client.apps.googleusercontent.com"  # verified for OUR client id


def test_other_google_accounts_are_refused(setup, monkeypatch):
    monkeypatch.setattr(auth.settings, "allowed_login_emails", "owner@gmail.com")
    assert g.verify_and_login("other@gmail.com|1").error == g.NOT_ALLOWED_ERROR  # has an account, not allowed
    assert g.verify_and_login("stranger@gmail.com|1").error == g.NOT_ALLOWED_ERROR


def test_no_account_no_signup_unverified_and_invalid(setup):
    assert g.verify_and_login("new@gmail.com|1").error == g.NOT_ALLOWED_ERROR  # never creates an account
    assert not g.verify_and_login("owner@gmail.com|0").ok  # unverified email
    assert not g.verify_and_login("bad").ok  # signature/expiry failure
    assert not g.verify_and_login("").ok


def test_not_configured(setup, monkeypatch):
    monkeypatch.setattr(g.settings, "google_client_id", "")
    assert "isn't set up" in g.verify_and_login("owner@gmail.com|1").error
