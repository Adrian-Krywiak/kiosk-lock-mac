"""Files on disk: the friend-held password hash and the active lock."""

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

# KIOSKLOCK_HOME lets tests and demos use a throwaway folder.
HOME = Path(os.environ.get("KIOSKLOCK_HOME") or os.path.expanduser("~/.kiosklock"))
CONFIG_PATH = HOME / "config.json"
LOCK_PATH = HOME / "lock.json"


def _read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _write(path, data):
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)
    os.chmod(path, 0o600)


# --- password ---------------------------------------------------------------

def _derive(password, salt_hex):
    return hashlib.scrypt(
        password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1, dklen=32
    ).hex()


def set_password(password):
    """Store only a scrypt hash. The password itself never touches the disk."""
    cfg = _read(CONFIG_PATH)
    cfg["unlock_salt"] = secrets.token_hex(16)
    cfg["unlock_hash"] = _derive(password, cfg["unlock_salt"])
    _write(CONFIG_PATH, cfg)


def has_password():
    return bool(_read(CONFIG_PATH).get("unlock_hash"))


def check_password(password):
    cfg = _read(CONFIG_PATH)
    if not cfg.get("unlock_hash"):
        return False
    return hmac.compare_digest(_derive(password, cfg["unlock_salt"]), cfg["unlock_hash"])


# --- the active lock ----------------------------------------------------------

def save_lock(url, allowed_hosts, until, message):
    _write(LOCK_PATH, {
        "url": url,
        "allowed_hosts": list(allowed_hosts),
        "until": float(until),
        "message": message,
        "started": time.time(),
    })


def active_lock():
    """The saved lock if it hasn't run out yet, otherwise None."""
    lock = _read(LOCK_PATH)
    if lock.get("until", 0) > time.time() and lock.get("url"):
        return lock
    return None


def clear_lock():
    try:
        LOCK_PATH.unlink()
    except FileNotFoundError:
        pass
