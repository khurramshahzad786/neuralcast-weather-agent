"""Owner access: one ADMIN_PASSWORD (in .env locally, in Streamlit Cloud Secrets when deployed)
unlocks owner-only views: project-wide LangSmith usage, raw provider errors, evaluation commands, and
every visitor's reports and analyses.

The typed password is wiped from the session as soon as it is checked; only an ``is_owner`` flag stays. Comparison is constant-time
on SHA-256 digests. Guessing is throttled per browser session and across the whole app.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from collections import deque
from collections.abc import MutableMapping

MIN_PASSWORD_LEN = 12
# Example values from docs / templates: never accepted, even if copied into Secrets unchanged.
PLACEHOLDER_PASSWORDS = frozenset({
    "choose-a-long-random-password", "a-long-random-password", "your-admin-password",
    "your-long-random-password", "change-me-to-a-long-password",
})
SESSION_MAX_FAILS = 5  # wrong guesses in one browser session before a pause
SESSION_LOCK_S = 300
GLOBAL_MAX_FAILS = 30  # wrong guesses from all sessions together within the window
GLOBAL_WINDOW_S = 600

_fails: deque[float] = deque()
_fails_lock = threading.Lock()


def configured_password() -> str | None:
    return os.getenv("ADMIN_PASSWORD") or None


def owner_mode_status() -> tuple[bool, str]:
    """(available, reason). Owner mode needs a configured, long-enough password."""
    pw = configured_password()
    if not pw:
        return False, "Owner mode is off: no ADMIN_PASSWORD is set in the app's secrets."
    if len(pw) < MIN_PASSWORD_LEN:
        return False, f"Owner mode is off: ADMIN_PASSWORD must be at least {MIN_PASSWORD_LEN} characters."
    if pw.strip().lower() in PLACEHOLDER_PASSWORDS:
        return False, "Owner mode is off: ADMIN_PASSWORD is still the example value; set your own."
    return True, ""


def password_matches(candidate: str, configured: str) -> bool:
    """Constant-time comparison (digests have equal length, so length is not leaked either)."""
    a = hashlib.sha256(candidate.encode("utf-8")).digest()
    b = hashlib.sha256(configured.encode("utf-8")).digest()
    return hmac.compare_digest(a, b)


def _global_blocked(now: float) -> bool:
    with _fails_lock:
        while _fails and now - _fails[0] > GLOBAL_WINDOW_S:
            _fails.popleft()
        return len(_fails) >= GLOBAL_MAX_FAILS


def _record_global_fail(now: float) -> None:
    with _fails_lock:
        _fails.append(now)


def reset_throttle() -> None:
    with _fails_lock:
        _fails.clear()


def try_unlock(candidate: str, session: MutableMapping, now: float | None = None) -> tuple[bool, str]:
    """Check a password typed by a visitor. On success sets ``session['is_owner'] = True``."""
    now = time.monotonic() if now is None else now
    available, reason = owner_mode_status()
    if not available:
        return False, reason
    locked_until = session.get("owner_locked_until", 0.0)
    if now < locked_until:
        return False, f"Too many wrong passwords. Try again in {int(locked_until - now) + 1} s."
    if _global_blocked(now):
        return False, "Owner sign-in is paused for a few minutes after many wrong passwords."
    if candidate and password_matches(candidate, configured_password() or ""):
        session["is_owner"] = True
        session["owner_fails"] = 0
        return True, "Owner mode on."
    _record_global_fail(now)
    fails = session.get("owner_fails", 0) + 1
    session["owner_fails"] = fails
    if fails >= SESSION_MAX_FAILS:
        session["owner_fails"] = 0
        session["owner_locked_until"] = now + SESSION_LOCK_S
        return False, f"Wrong password. Sign-in paused for {SESSION_LOCK_S // 60} minutes."
    return False, "Wrong password."


def lock(session: MutableMapping) -> None:
    session["is_owner"] = False
