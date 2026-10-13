import hashlib
import hmac
import secrets
import sqlite3

from .store import Problem, audit, digest, later, now, uid


def password_hash(password):
    salt = secrets.token_bytes(16)
    hashed = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return salt.hex() + ":" + hashed.hex()


def password_matches(password, stored):
    salt, expected = stored.split(":")
    actual = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1
    )
    return hmac.compare_digest(actual.hex(), expected)


def public_user(user):
    result = {k: user[k] for k in ("id", "email", "name", "role")}
    result["username"] = user["email"]
    result["must_change_password"] = bool(dict(user).get("must_change_password", 0))
    return result


def access(db, user_id):
    row = db.execute("SELECT * FROM user_access WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else {"status": "active", "must_change_password": 0}


def ensure_active(db, user_id, api=False):
    info = access(db, user_id)
    if info["status"] != "active":
        raise Problem(403, "account_disabled", "账户已停用，请联系管理员")
    if api and info["must_change_password"]:
        raise Problem(403, "password_change_required", "请登录账户中心修改初始密码")
    return info


def register(store, email, name, password, setup=False):
    # First administrator setup is deliberately restricted to this loopback-only sandbox.
    email = email.strip().lower()
    hashed = password_hash(password)
    with store.write() as db:
        count = db.execute("SELECT count(*) FROM users").fetchone()[0]
        if setup and count:
            raise Problem(409, "already_initialized", "管理员已经设置，请登录")
        if not setup and not count:
            raise Problem(409, "setup_required", "请先设置本地管理员")
        user_id = uid("usr")
        try:
            db.execute(
                "INSERT INTO users VALUES(?,?,?,?,?,?)",
                (
                    user_id,
                    email.lower(),
                    name,
                    hashed,
                    "admin" if setup else "customer",
                    now(),
                ),
            )
        except sqlite3.IntegrityError:
            raise Problem(409, "username_exists", "用户名已被使用") from None
        db.execute("INSERT INTO wallets(user_id) VALUES(?)", (user_id,))
        audit(db, user_id, "setup_admin" if setup else "register", user_id)
    return login(store, email, password)


def login(store, email, password):
    with store.write() as db:
        user = db.execute(
            "SELECT * FROM users WHERE email=?", (email.strip().lower(),)
        ).fetchone()
        if not user or not password_matches(password, user["password_hash"]):
            raise Problem(401, "invalid_login", "用户名或密码不正确")
        info = ensure_active(db, user["id"])
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        db.execute("DELETE FROM sessions WHERE expires_at<?", (now(),))
        db.execute(
            "INSERT INTO sessions VALUES(?,?,?,?)",
            (digest(token), user["id"], csrf, later(86400 * 14)),
        )
    return {"user": public_user({**dict(user), **info}), "csrf": csrf}, token


def session_user(store, token):
    with store.read() as db:
        row = db.execute(
            "SELECT u.*,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=? AND s.expires_at>?",
            (digest(token), now()),
        ).fetchone()
        if not row:
            raise Problem(401, "login_required", "请先登录账户中心")
        info = ensure_active(db, row["id"])
    return {**dict(row), **info}


def require_key(db, token=None, key_id=None):
    if token:
        row = db.execute(
            "SELECT * FROM api_keys WHERE token_hash=?", (digest(token),)
        ).fetchone()
    else:
        row = db.execute("SELECT * FROM api_keys WHERE id=?", (key_id,)).fetchone()
    if (
        not row
        or row["revoked_at"]
        or (row["expires_at"] and row["expires_at"] <= now())
    ):
        raise Problem(401, "invalid_key", "Key 无效、已撤销或已过期")
    ensure_active(db, row["user_id"], api=True)
    return dict(row)


def change_password(store, user_id, current, new):
    with store.write() as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        ensure_active(db, user_id)
        if not password_matches(current, user["password_hash"]):
            raise Problem(401, "invalid_password", "当前密码不正确")
        if current == new:
            raise Problem(422, "unchanged_password", "新密码不能与当前密码相同")
        db.execute(
            "UPDATE users SET password_hash=? WHERE id=?", (password_hash(new), user_id)
        )
        db.execute(
            "INSERT INTO user_access(user_id) VALUES(?) ON CONFLICT(user_id) DO NOTHING",
            (user_id,),
        )
        db.execute(
            "UPDATE user_access SET must_change_password=0 WHERE user_id=?", (user_id,)
        )
        db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        audit(db, user_id, "change_password", user_id)


def manage_customer(store, actor, user_id, status=None, password=None):
    with store.write() as db:
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise Problem(404, "not_found", "用户不存在")
        if row["role"] != "customer":
            raise Problem(
                403, "customer_required", "此操作仅适用于普通用户，管理员请自行修改密码"
            )
        db.execute(
            "INSERT INTO user_access(user_id) VALUES(?) ON CONFLICT(user_id) DO NOTHING",
            (user_id,),
        )
        if status is not None:
            db.execute(
                "UPDATE user_access SET status=? WHERE user_id=?", (status, user_id)
            )
            action = "disable_customer" if status == "disabled" else "enable_customer"
        else:
            db.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (password_hash(password), user_id),
            )
            db.execute(
                "UPDATE user_access SET must_change_password=1 WHERE user_id=?",
                (user_id,),
            )
            action = "reset_customer_password"
        db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        audit(db, actor, action, user_id)
    return {"ok": True}


def key_user(store, token):
    with store.read() as db:
        key = require_key(db, token=token)
        user = db.execute(
            "SELECT * FROM users WHERE id=?", (key["user_id"],)
        ).fetchone()
    return {**public_user(user), "key_id": key["id"]}


def key_public(key):
    return {
        k: str(key[k]) if k == "daily_limit" else key[k]
        for k in (
            "id",
            "name",
            "prefix",
            "daily_limit",
            "created_at",
            "expires_at",
            "revoked_at",
            "last_used_at",
        )
    }


def create_key(store, user_id, name, daily_limit, expires_days):
    token = "hk_" + secrets.token_urlsafe(32)
    key_id = uid("key")
    with store.write() as db:
        db.execute(
            "INSERT INTO api_keys VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                key_id,
                user_id,
                name,
                digest(token),
                token[:16],
                daily_limit,
                now(),
                later(expires_days * 86400),
                None,
                None,
            ),
        )
        audit(db, user_id, "create_key", key_id)
        key = db.execute("SELECT * FROM api_keys WHERE id=?", (key_id,)).fetchone()
    return {"key": key_public(key), "secret": token, "show_once": True}
