"""Portal administration stays cookie/CSRF protected; all gateway calls use a platform Key."""

import json
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from . import auth, commerce, funding, gateway, pricing, providers
from .exports import csv_response
from .store import Problem, audit, now


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Credit(Input):
    amount_micros: str = Field(pattern=r"^[0-9]{1,13}$")
    note: str = Field(default="管理员手动充值", min_length=1, max_length=200)
    channel: Literal["private", "wechat", "alipay", "bank"] = "private"
    payment_ref: str = Field(default="", max_length=100)
    received_confirmed: Literal[True] = True


class Codes(Input):
    amount_micros: str = Field(pattern=r"^[0-9]{1,13}$")
    count: int = Field(default=1, ge=1, le=100)
    expires_days: int = Field(default=30, ge=1, le=365)
    batch: str = Field(min_length=1, max_length=80)
    bound_user_id: str | None = Field(default=None, max_length=80)
    channel: Literal["private", "wechat", "alipay", "bank"] = "private"
    payment_ref: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=200)
    received_confirmed: Literal[True] = True


class UserStatus(Input):
    status: Literal["active", "disabled"]


class ResetPassword(Input):
    password: str = Field(min_length=1, max_length=128)


class FundingInfo(Input):
    contact: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=1000)


class Redeem(Input):
    code: str = Field(min_length=8, max_length=80)


class Config(Input):
    config: dict


class Channel(Input):
    id: str = Field(max_length=50)
    name: str = Field(min_length=1, max_length=60)
    base_url: str = Field(min_length=1, max_length=300)
    api_key: str = Field(min_length=1, max_length=500)


class ModelRoute(Input):
    model: str = Field(max_length=80)
    name: str = Field(min_length=1, max_length=60)
    provider: str = Field(max_length=50)
    target_model: str = Field(min_length=1, max_length=100)
    enabled: bool = False


class Tariff(Input):
    model: str = Field(max_length=80)
    rule: dict


class Preview(Tariff):
    usage: dict


class Resolve(Input):
    outcome: Literal["succeeded", "failed"]
    usage: dict = Field(default_factory=dict)
    evidence: str = Field(min_length=10, max_length=500)


