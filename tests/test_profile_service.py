"""/profile: details validation and saving, and picture handling (real images only, cropped and re-encoded, the
old file removed, nothing taken from the uploaded file name). Postgres is replaced by in-memory SQLite."""

import io

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.user import User
from app.services import profile_service as ps


@pytest.fixture
def env(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(ps, "SessionLocal", maker)
    monkeypatch.setattr(ps, "PROFILE_DIR", tmp_path / "profile")
    db = maker()
    db.add(User(id=1, full_name="Jake Nackos Jr", email="jake@x.com", password_hash="h"))
    db.add(User(id=2, full_name="Solo", email="solo@x.com", password_hash="h"))
    db.commit()
    db.close()
    yield maker
    engine.dispose()


def png(w=800, h=600, mode="RGB", fmt="PNG"):
    buf = io.BytesIO()
    Image.new(mode, (w, h), "red").save(buf, fmt)
    return buf.getvalue()


def test_profile_splits_the_name_and_email_is_included(env):
    p = ps.get_profile(1)
    assert (p["first_name"], p["last_name"], p["email"]) == ("Jake", "Nackos Jr", "jake@x.com")
    assert ps.get_profile(2)["last_name"] == "" and ps.get_profile(99) is None
    assert (p["phone"], p["address"], p["avatar_url"], p["banner_url"]) == ("", "", "", "")


def test_details_are_saved_trimmed_and_the_email_never_changes(env):
    assert ps.update_profile(1, " Jake ", " Nackos ", " +971 50 827 8229 ", " 1 Marina St\nDubai ") == {}
    p = ps.get_profile(1)
    assert (p["first_name"], p["last_name"], p["phone"], p["address"]) == ("Jake", "Nackos", "+971 50 827 8229", "1 Marina St\nDubai")
    assert p["email"] == "jake@x.com"
    db = env()
    assert db.get(User, 1).full_name == "Jake Nackos"  # what the header shows
    db.close()
    assert ps.update_profile(1, "Jake", "", "", "") == {} and ps.get_profile(1)["phone"] == ""  # empty clears


def test_invalid_details_save_nothing(env):
    errs = ps.update_profile(1, "", "x" * 41, "abc", "y" * 301)
    assert set(errs) == {"first_name", "last_name", "phone", "address"}
    assert ps.get_profile(1)["first_name"] == "Jake"
    assert ps.update_profile(1, "A" * 41, "", "", "").keys() == {"first_name"}
    assert [bool(ps.validate("J", "", p, "")) for p in ("+60 12-345 6789", "(03) 1234 5678", "12", "+", "1234567890123")] == [False, False, True, True, False]
    assert ps.update_profile(99, "A", "", "", "") == {"form": "Account not found."}


def test_avatar_is_cropped_square_webp_with_a_random_name_and_the_old_one_is_deleted(env):
    url = ps.save_image(1, "avatar", png(800, 300))
    assert url.startswith("/user_uploads/profile/avatar-1-") and url.endswith(".webp")
    f = ps.PROFILE_DIR / url.rsplit("/", 1)[1]
    with Image.open(f) as img:
        assert img.format == "WEBP" and img.size == (512, 512)
    assert ps.get_profile(1)["avatar_url"] == url and ps.avatar_url(1) == url
    url2 = ps.save_image(1, "avatar", png(100, 100, "RGBA"))
    assert url2 != url and not f.exists() and (ps.PROFILE_DIR / url2.rsplit("/", 1)[1]).exists()
    ps.remove_image(1, "avatar")
    assert ps.get_profile(1)["avatar_url"] == "" and list(ps.PROFILE_DIR.iterdir()) == []


def test_banner_is_four_to_one_and_a_small_picture_is_not_stretched(env):
    big = ps.save_image(1, "banner", png(3000, 2000, fmt="JPEG"))
    with Image.open(ps.PROFILE_DIR / big.rsplit("/", 1)[1]) as img:
        assert img.size == (1600, 400)
    small = ps.save_image(2, "banner", png(400, 400))
    with Image.open(ps.PROFILE_DIR / small.rsplit("/", 1)[1]) as img:
        assert img.size == (400, 100)


def test_only_real_pictures_are_accepted(env):
    for bad, msg in ((b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "not a valid"), (b"not an image at all", "not a valid"),
                     (b"", "not a valid"), (png(10, 10, fmt="BMP"), "PNG, JPG, WebP or GIF"), (b"x" * (ps.MAX_BYTES + 1), "too large")):
        with pytest.raises(ps.ProfileError, match=msg):
            ps.save_image(1, "avatar", bad)
    with pytest.raises(ps.ProfileError, match="Unknown"):
        ps.save_image(1, "cover", png())
    assert not ps.PROFILE_DIR.exists() or list(ps.PROFILE_DIR.iterdir()) == []  # nothing stored for a rejected file
    assert ps.get_profile(1)["avatar_url"] == ""


def test_a_picture_for_a_missing_account_leaves_no_file(env):
    with pytest.raises(ps.ProfileError):
        ps.save_image(99, "avatar", png())
    assert list(ps.PROFILE_DIR.iterdir()) == []


def test_only_our_own_picture_files_are_ever_deleted(env, tmp_path):
    outside = tmp_path / "keep.txt"
    outside.write_text("x")
    ps.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    for evil in ("/user_uploads/profile/../../keep.txt", "/etc/passwd", "/user_uploads/profile/.hidden", "keep.txt", None, ""):
        ps._delete_file(evil)
    assert outside.exists()
