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
- reCAPTCHA v3 is OFF by default (`RECAPTCHA_ENABLED`); re-enable only after the key's domains are set.
- "Remember me" is opt-in: ticked -> `create_session` + `repace_session` cookie (30 days, SameSite=Strict, token stored as SHA-256 in `user_sessions`). Unticked/signup -> tab session only. `CoinState.restore_session` is the first `on_load` event on every page.
- Watchlist, price alerts and alert history are scoped by the server-side `CoinState.user_id` (set at login, never from the browser). Alert events are wrapped by `_login_required`; `/alerts` uses `require_login`.
- Password eye state is per field and reset on page load (`LoginState.reset_visibility`).
- Cookie isn't `Secure` yet; add it when served over HTTPS.
- Delete test users after UI tests (`users`, `user_watchlist`, `user_sessions`, `price_alerts` should end empty).
- Notifications (`notification_service`, bell + `/notifications`) are scoped by the server-side `user_id` like alerts. New kinds: add to `KINDS`, then call `notify(...)`; see `docs/notifications.md`. A triggered price alert creates its notification inside `alert_service.mark_triggered`'s transaction.
- **Local dummy account** (created 2026-10-12, local DB only): `DEV_TEST_USER_EMAIL` / `DEV_TEST_USER_PASSWORD` in the gitignored `.env`, with sample notifications. Use it for logged-in UI tests instead of creating throwaway users, and don't delete it with the other test users. It stays logged in across restarts only if you log in with "Remember me" ticked (30-day `repace_session` cookie, token stored in `user_sessions`); without it the login lives in the tab session and is lost when Reflex restarts.
