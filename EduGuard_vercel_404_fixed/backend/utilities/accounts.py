"""Sign-in accounts for EduGuard.

* Passwords are stored only as salted scrypt hashes (standard library).
* Desktop sessions live in memory; Vercel uses short-lived signed session tokens.
* Only an academic advisor creates, edits, resets or removes accounts.
* Repeated wrong passwords lock that username for a few minutes.

Recovery if every advisor password is lost (run from the project folder):
    backend\\venv\\Scripts\\python -m backend.utilities.accounts reset-advisor
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
import sys
import threading
import time

from . import db
from .common import now_str

ROLES = ("advisor", "admin", "faculty", "equity")
USERNAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,31}")
MIN_PASSWORD = 8
SESSION_SECONDS = 12 * 3600
MAX_FAILURES = 5
LOCK_SECONDS = 300

_lock = threading.RLock()
_sessions = {}   # local desktop token -> {"user_id": int, "expires": float}
_failures = {}   # username -> {"count": int, "until": float}
_IS_VERCEL = str(os.environ.get("VERCEL", "")).lower() in {"1", "true", "yes"}
_SESSION_SECRET = (os.environ.get("EDUGUARD_SESSION_SECRET") or "").encode("utf-8")

_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


# ------------------------------------------------------------------ passwords
def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        _, n, r, p, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), dklen=len(digest) // 2,
                             n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(got.hex(), digest)
    except (ValueError, AttributeError):
        return False


def check_password_strength(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise ValueError(f"Use a password of at least {MIN_PASSWORD} characters.")
    if len(password) > 128:
        raise ValueError("That password is too long (128 characters at most).")
    if password.strip() != password:
        raise ValueError("The password can't start or end with a space.")


def generate_password():
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(12))


# ------------------------------------------------------------------ validation helpers
def _username(value):
    name = str(value or "").strip().lower()
    if not USERNAME_RE.fullmatch(name):
        raise ValueError("Username: 3 to 32 characters, using letters, numbers, dot, dash or underscore.")
    return name


def _full_name(value):
    name = " ".join(str(value or "").split())
    if not 2 <= len(name) <= 80:
        raise ValueError("Enter the person's full name (2 to 80 characters).")
    return name


def _role(value):
    role = str(value or "").strip().lower()
    if role not in ROLES:
        raise ValueError("Choose a role from the list.")
    return role


def public(user):
    """A user row without the password hash."""
    return {"id": user["id"], "username": user["username"], "full_name": user["full_name"], "role": user["role"],
            "active": bool(user["active"]), "must_change": bool(user["must_change"]),
            "created_at": user["created_at"], "created_by": user["created_by"], "last_login": user["last_login"]}


def _get(user_id):
    return db.one("SELECT * FROM users WHERE id=?", (user_id,))


def _active_advisors(exclude_id=None):
    row = db.one("SELECT COUNT(*) AS c FROM users WHERE role='advisor' AND active=1 AND id<>?", (exclude_id or -1,))
    return row["c"]


# ------------------------------------------------------------------ setup and management
def needs_setup():
    return db.one("SELECT COUNT(*) AS c FROM users")["c"] == 0


def create_user(username, full_name, role, password, created_by, must_change=True):
    username, full_name, role = _username(username), _full_name(full_name), _role(role)
    check_password_strength(password)
    with _lock:
        if db.one("SELECT 1 AS x FROM users WHERE username=?", (username,)):
            raise ValueError("That username is already taken.")
        uid = db.execute(
            "INSERT INTO users(username,full_name,role,password_hash,active,must_change,created_at,created_by) "
            "VALUES(?,?,?,?,1,?,?,?)",
            (username, full_name, role, hash_password(password), 1 if must_change else 0, now_str(), created_by))
    return public(_get(uid))


def create_first_advisor(username, full_name, password):
    """Only works while no account exists, so it can't be used to take over a running system."""
    with _lock:
        if not needs_setup():
            raise PermissionError("Setup is already complete. Ask an academic advisor for an account.")
    return create_user(username, full_name, "advisor", password, "first-run setup", must_change=False)


