"""Private mode (ALLOWED_LOGIN_EMAILS): only listed accounts can log in or
resume a session, and sign-up is closed. In-memory SQLite only."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.services import auth_service as auth

PW = "Correct-Horse-9!"


@pytest.fixture
def users(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(auth, "SessionLocal", sessionmaker(bind=engine, autoflush=False))
    monkeypatch.setattr(auth.settings, "allowed_login_emails", "")
    assert auth.register_user("Owner", "owner@example.com", PW, PW).ok
    assert auth.register_user("Other", "other@example.com", PW, PW).ok
    yield
    engine.dispose()


def private(monkeypatch, emails="Owner@Example.com"):
    monkeypatch.setattr(auth.settings, "allowed_login_emails", emails)


def test_open_mode_unchanged(users):
    assert not auth.is_private()
    assert auth.login_user("other@example.com", PW).ok


def test_only_listed_account_can_log_in(users, monkeypatch):
    private(monkeypatch)
    assert auth.is_private()
    assert auth.login_user("owner@example.com", PW).ok  # case-insensitive match
    other = auth.login_user("other@example.com", PW)
    assert not other.ok and other.error == auth.GENERIC_LOGIN_ERROR  # same message as a wrong password


def test_signup_closed(users, monkeypatch):
    private(monkeypatch)
    r = auth.register_user("New", "new@example.com", PW, PW)
    assert not r.ok and r.error == auth.SIGNUP_CLOSED_ERROR


def test_existing_cookie_of_unlisted_account_stops_working(users, monkeypatch):
    other_id = auth.login_user("other@example.com", PW).user_id
    token = auth.create_session(other_id)
    assert auth.resume_session(token).ok
    private(monkeypatch)
    assert not auth.resume_session(token).ok


def test_dev_auto_login_also_respects_the_list(users, monkeypatch):
    monkeypatch.setattr(auth.settings, "dev_auto_login_email", "other@example.com")
    assert auth.dev_auto_login("localhost:3000").ok
    private(monkeypatch)
    assert not auth.dev_auto_login("localhost:3000").ok
