

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from openshores.core.logging import get_logger

logger = get_logger(__name__)


_SCHEMA_VERSION = 1
_PBKDF2_ITERS = 200_000
_SALT_BYTES = 16
_HASH_BYTES = 32

DEFAULT_PATH = Path("accounts.json")


class AccountError(Exception):
    pass


class UserNotFound(AccountError):
    pass


class UserExists(AccountError):
    pass


class BadPassword(AccountError):
    pass


class AccountStore:
    def __init__(self, path: os.PathLike | str = DEFAULT_PATH):
        self.path = Path(path)
        self._data: dict = self._load()
        self._loaded_mtime: float = self._current_mtime()

    def _current_mtime(self) -> float:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return 0.0

    def _maybe_reload(self) -> None:
        cur = self._current_mtime()
        if cur and cur != self._loaded_mtime:
            try:
                self._data = self._load()
                self._loaded_mtime = cur
                logger.info(
                    "Reloaded %s after an external write; %d account(s) "
                    "now known.",
                    self.path, len(self._data.get("users", {})))
            except Exception as e:
                logger.warning(
                    "Could not reload %s; keeping the accounts already in "
                    "memory, which may now be behind the file: %r",
                    self.path, e)

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": _SCHEMA_VERSION, "users": {}}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                d = json.load(f)
            if "users" not in d:
                d = {"version": _SCHEMA_VERSION, "users": {}}
            return d
        except Exception as e:
            import time as _time_load
            stamp = _time_load.strftime("%Y%m%d-%H%M%S")
            backup = self.path.with_suffix(
                self.path.suffix + f".corrupt-{stamp}.bak")
            try:
                os.replace(self.path, backup)
                logger.error(
                    'Account store %s is unreadable (%s). Moved it to %s and started with no accounts.',
                    self.path, e, backup)
            except Exception as _be:
                logger.error(
                    'Account store %s is unreadable (%s) and could not be moved aside (%r).',
                    self.path, e, _be)
            return {"version": _SCHEMA_VERSION, "users": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=".accounts.", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
            self._loaded_mtime = self._current_mtime()
        except Exception:
            os.unlink(tmp)
            raise

    def has_user(self, username: str) -> bool:
        self._maybe_reload()
        return username in self._data["users"]

    def list_users(self) -> list[str]:
        self._maybe_reload()
        return sorted(self._data["users"].keys())

    def create(self, username: str, password: bytes,
               avatars: Optional[Iterable[int]] = None) -> None:
        if username in self._data["users"]:
            raise UserExists(username)
        salt = secrets.token_bytes(_SALT_BYTES)
        h = hashlib.pbkdf2_hmac("sha256", password, salt, _PBKDF2_ITERS,
                                dklen=_HASH_BYTES)
        self._data["users"][username] = {
            "salt": salt.hex(),
            "hash": h.hex(),
            "avatars": list(int(a) for a in (avatars or [])),
        }
        self._save()

    def delete(self, username: str) -> None:
        if username not in self._data["users"]:
            raise UserNotFound(username)
        del self._data["users"][username]
        self._save()

    def set_password(self, username: str, password: bytes) -> None:
        rec = self._data["users"].get(username)
        if rec is None:
            raise UserNotFound(username)
        salt = secrets.token_bytes(_SALT_BYTES)
        h = hashlib.pbkdf2_hmac("sha256", password, salt, _PBKDF2_ITERS,
                                dklen=_HASH_BYTES)
        rec["salt"] = salt.hex()
        rec["hash"] = h.hex()
        self._save()

    def verify(self, username: str, password: bytes) -> bool:
        self._maybe_reload()
        rec = self._data["users"].get(username)
        if rec is None:
            hashlib.pbkdf2_hmac("sha256", password,
                                b"\x00" * _SALT_BYTES, _PBKDF2_ITERS,
                                dklen=_HASH_BYTES)
            return False
        salt = bytes.fromhex(rec["salt"])
        want = bytes.fromhex(rec["hash"])
        got = hashlib.pbkdf2_hmac("sha256", password, salt, _PBKDF2_ITERS,
                                  dklen=_HASH_BYTES)
        return hmac.compare_digest(got, want)

    def list_avatars(self, username: str) -> list[int]:
        self._maybe_reload()
        rec = self._data["users"].get(username)
        if rec is None:
            raise UserNotFound(username)
        return list(rec.get("avatars", []))

    def add_avatar(self, username: str, auid: int) -> bool:
        rec = self._data["users"].get(username)
        if rec is None:
            raise UserNotFound(username)
        avs = rec.setdefault("avatars", [])
        if int(auid) in avs:
            return False
        avs.append(int(auid))
        try:
            self._save()
        except Exception as e:
            avs.remove(int(auid))
            raise AccountError(
                f"add_avatar({username!r}, {auid}) save failed: {e}")
        try:
            verify = self._load()
            verify_avs = (verify.get("users", {})
                              .get(username, {})
                              .get("avatars", []))
            if int(auid) not in verify_avs:
                raise AccountError(
                    f"add_avatar({username!r}, {auid}) post-write verify failed: not present on disk after save (disk roster: {verify_avs})")
        except AccountError:
            raise
        except Exception as e:
            logger.warning(
                "Wrote avatar %d for %r to %s but could not read it back to confirm: %r.",
                auid, username, self.path, e)
        return True

    def remove_avatar(self, username: str, auid: int) -> None:
        rec = self._data["users"].get(username)
        if rec is None:
            raise UserNotFound(username)
        avs = rec.get("avatars", [])
        if int(auid) in avs:
            avs.remove(int(auid))
            self._save()


_DEFAULT_STORE: Optional[AccountStore] = None


def default_store() -> AccountStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = AccountStore()
    return _DEFAULT_STORE


REASON_NO_SUCH_ACCOUNT = 1
REASON_BAD_PASSWORD = 2
REASON_SERVER_ERROR = 3


_FIRST_PASSWORD_BYTES = 24


def _wire_password(typed: str) -> bytes:
    return hashlib.sha1(typed.encode("utf-8")).digest()


def ensure_default_account(store: AccountStore, *, username: str) -> bool:
    if store.list_users():
        return False
    typed = secrets.token_urlsafe(_FIRST_PASSWORD_BYTES)
    store.create(username, _wire_password(typed))
    logger.warning(
        "\n  First run: account %r password %s\n"
        "  Write it down. It is not stored; only its hash is in %s.",
        username, typed, store.path)
    return True