def list_users():
    rows = db.query("SELECT * FROM users ORDER BY CASE role WHEN 'advisor' THEN 0 ELSE 1 END, full_name COLLATE NOCASE")
    return [public(r) for r in rows]


def update_user(user_id, changes, actor_id):
    user = _get(user_id)
    if not user:
        raise LookupError("That account no longer exists.")
    new_name = _full_name(changes["full_name"]) if "full_name" in changes else user["full_name"]
    new_role = _role(changes["role"]) if "role" in changes else user["role"]
    new_active = bool(changes["active"]) if "active" in changes else bool(user["active"])
    losing_advisor = user["role"] == "advisor" and user["active"] and (new_role != "advisor" or not new_active)
    if user_id == actor_id and (new_role != user["role"] or not new_active):
        raise ValueError("You can't change your own role or switch off your own account.")
    if losing_advisor and _active_advisors(exclude_id=user_id) == 0:
        raise ValueError("At least one active academic advisor must remain.")
    db.execute("UPDATE users SET full_name=?, role=?, active=? WHERE id=?",
               (new_name, new_role, 1 if new_active else 0, user_id))
    if not new_active or new_role != user["role"]:
        end_sessions_for(user_id)
    return public(_get(user_id))


def reset_password(user_id, password, temporary=True):
    user = _get(user_id)
    if not user:
        raise LookupError("That account no longer exists.")
    check_password_strength(password)
    db.execute("UPDATE users SET password_hash=?, must_change=? WHERE id=?",
               (hash_password(password), 1 if temporary else 0, user_id))
    _failures.pop(user["username"], None)
    end_sessions_for(user_id)
    return public(_get(user_id))


def delete_user(user_id, actor_id):
    user = _get(user_id)
    if not user:
        raise LookupError("That account no longer exists.")
    if user_id == actor_id:
        raise ValueError("You can't delete the account you are signed in with.")
    if user["role"] == "advisor" and user["active"] and _active_advisors(exclude_id=user_id) == 0:
        raise ValueError("At least one active academic advisor must remain.")
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    end_sessions_for(user_id)
    return public(user)


def change_own_password(user_id, current, new):
    user = _get(user_id)
    if not user or not verify_password(current or "", user["password_hash"]):
        raise ValueError("The current password isn't right.")
    if current == new:
        raise ValueError("Choose a new password that differs from the current one.")
    check_password_strength(new)
    db.execute("UPDATE users SET password_hash=?, must_change=0 WHERE id=?", (hash_password(new), user_id))
    return public(_get(user_id))


DEFAULT_ADVISOR = {
    "username": os.environ.get("EDUGUARD_DEFAULT_ADVISOR_USERNAME", "cheerwin"),
    "full_name": os.environ.get("EDUGUARD_DEFAULT_ADVISOR_NAME", "Cheerwin (default advisor)"),
    "password": os.environ.get("EDUGUARD_DEFAULT_ADVISOR_PASSWORD", "cheer6598"),
}


def seed_default_advisor():
    """Create the default advisor login once. If it is later deleted or renamed it is not brought back."""
    with _lock:
        if db.get_meta("default_advisor_seeded"):
            return False
        db.set_meta("default_advisor_seeded", "1")
        if db.one("SELECT 1 AS x FROM users WHERE username=?", (DEFAULT_ADVISOR["username"],)):
            return False
        create_user(DEFAULT_ADVISOR["username"], DEFAULT_ADVISOR["full_name"], "advisor",
                    DEFAULT_ADVISOR["password"], "default", must_change=False)
        return True


# ------------------------------------------------------------------ sessions
def _web_sign(user_id, expires):
    if not _SESSION_SECRET:
        raise RuntimeError("EDUGUARD_SESSION_SECRET must be set for Vercel web sessions.")
    payload = f"{int(user_id)}.{int(expires)}".encode("ascii")
    body = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    sig = hmac.new(_SESSION_SECRET, body.encode("ascii"), hashlib.sha256).digest()
    return f"v1.{body}.{base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")}"

