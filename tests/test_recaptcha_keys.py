"""reCAPTCHA: one key pair per environment (_LOCAL on the dev machine, _PROD on the live server), picked by RECAPTCHA_ENV."""
from app.core.config import Settings


NONE = dict(recaptcha_site_key_local="", recaptcha_secret_key_local="", recaptcha_site_key_prod="", recaptcha_secret_key_prod="", recaptcha_site_key="", recaptcha_secret_key="")
# (Environment variables win over _env_file=None, and importing the login page loads the real .env into them, so every field is set explicitly.)


def _s(**kw):
    return Settings(_env_file=None, **{**NONE, "recaptcha_site_key_local": "site-local", "recaptcha_secret_key_local": "secret-local",
                                       "recaptcha_site_key_prod": "site-prod", "recaptcha_secret_key_prod": "secret-prod", **kw})


def test_local_is_the_default_and_prod_is_picked_by_recaptcha_env():
    assert _s().recaptcha_keys() == ("site-local", "secret-local")
    assert _s(recaptcha_env="local").recaptcha_keys() == ("site-local", "secret-local")
    assert _s(recaptcha_env="prod").recaptcha_keys() == ("site-prod", "secret-prod")
    assert _s(recaptcha_env=" PROD ").recaptcha_keys() == ("site-prod", "secret-prod")  # spacing / case do not matter
    assert _s(recaptcha_env="something else").recaptcha_keys() == ("site-local", "secret-local")  # anything but prod is local: never the live keys by accident


def test_the_old_single_pair_is_only_a_fallback_when_the_pair_for_the_environment_is_empty():
    old = Settings(_env_file=None, **{**NONE, "recaptcha_site_key": "old-site", "recaptcha_secret_key": "old-secret"})
    assert old.recaptcha_keys() == ("old-site", "old-secret")
    half = Settings(_env_file=None, **{**NONE, "recaptcha_env": "prod", "recaptcha_site_key_local": "site-local", "recaptcha_secret_key_local": "secret-local",
                                       "recaptcha_site_key": "old-site", "recaptcha_secret_key": "old-secret"})
    assert half.recaptcha_keys() == ("old-site", "old-secret")  # prod pair empty: the legacy pair, not the local one
    assert Settings(_env_file=None, **NONE).recaptcha_keys() == ("", "")


def test_the_login_form_uses_those_keys_and_is_only_on_with_both_keys_and_the_flag():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    page = (root / "frontend" / "frontend" / "components" / "login_page.py").read_text()
    assert "_settings.recaptcha_keys()" in page and 'os.getenv("RECAPTCHA_SITE_KEY"' not in page
    assert "bool(_settings.recaptcha_enabled) and bool(_settings.recaptcha_keys()[0]) and bool(_settings.recaptcha_keys()[1])" in page
    auth = (root / "app" / "services" / "auth_service.py").read_text()
    assert 'settings.recaptcha_keys()[1]' in auth and "settings.recaptcha_secret_key," not in auth
