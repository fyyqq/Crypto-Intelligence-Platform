"""The /profile page: contact details in the users table and the profile picture / banner files.

Pictures are checked with Pillow (a real image of a plain format, a bounded pixel count), rotated by their EXIF
orientation, cropped (avatar square, banner 4:1), shrunk and saved as WebP under user_uploads/profile/ with a random
name (never taken from the upload), so a replaced picture is never served from a stale browser cache and nothing a
user sends is ever executed or served as its original bytes. The previous file is deleted. The e-mail is read-only
here: it is the login and never changes through this page."""
import io
import re
import secrets
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.database import SessionLocal
from app.models.user import User

UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "user_uploads"
PROFILE_DIR = UPLOAD_ROOT / "profile"
URL_PREFIX = "/user_uploads/profile/"
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000  # decompression-bomb guard
SIZES = {"avatar": (512, 512), "banner": (1600, 400)}
_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
_PHONE = re.compile(r"^[+(]?[0-9][0-9 ()\-]{5,30}$")
NAME_MAX = 40


class ProfileError(ValueError):
    """A message that is safe to show to the user."""


def _split(full_name: str) -> tuple[str, str]:
    first, _, last = (full_name or "").strip().partition(" ")
    return first, last.strip()


def get_profile(user_id: int) -> dict | None:
    db = SessionLocal()
    try:
        u = db.get(User, user_id)
        if u is None:
            return None
        first, last = _split(u.full_name)
        return {"first_name": first, "last_name": last, "email": u.email, "phone": u.phone or "",
                "address": u.address or "", "avatar_url": u.avatar_url or "", "banner_url": u.banner_url or ""}
    finally:
        db.close()


def validate(first: str, last: str, phone: str, address: str) -> dict[str, str]:
    """{field: message} for every invalid field (empty = valid). The values are stripped by the caller."""
    errors: dict[str, str] = {}
    if not first:
        errors["first_name"] = "First name is required."
    elif len(first) > NAME_MAX:
        errors["first_name"] = f"First name can be at most {NAME_MAX} characters."
    if len(last) > NAME_MAX:
        errors["last_name"] = f"Last name can be at most {NAME_MAX} characters."
    if phone and not _PHONE.match(phone):
        errors["phone"] = "Use digits, spaces, + ( ) and - only, e.g. +60 12 345 6789."
    if len(address) > 300:
        errors["address"] = "Address can be at most 300 characters."
    return errors


def update_profile(user_id: int, first: str, last: str, phone: str, address: str) -> dict[str, str]:
    """Saves the details; returns the validation errors (nothing is saved when there are any)."""
    first, last, phone, address = first.strip(), last.strip(), phone.strip(), address.strip()
    errors = validate(first, last, phone, address)
    if errors:
        return errors
    db = SessionLocal()
    try:
        u = db.get(User, user_id)
        if u is None:
            return {"form": "Account not found."}
        u.full_name = f"{first} {last}".strip()
        u.phone = phone or None
        u.address = address or None
        db.commit()
        return {}
    finally:
        db.close()


def _process(data: bytes, kind: str) -> bytes:
    if len(data) > MAX_BYTES:
        raise ProfileError("The picture is too large (5 MB at most).")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in _FORMATS:
            raise ProfileError("Use a PNG, JPG, WebP or GIF picture.")
        img.load()
    except ProfileError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise ProfileError("That file is not a valid picture.") from None
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")
    img = ImageOps.fit(img, SIZES[kind], Image.LANCZOS) if kind == "avatar" else _fit_banner(img)
    out = io.BytesIO()
    img.save(out, "WEBP", quality=85, method=4)
    return out.getvalue()


def _fit_banner(img: Image.Image) -> Image.Image:
    w, h = SIZES["banner"]
    if img.width < w:  # never blow a small picture up past its own width, keep the 4:1 shape
        w, h = img.width, max(1, img.width // 4)
    return ImageOps.fit(img, (w, h), Image.LANCZOS)


def save_image(user_id: int, kind: str, data: bytes) -> str:
    """Stores the picture and returns its URL path. Raises ProfileError with a user-facing message."""
    if kind not in SIZES:
        raise ProfileError("Unknown picture type.")
    webp = _process(data, kind)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{kind}-{user_id}-{secrets.token_hex(6)}.webp"
    (PROFILE_DIR / name).write_bytes(webp)
    column = "avatar_url" if kind == "avatar" else "banner_url"
    db = SessionLocal()
    try:
        u = db.get(User, user_id)
        if u is None:
            (PROFILE_DIR / name).unlink(missing_ok=True)
            raise ProfileError("Account not found.")
        old = getattr(u, column)
        setattr(u, column, URL_PREFIX + name)
        db.commit()
    finally:
        db.close()
    _delete_file(old)
    return URL_PREFIX + name


def remove_image(user_id: int, kind: str) -> None:
    column = "avatar_url" if kind == "avatar" else "banner_url"
    db = SessionLocal()
    try:
        u = db.get(User, user_id)
        if u is None:
            return
        old = getattr(u, column)
        setattr(u, column, None)
        db.commit()
    finally:
        db.close()
    _delete_file(old)


def _delete_file(url: str | None) -> None:
    """Deletes one of our own picture files (only names inside PROFILE_DIR, never a path from elsewhere)."""
    if not url or not url.startswith(URL_PREFIX):
        return
    name = url[len(URL_PREFIX):]
    if "/" in name or "\\" in name or name.startswith("."):
        return
    (PROFILE_DIR / name).unlink(missing_ok=True)


def avatar_url(user_id: int) -> str:
    db = SessionLocal()
    try:
        return db.query(User.avatar_url).filter(User.id == user_id).scalar() or ""
    finally:
        db.close()
