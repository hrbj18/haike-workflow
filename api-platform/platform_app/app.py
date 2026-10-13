import asyncio
import csv
import hmac
import io
import json
import re
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from . import (
    auth,
    commerce_routes,
    deployment,
    domain,
    funding,
    gateway,
    pricing,
    providers,
)
from .exports import csv_response
from .store import Problem, Store, audit, digest, now, owned
from .worker import recover_interrupted, run_worker

ROOT = Path(__file__).resolve().parents[1]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Credentials(Input):
    # Keep the persisted email column and legacy request field for existing accounts.
    email: str = Field(
        min_length=1, max_length=120, validation_alias=AliasChoices("username", "email")
    )
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def valid_username(cls, value):
        value = value.strip().lower()
        if not value:
            raise ValueError("请填写用户名")
        return value


class Registration(Credentials):
    name: str | None = Field(default=None, min_length=1, max_length=40)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if value is None:
            return value
        if not value.strip():
            raise ValueError("请填写显示名称")
        return value.strip()


class PasswordChange(Input):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class NewKey(Input):
    name: str = Field(min_length=1, max_length=60)
    daily_limit_micros: str = Field(pattern=r"^[0-9]{1,13}$")
    expires_days: int = Field(default=90, ge=1, le=365)


class Recharge(Input):
    amount_fen: int = Field(ge=100, le=1000000)
    currency: Literal["CNY"] = "CNY"


class Quote(Input):
    model: str = Field(max_length=80)
    input: dict
    project_ref: str = Field(default="", max_length=100)


class QuoteRenew(Input):
    confirmed: Literal[True]


class Submit(Input):
    quote_id: str = Field(max_length=80)
    max_charge_micros: str = Field(pattern=r"^[0-9]{1,13}$")
    call_intent_id: str = Field(min_length=8, max_length=100)
    currency: Literal["CNY"] = "CNY"
    confirmed: Literal[True]


class Rule(Input):
    mode: Literal["markup", "margin", "fixed"]
    cost_micros: str = Field(pattern=r"^[0-9]{1,13}$")
    multiplier: str = Field(max_length=16)
    margin: str = Field(max_length=16)
    fixed_micros: str = Field(pattern=r"^[0-9]{1,13}$")
    fee_micros: str = Field(pattern=r"^[0-9]{1,13}$")


class NewPrice(Input):
    model: str = Field(max_length=80)
    rule: Rule


class PricePreview(NewPrice):
    quantity: int = Field(ge=1, le=20000)


class Reconcile(Input):
    outcome: Literal["succeeded", "failed"]