def _web_verify(token):
    try:
        version, body, sig_b64 = token.split(".", 2)
        if version != "v1" or not _SESSION_SECRET:
            return None
        expected = hmac.new(_SESSION_SECRET, body.encode("ascii"), hashlib.sha256).digest()
        padded = sig_b64 + "=" * (-len(sig_b64) % 4)
        supplied = base64.urlsafe_b64decode(padded.encode("ascii"))
        if not hmac.compare_digest(expected, supplied):
            return None
        payload = base64.urlsafe_b64decode((body + "=" * (-len(body) % 4)).encode("ascii")).decode("ascii")
        user_id, expires = payload.split(".", 1)
        if int(expires) < int(time.time()):
            return None
        return int(user_id)
    except (TypeError, ValueError, UnicodeError):
        return None

def login(username, password, role):
    """Return (token, user). The account must hold the role whose login page was used."""
    name = str(username or "").strip().lower()
    now = time.time()
    with _lock:
        fail = _failures.get(name)
        if fail and fail["until"] > now:
            wait = int((fail["until"] - now) // 60) + 1
            raise PermissionError(f"Too many wrong attempts. Try again in about {wait} minute{'s' if wait != 1 else ''}.")
    user = db.one("SELECT * FROM users WHERE username=?", (name,))
    # Hash even when the user is unknown so response time doesn't reveal which usernames exist.
    stored = user["password_hash"] if user else hash_password("not-a-real-password")
    good = verify_password(password or "", stored) and user is not None
    if not good or user["role"] != role:
        with _lock:
            fail = _failures.get(name, {"count": 0, "until": 0})
            fail["count"] += 1
            if fail["count"] >= MAX_FAILURES:
                fail.update(count=0, until=now + LOCK_SECONDS)
            _failures[name] = fail
        raise PermissionError("Username, password or role doesn't match. Check that you chose your own role's sign-in.")
    if not user["active"]:
        raise PermissionError("This account has been switched off. Ask an academic advisor.")
    with _lock:
        _failures.pop(name, None)
        expires = now + SESSION_SECONDS
        if _IS_VERCEL:
            token = _web_sign(user["id"], expires)
        else:
            token = secrets.token_urlsafe(32)
            _sessions[token] = {"user_id": user["id"], "expires": expires}
    db.execute("UPDATE users SET last_login=? WHERE id=?", (now_str(), user["id"]))
    return token, public(_get(user["id"]))


def session_user(token):
    """The active user for a session token, or None."""
    if not token:
        return None
    if _IS_VERCEL:
        user_id = _web_verify(token)
        if not user_id:
            return None
        user = _get(user_id)
        return public(user) if user and user["active"] else None

    now = time.time()
    with _lock:
        s = _sessions.get(token)
        if not s:
            return None
        if s["expires"] < now:
            _sessions.pop(token, None)
            return None
        s["expires"] = now + SESSION_SECONDS
        user_id = s["user_id"]
    user = _get(user_id)
    if not user or not user["active"]:
        return None
    return public(user)


def logout(token):
    with _lock:
        _sessions.pop(token, None)


def end_sessions_for(user_id):
    with _lock:
        for t in [t for t, s in _sessions.items() if s["user_id"] == user_id]:
            _sessions.pop(t, None)


# ------------------------------------------------------------------ recovery command
def _cli_reset_advisor():
    import getpass

    db.init()
    username = input("Advisor username to create or reset: ").strip().lower()
    pw = getpass.getpass("New password: ")
    existing = db.one("SELECT id FROM users WHERE username=?", (_username(username),))
    if existing:
        db.execute("UPDATE users SET role='advisor', active=1 WHERE id=?", (existing["id"],))
        reset_password(existing["id"], pw, temporary=False)
    else:
        create_user(username, input("Full name: "), "advisor", pw, "recovery command", must_change=False)
    print("Done. You can sign in as an academic advisor now.")


if __name__ == "__main__":
    if sys.argv[1:] == ["reset-advisor"]:
        try:
            _cli_reset_advisor()
        except (ValueError, KeyboardInterrupt) as exc:
            print(f"Not changed: {exc}")
    else:
        print("Usage: python -m backend.utilities.accounts reset-advisor")