def router(store, vault, portal_user, admin_user, api_user, idem_key, registration):
    routes = APIRouter()

    @routes.get("/admin/v1/users")
    def users(search: str = "", user=Depends(admin_user)):
        return {"items": commerce.users(store, search[:120]), "limit": 500}

    @routes.post("/admin/v1/users/{user_id}/status")
    def user_status(user_id: str, body: UserStatus, user=Depends(admin_user)):
        return auth.manage_customer(store, user["id"], user_id, status=body.status)

    @routes.post("/admin/v1/users/{user_id}/password")
    def reset_password(user_id: str, body: ResetPassword, user=Depends(admin_user)):
        return auth.manage_customer(store, user["id"], user_id, password=body.password)

    @routes.post("/admin/v1/funding-info")
    def funding_info(body: FundingInfo, user=Depends(admin_user)):
        return funding.configure(store, user["id"], body.contact, body.instructions)

    @routes.get("/portal/v1/funding-history")
    def funding_history(user=Depends(portal_user)):
        return {"items": funding.history(store, user["id"]), "limit": 500}

    @routes.get("/admin/v1/funding-history")
    def admin_funding(user=Depends(admin_user)):
        return {
            "items": funding.history(store),
            "receipts": funding.receipts(store),
            "limit": 500,
        }

    @routes.get("/admin/v1/funding-history/export")
    def export_funding(user=Depends(admin_user)):
        return csv_response(
            [
                "收款记录",
                "时间 UTC",
                "方式",
                "绑定用户名",
                "确认收款微元",
                "渠道",
                "收款凭证",
                "备注",
                "操作人",
                "签发码数",
                "已兑换码数",
            ],
            (
                [
                    r["id"],
                    r["created_at"],
                    r["kind"],
                    r["email"],
                    r["amount_micros"],
                    r["channel"],
                    r["payment_ref"],
                    r["note"],
                    r["operator"],
                    r["code_count"],
                    r["redeemed_count"],
                ]
                for r in funding.receipts(store)
            ),
            "haike-funding.csv",
        )

    @routes.post("/admin/v1/users")
    def create_user(body: registration, user=Depends(admin_user)):
        return commerce.create_customer(
            store, user["id"], body.email, body.name, body.password
        )

    @routes.post("/admin/v1/users/{user_id}/credits")
    def credit(
        user_id: str, body: Credit, user=Depends(admin_user), idem=Depends(idem_key)
    ):
        return commerce.credit(
            store,
            user["id"],
            user_id,
            pricing.amount_string(body.amount_micros, allow_zero=False),
            body.note,
            idem,
            body.channel,
            body.payment_ref,
        )

    @routes.get("/admin/v1/redeem-codes")
    def codes(user=Depends(admin_user)):
        with store.read() as db:
            return {
                "items": [
                    commerce.code_public(r)
                    for r in db.execute(
                        "SELECT c.*,r.new_code_id replacement_id FROM redeem_codes c LEFT JOIN redeem_replacements r ON r.old_code_id=c.id ORDER BY c.created_at DESC LIMIT 500"
                    )
                ]
            }

    @routes.post("/admin/v1/redeem-codes")
    def issue(
        body: Codes,
        user=Depends(admin_user),
        idempotency_key: str | None = Header(default=None),
    ):
        return commerce.issue_codes(
            store,
            user["id"],
            pricing.amount_string(body.amount_micros, allow_zero=False),
            body.count,
            body.expires_days,
            body.batch,
            body.bound_user_id,
            body.channel,
            body.payment_ref,
            body.note,
            idem_key(idempotency_key) if idempotency_key else None,
        )

    @routes.post("/admin/v1/redeem-codes/{code_id}/revoke")
    def revoke(code_id: str, user=Depends(admin_user)):
        with store.write() as db:
            row = db.execute(
                "SELECT * FROM redeem_codes WHERE id=?", (code_id,)
            ).fetchone()
            if not row:
                raise Problem(404, "not_found", "兑换码不存在")
            if row["redeemed_by"]:
                raise Problem(409, "code_used", "已领取兑换码不能作废或回扣")
            db.execute(
                "UPDATE redeem_codes SET revoked_at=coalesce(revoked_at,?) WHERE id=?",
                (now(), code_id),
            )
            audit(db, user["id"], "revoke_redeem_code", code_id)
        return {"ok": True}

    @routes.post("/admin/v1/redeem-codes/{code_id}/reissue")
    def reissue(code_id: str, user=Depends(admin_user)):
        return commerce.reissue_code(store, user["id"], code_id)

    @routes.post("/portal/v1/redeem-codes/preview")
    def preview_code(body: Redeem, user=Depends(portal_user)):
        return commerce.redeem(store, user["id"], body.code, preview=True)

    @routes.post("/portal/v1/redeem-codes/redeem")
    def redeem(body: Redeem, user=Depends(portal_user)):
        return commerce.redeem(store, user["id"], body.code)

    @routes.get("/admin/v1/providers")
    def configs(user=Depends(admin_user)):
        return {"items": vault.public()}

    @routes.post("/admin/v1/providers")
    def add_channel(body: Channel, user=Depends(admin_user)):
        with store.write() as db:
            vault.add_channel(body.id, body.name, body.base_url, body.api_key)
            audit(db, user["id"], "add_provider", body.id)
        return {"ok": True}

    @routes.post("/admin/v1/providers/{provider:path}")
    def config(provider: str, body: Config, user=Depends(admin_user)):
        with store.write() as db:
            vault.update(provider, body.config)
            audit(db, user["id"], "update_provider", provider)
        return {"ok": True}

    @routes.get("/admin/v1/gateway-models")
    def models(user=Depends(admin_user)):
        return {"items": providers.catalogue(store, vault, admin=True)}

    @routes.post("/admin/v1/gateway-models")
    def save_model(body: ModelRoute, user=Depends(admin_user)):
        with store.write() as db:
            vault.save_model(
                body.model, body.name, body.provider, body.target_model, body.enabled
            )
            audit(db, user["id"], "save_model_route", body.model)
        return {"ok": True}

    @routes.post("/admin/v1/gateway-prices/preview")
    def preview(body: Preview, user=Depends(admin_user)):
        proposal = {**body.rule, "confirmed": True}
        proposal["source"] = proposal.get("source") or "仅用于定价预览"
        proposal["cost_basis"] = proposal.get("cost_basis") or "试算成本"
        info = vault.models().get(body.model)
        rule = providers.normalize(body.model, proposal, info)
        cost, sale = providers.calculate(body.model, rule, body.usage, info)
        return {
            "cost_micros": str(cost),
            "sale_micros": str(sale),
            "profit_micros": str(sale - cost),
            "gross_margin": str(Decimal(sale - cost) / sale) if sale else "0",
        }

    @routes.post("/admin/v1/gateway-prices")
    def publish(body: Tariff, user=Depends(admin_user)):
        return providers.publish(store, user["id"], body.model, body.rule, vault)

    @routes.get("/admin/v1/gateway-jobs")
    def jobs(user=Depends(admin_user)):
        return {"items": gateway.list_jobs(store, user, admin=True)}

    @routes.get("/admin/v1/gateway-jobs/export")
    def export_jobs(user=Depends(admin_user)):
        items = gateway.list_jobs(store, user, admin=True)
        return csv_response(
            [
                "任务",
                "时间 UTC",
                "客户",
                "用户名",
                "模型",
                "Key",
                "项目",
                "状态",
                "实际用量 JSON",
                "价格版本",
                "系数",
                "逐项计费及采购单价 JSON",
                "实扣微元",
                "估算成本微元",
                "估算毛利微元",
                "采购成本说明",
                "回执编号",
            ],
            (
                [
                    j["id"],
                    j["created_at"],
                    j["account_name"],
                    j["account_email"],
                    j["model"],
                    j["key_name"],
                    j["project_ref"],
                    j["status"],
                    json.dumps(j["usage"], ensure_ascii=False),
                    j["price"]["version"],
                    j["billing"]["multiplier"],
                    json.dumps(j["billing"]["lines"], ensure_ascii=False),
                    j["charged_micros"],
                    j["estimated_cost_micros"],
                    j["estimated_profit_micros"],
                    j["cost_basis"],
                    j["upstream_id"],
                ]
                for j in items
            ),
            "haike-operations.csv",
        )

    @routes.get("/admin/v1/gateway-jobs/{job_id}")
    def job_detail(job_id: str, user=Depends(admin_user)):
        return gateway.get_job(store, user, job_id, admin=True)

    @routes.post("/admin/v1/gateway-jobs/{job_id}/reconcile")
    def reconcile(job_id: str, body: Resolve, user=Depends(admin_user)):
        return gateway.reconcile(
            store, user["id"], job_id, body.outcome, body.usage, body.evidence
        )

    @routes.post("/v2/files")
    async def file(request: Request, kind: str, user=Depends(api_user)):
        return gateway.upload(store, user["id"], kind, await request.body())

    return routes