def create_app(db_path=None, worker_enabled=True, testing=False, public_origin=None):
    public_origin = deployment.public_origin(public_origin)
    store = Store(db_path or ROOT / "data" / "platform.sqlite3")
    vault = providers.Vault(store.path.parent)

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        if public_origin:
            with store.read() as db:
                if not db.execute("SELECT id FROM users WHERE role='admin'").fetchone():
                    raise RuntimeError("Initialize an administrator before public deployment")
        pricing.seed_prices(store)
        providers.seed(store)
        gateway.recover(store)
        recover_interrupted(store)
        task = asyncio.create_task(run_worker(store)) if worker_enabled else None
        gateway_task = (
            asyncio.create_task(gateway.run_worker(store, vault))
            if worker_enabled
            else None
        )
        app.state.worker = task
        app.state.gateway_worker = gateway_task
        try:
            yield
        finally:
            if gateway_task:
                gateway_task.cancel()
                with suppress(asyncio.CancelledError):
                    await gateway_task
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        title="海客科技 · API 账户与统一网关",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.store = store
    app.state.vault = vault
    app.state.worker = None
    app.state.gateway_worker = None
    login_failures = {}

    @app.exception_handler(Problem)
    async def problem_handler(request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}},
            status_code=error.status,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, error):
        # Never echo passwords, API keys or submitted media/text in validation errors.
        fields = [".".join(str(v) for v in e["loc"]) for e in error.errors()]
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_request",
                    "message": "参数格式不正确",
                    "fields": fields,
                }
            },
            status_code=422,
        )

    @app.middleware("http")
    async def sandbox_boundary(request, call_next):
        host = request.url.hostname
        client = request.client.host if request.client else ""
        local = {"127.0.0.1", "localhost", "::1"}
        origin_allowed = (
            str(request.base_url).rstrip("/") == public_origin
            if public_origin
            else host in local and (client in local or (testing and client == "testclient"))
        )
        if not origin_allowed:
            return JSONResponse(
                {
                    "error": {
                        "code": "origin_not_allowed" if public_origin else "local_only",
                        "message": "请使用配置的 HTTPS 地址访问" if public_origin else "本地模拟版只允许回环地址访问",
                    }
                },
                status_code=403,
            )
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
                return JSONResponse(
                    {"error": {"code": "origin_rejected", "message": "请求来源不匹配"}},
                    status_code=403,
                )
            if not request.url.path.startswith("/v2/") and not origin:
                return JSONResponse(
                    {
                        "error": {
                            "code": "origin_required",
                            "message": "账户中心写操作需要同源请求",
                        }
                    },
                    status_code=403,
                )
            if len(await request.body()) > (
                5 * 1024 * 1024 if request.url.path == "/v2/files" else 100000
            ):
                return JSONResponse(
                    {"error": {"code": "request_too_large", "message": "请求过大"}},
                    status_code=413,
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        )
        return response

    def portal_user(request: Request):
        user = auth.session_user(store, request.cookies.get("haike_session", ""))
        if request.method not in {"GET", "HEAD"} and not hmac.compare_digest(
            request.headers.get("x-csrf-token", ""), user["csrf"]
        ):
            raise Problem(403, "csrf_rejected", "页面会话已变化，请刷新后重试")
        if user["must_change_password"] and request.url.path not in {
            "/portal/v1/me",
            "/portal/v1/password",
            "/portal/v1/logout",
        }:
            raise Problem(
                403,
                "password_change_required",
                "请先修改初始密码，再使用充值和 API 服务",
            )
        return user

    def admin_user(user=Depends(portal_user)):
        if user["role"] != "admin":
            raise Problem(403, "admin_required", "需要管理员权限")
        return user

    def api_user(authorization: str | None = Header(default=None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise Problem(401, "key_required", "请提供 Bearer API Key")
        return auth.key_user(store, authorization[7:])

    def idem_key(idempotency_key: str | None = Header(default=None)):
        if not idempotency_key or not re.fullmatch(
            r"[A-Za-z0-9_.:-]{8,100}", idempotency_key
        ):
            raise Problem(422, "idempotency_required", "需要 8–100 位 Idempotency-Key")
        return idempotency_key

    def set_session(response, token):
        response.set_cookie(
            "haike_session",
            token,
            max_age=86400 * 14,
            httponly=True,
            samesite="strict",
            secure=bool(public_origin),
            path="/",
        )

    @app.get("/health")
    def health():
        tasks = (app.state.worker, app.state.gateway_worker)
        return {
            "status": "worker_stopped"
            if any(task and task.done() for task in tasks)
            else "ok",
            "mode": "cloud_commercial" if public_origin else "local_commercial",
            "real_payments": False,
            "real_providers": any(
                r["status"] == "available" for r in providers.catalogue(store, vault)
            ),
        }

    @app.get("/portal/v1/setup-status")
    def setup_status():
        with store.read() as db:
            return {
                "setup_required": db.execute("SELECT count(*) FROM users").fetchone()[0]
                == 0,
                "simulation": not bool(public_origin),
                "environment": "cloud" if public_origin else "local",
            }

    @app.post("/portal/v1/setup")
    def setup(body: Registration, response: Response):
        if public_origin:
            raise Problem(403, "setup_disabled", "云端管理员初始化入口已关闭")
        result, token = auth.register(
            store, body.email, body.name or body.email, body.password, setup=True
        )
        set_session(response, token)
        return result

    @app.post("/portal/v1/register")
    def register(body: Registration, response: Response):
        result, token = auth.register(store, body.email, body.name or body.email, body.password)
        set_session(response, token)
        return result

    @app.post("/portal/v1/login")
    def login(body: Credentials, response: Response):
        bucket = digest(body.email)
        timestamp = time.monotonic()
        failures = [t for t in login_failures.get(bucket, []) if timestamp - t < 60]
        if len(failures) >= 5:
            raise Problem(429, "login_rate_limit", "尝试过多，请一分钟后重试")
        try:
            result, token = auth.login(store, body.email, body.password)
        except Problem:
            login_failures[bucket] = failures + [timestamp]
            raise
        login_failures.pop(bucket, None)
        set_session(response, token)
        return result

    @app.post("/portal/v1/logout")
    def logout(request: Request, response: Response, user=Depends(portal_user)):
        with store.write() as db:
            db.execute(
                "DELETE FROM sessions WHERE token_hash=?",
                (digest(request.cookies["haike_session"]),),
            )
        response.delete_cookie("haike_session", path="/")
        return {"ok": True}

    @app.get("/portal/v1/me")
    def me(user=Depends(portal_user)):
        return {
            "user": auth.public_user(user),
            "csrf": user["csrf"],
            "simulation": not bool(public_origin),
        }

    @app.post("/portal/v1/password")
    def password(body: PasswordChange, response: Response, user=Depends(portal_user)):
        auth.change_password(
            store, user["id"], body.current_password, body.new_password
        )
        result, token = auth.login(store, user["email"], body.new_password)
        set_session(response, token)
        return result

    @app.get("/portal/v1/funding-info")
    def funding_info():
        return funding.info(store)

    @app.get("/portal/v1/wallet")
    def get_wallet(user=Depends(portal_user)):
        return domain.wallet(store, user["id"])

    @app.get("/portal/v1/ledger")
    def get_ledger(user=Depends(portal_user)):
        return {"items": domain.ledger(store, user["id"])}

    @app.get("/portal/v1/ledger/export")
    def export_ledger(user=Depends(portal_user)):
        return csv_response(
            [
                "凭证",
                "时间 UTC",
                "事件",
                "关联记录",
                "可用变动微元",
                "冻结变动微元",
                "可用余额微元",
                "冻结余额微元",
            ],
            (
                [
                    r["id"],
                    r["created_at"],
                    r["kind"],
                    r["reference"],
                    r["postings"].get("available", "0"),
                    r["postings"].get("reserved", "0"),
                    r["available_after_micros"],
                    r["reserved_after_micros"],
                ]
                for r in domain.ledger(store, user["id"])
            ),
            "haike-ledger.csv",
        )

    @app.get("/portal/v1/recharges")
    def orders(user=Depends(portal_user)):
        with store.read() as db:
            return {
                "items": [
                    domain.order_public(r)
                    for r in db.execute(
                        "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 100",
                        (user["id"],),
                    )
                ]
            }

    @app.post("/portal/v1/recharges")
    def recharge(body: Recharge, user=Depends(portal_user), idem=Depends(idem_key)):
        return domain.create_order(store, user["id"], body.amount_fen, idem)

    @app.post("/portal/v1/recharges/{order_id}/mock-confirm")
    def confirm(order_id: str, user=Depends(portal_user)):
        if any(c["configured"] for c in vault.public()):
            raise Problem(
                409, "simulation_disabled", "商业模式已启用，请由管理员充值或使用兑换码"
            )
        return domain.mock_pay(store, user["id"], order_id)

    @app.get("/portal/v1/api-keys")
    def keys(user=Depends(portal_user)):
        with store.read() as db:
            return {
                "items": [
                    auth.key_public(r)
                    for r in db.execute(
                        "SELECT * FROM api_keys WHERE user_id=? ORDER BY created_at DESC",
                        (user["id"],),
                    )
                ]
            }

    @app.post("/portal/v1/api-keys")
    def create_key(body: NewKey, user=Depends(portal_user)):
        limit = pricing.amount_string(body.daily_limit_micros, allow_zero=False)
        return auth.create_key(store, user["id"], body.name, limit, body.expires_days)

    @app.post("/portal/v1/api-keys/{key_id}/revoke")
    def revoke(key_id: str, user=Depends(portal_user)):
        with store.write() as db:
            owned(db, "api_keys", key_id, user["id"])
            db.execute(
                "UPDATE api_keys SET revoked_at=coalesce(revoked_at,?) WHERE id=?",
                (now(), key_id),
            )
            audit(db, user["id"], "revoke_key", key_id)
        return {"ok": True}

    @app.get("/portal/v1/bills/export")
    def export(
        model: str | None = None, status: str | None = None, user=Depends(portal_user)
    ):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(
            [
                "任务",
                "日期 UTC",
                "项目",
                "Key",
                "模型",
                "状态",
                "单位",
                "用量",
                "价格版本",
                "冻结上限微元",
                "实扣微元",
                "模拟服务",
                "完整计量回执 JSON",
                "固定单价 JSON",
                "供应商任务编号",
                "加价系数",
                "逐项费用 JSON",
                "合计舍入调整微元",
                "费用上限减免微元",
                "释放额度微元",
            ]
        )
        for bill in combined_jobs(user, model, status):
            values = [
                bill["id"],
                bill["created_at"],
                bill["project_ref"],
                bill["key_name"],
                bill["model"],
                bill["status"],
                bill["price"]["unit"],
                bill["quantity"],
                bill["price"]["version"],
                bill["max_charge_micros"],
                bill["charged_micros"],
                "是" if bill["simulation"] else "否",
                json.dumps(bill.get("usage", {}), ensure_ascii=False),
                json.dumps(bill["price"].get("rates", []), ensure_ascii=False),
                bill.get("upstream_id") or "",
                bill.get("billing", {}).get("multiplier", ""),
                json.dumps(
                    bill.get("billing", {}).get("lines", []), ensure_ascii=False
                ),
                bill.get("billing", {}).get("rounding_adjustment_micros", ""),
                bill.get("billing", {}).get("ceiling_discount_micros", ""),
                bill.get("billing", {}).get("released_micros", ""),
            ]
            writer.writerow(
                [
                    "'" + str(v)
                    if str(v).startswith(("=", "+", "-", "@", "\t", "\r"))
                    else v
                    for v in values
                ]
            )
        return Response(
            "\ufeff" + stream.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="haike-bills.csv"'},
        )

    @app.get("/portal/v1/bills")
    def bills(
        model: str | None = None, status: str | None = None, user=Depends(portal_user)
    ):
        return {"items": combined_jobs(user, model, status), "limit": 500}

    @app.get("/portal/v1/bills/{job_id}")
    def bill(job_id: str, user=Depends(portal_user)):
        return (
            gateway.get_job(store, user, job_id)
            if job_id.startswith("gj_")
            else domain.get_job(store, user, job_id)
        )

    @app.post("/portal/v1/bills/{job_id}/cancel")
    def cancel_bill(job_id: str, user=Depends(portal_user)):
        return (
            gateway.cancel(store, user, job_id)
            if job_id.startswith("gj_")
            else domain.cancel_job(store, user, job_id)
        )

    @app.get("/portal/v1/catalogue")
    def portal_catalogue(user=Depends(portal_user)):
        items = providers.catalogue(store, vault)
        return {
            "items": pricing.catalogue(store) + items
            if user["role"] == "admin"
            else [m for m in items if m["status"] == "available"]
        }

    @app.get("/v2/capabilities")
    @app.get("/v2/prices")
    def capabilities(user=Depends(api_user)):
        return {
            "items": [
                m
                for m in providers.catalogue(store, vault)
                if m["status"] == "available"
            ],
            "mode": "local_commercial",
        }

    @app.get("/v2/account/summary")
    def summary(user=Depends(api_user)):
        return {
            "account_name": user["name"],
            "key_id": user["key_id"],
            **domain.wallet(store, user["id"]),
        }

    @app.get("/v2/account/usage")
    def usage(user=Depends(api_user)):
        return {"items": combined_jobs(user)}

    @app.post("/v2/quotes")
    def quotes(body: Quote, user=Depends(api_user)):
        if not body.model.startswith("demo/"):
            return gateway.create_quote(
                store, vault, user, body.model, body.input, body.project_ref
            )
        return domain.create_quote(
            store, user, body.model, body.input, body.project_ref
        )

    @app.post("/v2/quotes/{quote_id}/renew")
    def renew_quote(quote_id: str, body: QuoteRenew, user=Depends(api_user)):
        return gateway.renew_quote(store, vault, user, quote_id)

    @app.post("/v2/jobs")
    def jobs(body: Submit, user=Depends(api_user), idem=Depends(idem_key)):
        if body.quote_id.startswith("gquote_"):
            return gateway.accept(
                store,
                vault,
                user,
                body.quote_id,
                pricing.amount_string(body.max_charge_micros),
                body.call_intent_id,
                idem,
            )
        return domain.accept_job(
            store,
            user,
            body.quote_id,
            pricing.amount_string(body.max_charge_micros),
            body.call_intent_id,
            idem,
        )

    @app.get("/v2/requests/{idem}")
    def recover(idem: str, user=Depends(api_user)):
        with store.read() as db:
            row = db.execute(
                "SELECT * FROM idempotency WHERE user_id=? AND operation='job' AND idem_key=?",
                (user["id"], idem),
            ).fetchone()
        if not row:
            raise Problem(404, "not_found", "该请求尚未被接受")
        return (
            gateway.get_job(store, user, row["resource_id"])
            if row["resource_id"].startswith("gj_")
            else domain.get_job(store, user, row["resource_id"])
        )

    @app.get("/v2/jobs/{job_id}")
    def job(job_id: str, user=Depends(api_user)):
        return (
            gateway.get_job(store, user, job_id)
            if job_id.startswith("gj_")
            else domain.get_job(store, user, job_id)
        )

    @app.post("/v2/jobs/{job_id}/cancel")
    def cancel(job_id: str, user=Depends(api_user)):
        return (
            gateway.cancel(store, user, job_id)
            if job_id.startswith("gj_")
            else domain.cancel_job(store, user, job_id)
        )

    @app.post("/admin/v1/price-versions/preview")
    def preview(body: PricePreview, user=Depends(admin_user)):
        clean = pricing.normalize_rule(body.model, body.rule.model_dump())
        return pricing.calculate(body.model, clean, body.quantity)

    @app.post("/admin/v1/price-versions")
    def save_price(body: NewPrice, user=Depends(admin_user)):
        return domain.save_price(store, user["id"], body.model, body.rule.model_dump())

    @app.post("/admin/v1/price-versions/{price_id}/publish")
    def publish(price_id: str, user=Depends(admin_user)):
        return domain.publish_price(store, user["id"], price_id)

    @app.get("/admin/v1/price-versions")
    def price_versions(user=Depends(admin_user)):
        with store.read() as db:
            return {
                "items": [
                    {**dict(r), "rule": json.loads(r["rule"])}
                    for r in db.execute(
                        "SELECT * FROM prices ORDER BY created_at DESC LIMIT 100"
                    )
                ]
            }

    @app.get("/admin/v1/reconciliation")
    def pending(user=Depends(admin_user)):
        with store.read() as db:
            rows = db.execute(
                "SELECT * FROM jobs WHERE funds_status='reconciliation_pending' OR status='cancel_pending' ORDER BY created_at"
            ).fetchall()
            return {"items": [domain.job_public(db, r) for r in rows]}

    @app.post("/admin/v1/reconciliation/{job_id}/mock-resolve")
    def resolve(job_id: str, body: Reconcile, user=Depends(admin_user)):
        return domain.reconcile(store, user["id"], job_id, body.outcome)

    @app.get("/admin/v1/ledger-check")
    def ledger_check(user=Depends(admin_user)):
        return domain.verify_ledger(store)

    @app.get("/admin/v1/audit")
    def audit_log(user=Depends(admin_user)):
        with store.read() as db:
            return {
                "items": [
                    dict(r)
                    for r in db.execute(
                        "SELECT * FROM audit ORDER BY created_at DESC LIMIT 100"
                    )
                ]
            }

    def combined_jobs(user, model=None, status=None):
        return sorted(
            domain.list_jobs(store, user, model, status)
            + gateway.list_jobs(store, user, model, status),
            key=lambda j: j["created_at"],
            reverse=True,
        )[:500]

    app.include_router(
        commerce_routes.router(
            store, vault, portal_user, admin_user, api_user, idem_key, Registration
        )
    )
    app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")

    @app.get("/docs", include_in_schema=False)
    def api_docs():
        return FileResponse(ROOT / "web" / "api-docs.html")

    @app.get("/")
    @app.get("/admin")
    def index():
        return FileResponse(ROOT / "web" / "index.html")

    return app
