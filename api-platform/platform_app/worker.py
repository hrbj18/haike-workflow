"""Persistent local simulator; intentionally no network or real media generation."""

import asyncio
import json

from .domain import finalize
from .store import now, uid


def recover_interrupted(store):
    with store.write() as db:
        db.execute(
            "UPDATE jobs SET status='submission_unknown',funds_status='reconciliation_pending',"
            "error='服务重启时提交结果未确认，需核对；不会自动再次提交',updated_at=? "
            "WHERE status IN ('submitting','running','cancel_pending') AND funds_status='reserved'",
            (now(),),
        )
        db.execute(
            "DELETE FROM outbox WHERE job_id IN (SELECT id FROM jobs WHERE status<>'queued')"
        )


def claim(store):
    with store.write() as db:
        job = db.execute(
            "SELECT j.* FROM jobs j JOIN outbox o ON o.job_id=j.id WHERE j.status='queued' ORDER BY j.created_at LIMIT 1"
        ).fetchone()
        if not job:
            return None
        # Persist an intent/submission identifier BEFORE any provider-side operation.
        db.execute(
            "UPDATE jobs SET status='submitting',submission_id=?,updated_at=? WHERE id=?",
            (uid("sim"), now(), job["id"]),
        )
        return job["id"]


def complete_simulation(store, job_id):
    with store.write() as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job["funds_status"] not in {"reserved", "reconciliation_pending"}:
            return
        quote = db.execute(
            "SELECT * FROM quotes WHERE id=?", (job["quote_id"],)
        ).fetchone()
        outcome = json.loads(quote["input_json"])["demo_outcome"]
        if outcome == "submission_unknown":
            db.execute(
                "UPDATE jobs SET status='submission_unknown',funds_status='reconciliation_pending',"
                "error='模拟提交结果未知；冻结额度保留，管理员核对后结算或释放',updated_at=? WHERE id=?",
                (now(), job_id),
            )
            db.execute("DELETE FROM outbox WHERE job_id=?", (job_id,))
        else:
            finalize(
                db, job, "cancelled" if job["status"] == "cancel_pending" else outcome
            )


async def run_worker(store):
    while True:
        job_id = await asyncio.to_thread(claim, store)
        if job_id:
            await asyncio.sleep(1.5)
            await asyncio.to_thread(complete_simulation, store, job_id)
        else:
            await asyncio.sleep(0.5)
