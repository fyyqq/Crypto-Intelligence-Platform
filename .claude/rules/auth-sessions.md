---
paths:
  - "app/services/auth_service.py"
  - "app/services/alert_service.py"
  - "app/services/notification_service.py"
  - "app/services/watchlist_service.py"
  - "app/models/user*.py"
  - "frontend/frontend/components/login_page.py"
  - "frontend/frontend/components/alerts_page.py"
---

# Auth / accounts rules

- All validation is re-checked server-side in `auth_service` (never trust the form). Argon2id hashes; SQLAlchemy parameterised queries only.
- Login failures are generic ("Invalid email or password."), verify against a dummy hash for unknown emails, lock 15 min after 5 failures. Signup duplicate email is deliberately explicit (user's choice). Format errors are specific.
- reCAPTCHA v3 is OFF by default (`RECAPTCHA_ENABLED`). Two key pairs: `RECAPTCHA_SITE_KEY_LOCAL/_SECRET_KEY_LOCAL` (dev machine, the default) and `..._PROD` (live; the live `.env` has `RECAPTCHA_ENV=prod` + `RECAPTCHA_ENABLED=true`); `Settings.recaptcha_keys()` picks the pair. A key only works on the domains listed for it in Google's reCAPTCHA admin: check with a real browser (the anchor frame says "... is not in the list of supported domains"), because Google's `browser-error` from siteverify is the only symptom otherwise. Status 2026-10-25: PROD key verified end to end on repace.fyqqflow.com (success, score 0.9, action login); the LOCAL key does not list `localhost` yet, so the local flag stays false.
- "Remember me" is opt-in: ticked -> `create_session` + `repace_session` cookie (30 days, SameSite=Strict, token stored as SHA-256 in `user_sessions`). Unticked/signup -> tab session only. `CoinState.restore_session` is the first `on_load` event on every page.
- Watchlist, price alerts and alert history are scoped by the server-side `CoinState.user_id` (set at login, never from the browser). Alert events are wrapped by `_login_required`; `/alerts` uses `require_login`.
- Password eye state is per field and reset on page load (`LoginState.reset_visibility`).
- Cookie isn't `Secure` yet; add it when served over HTTPS.
- Delete test users after UI tests (`users`, `user_watchlist`, `user_sessions`, `price_alerts` should end empty).
- Notifications (`notification_service`, bell + `/notifications`) are scoped by the server-side `user_id` like alerts. New kinds: add to `KINDS`, then call `notify(...)`; see `docs/notifications.md`. A triggered price alert creates its notification inside `alert_service.mark_triggered`'s transaction.
- **Local dummy account** (created 2026-10-12, local DB only): `DEV_TEST_USER_EMAIL` / `DEV_TEST_USER_PASSWORD` in the gitignored `.env`, with sample notifications. Use it for logged-in UI tests instead of creating throwaway users, and don't delete it with the other test users.
- **Dev auto-login** (local only): `DEV_AUTO_LOGIN_EMAIL=dev-tester@example.com` in the local `.env` logs that account in automatically on every page load, no login step and nothing to survive a Reflex restart (`CoinState.restore_session` -> `auth_service.dev_auto_login`). It is inert unless the key is set AND the request Host is localhost / 127.0.0.1 / *.localhost, so it cannot work on the live site (the live `.env` has no such key; never add it there). Logging out keeps that tab logged out until Reflex restarts. Remove the key to test the normal logged-out flow; to test another account, log out first. Without the key, login without "Remember me" is lost on restart.
- **Private mode** (`ALLOWED_LOGIN_EMAILS`, comma-separated; set on the live server for the owner's account only): only listed accounts can log in or resume a cookie session (others get the generic login error), sign-up is closed (no link, `register_user` refuses), and every page's `restore_session` sends a logged-out visitor to `/login` while `_header_bar` covers the page (`.private-mode-cover`). Dev auto-login also respects the list. Unset = open site (local dev). Tests: `tests/test_private_mode.py`.

- **Login wall (2026-10-14)**: every page needs a login; logged-out visitors (and anyone after Log out) are sent to `/login` (`/signup` stays open only when sign-up is open). **Google sign-in**: GIS button (`assets/google_login.js`) -> `POST /api/auth/google` -> `google_auth_service.verify_and_login` (google-auth `verify_oauth2_token`, audience `GOOGLE_CLIENT_ID`; verified + allowed email with an existing account only) -> 30-day `repace_session` cookie. Never use `GOOGLE_CLIENT_SECRET` for this flow and never send it to the browser. Tests: `tests/test_google_auth.py`.
