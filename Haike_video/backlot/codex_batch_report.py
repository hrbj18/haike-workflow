"""Render a local batch receipt document; never infer review or actual charges."""
from datetime import datetime, timezone
import html
import os
from pathlib import Path
import tempfile

from backlot.codex_batch import BatchError, fingerprint


def _text(value):
    return html.escape(str(value or ""), quote=False).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _money(value):
    return f"{value / 1_000_000:.6f} 元" if type(value) is int else "未知，等待结算回执"


def write_report(batch, result, *, slot=None):
    root = batch.root / "Haike_video"
    folder = root / ".backlot/codex-batches" / ("batch-" + fingerprint(batch.spec["batch_id"])[:24])
    name = "汇报文档.md" if slot is None else "汇报文档-" + fingerprint(slot)[:12] + ".md"
    target = folder / name
    for path in (target, *target.parents):
        if path == root:
            break
        if path.is_symlink() or (path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
            raise BatchError("汇报文档路径不能穿过链接或目录联接")
    folder.mkdir(parents=True, exist_ok=True)
    budget = result["budget"]
    lines = ["# 视频批次汇报", "", f"批次：{_text(result['batch_id'])}",
             f"规格 SHA256：`{result['spec_sha256']}`", f"更新时间：{datetime.now(timezone.utc).isoformat()}", "",
             f"批次预算上限：{_money(budget['limit_micros'])}；已分配上限：{_money(budget['allocated_micros'])}。",
             f"实际结算：{_money(budget['actual_micros'])}；保留额度：{_money(budget['reserved_micros'])}。",
             "实际费用未知时不会记为零；失败和未知结果不释放保守额度。", "",
             "| 槽位 | 标题 | 制作/发布阶段 | 队列 | 作品 |", "| --- | --- | --- | --- | --- |"]
    for row in result["items"]:
        item = next(i for i in batch.spec["items"] if i["slot_id"] == row["slot_id"])
        queue = row.get("queue") or {}
        lines.append("| " + " | ".join(_text(v) for v in (row["slot_id"], item["title"], row["stage"],
                     f"{queue.get('job_id', '未提交')} / {queue.get('status', '未提交')}", row.get("work_id") or "尚未生成")) + " |")
    if "prior_exposure_micros" in budget:
        lines.extend(["", f"历史预留敞口：{_money(budget['prior_exposure_micros'])}；含历史的已分配上限：{_money(budget['combined_allocated_micros'])}。",
                      "原内容规格保持不变，预算上调依据独立授权收据；历史敞口未释放，以上不是实际结算。"])
    for row in result["items"]:
        item = next(i for i in batch.spec["items"] if i["slot_id"] == row["slot_id"])
        lines.extend(["", "## " + _text(item["title"]), "", _text(row.get("summary") or row["stage"]),
                      "", "音轨：" + ("使用上传的完整音轨，原速播放。" if "audio_path" in item else "使用冻结规格中的配音模型、音色与语速。"),
                      f"原任务：`{row['task_id']}`；项目：`{row['draft_id']}`。"])
        if row.get("audio_sha256"):
            lines.extend(["", "原始完整音轨 SHA256：`" + _text(row["audio_sha256"]) + "`。"])
        receipts = row.get("publication_receipts") or []
        if not item["publishing"]["targets"]:
            lines.extend(["", "发布：本条仅制作，未指定发布账号。"])
        lines.append("")
        for account in item["publishing"]["targets"]:
            receipt = next((r for r in receipts if r["platform"] == account["platform"] and r["account_id"] == account["account_id"]), {})
            lines.append(f"- {_text(account['platform'])} / 账号 {account['account_id']}：{_text(receipt.get('label') or '尚未取得发布回执')}；原发布任务 {_text(receipt.get('task_id') or '未提交')}。" +
                         (" 排期：" + _text(account["scheduled_at"]) if account.get("scheduled_at") else ""))
        lines.extend(["", "来源："])
        for source in item["sources"]:
            if source.get("kind") == "user_provided":
                lines.append("- 用户提供：" + _text(source["label"]) + "；原始文件 SHA 已冻结。")
            else:
                lines.append("- " + _text(source.get("publisher") or "来源") + "：" + _text(source["url"]))
    if result.get("errors"):
        lines.extend(["", "## 待处理事项", ""])
        for error in result["errors"]:
            lines.append("- " + _text(error["slot_id"]) + "：" + _text(error["message"]))
    lines.extend(["", "恢复时使用原规格和任务编号执行 status / resume / advance；不要换批次编号重复制作或发布。", ""])
    fd, temporary = tempfile.mkstemp(prefix=".report-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(lines))
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target
