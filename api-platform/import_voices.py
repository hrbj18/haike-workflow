"""Operator-only migration of existing compatible system voices and cached auditions."""

import argparse
import json
from pathlib import Path

from platform_app import providers, voices
from platform_app.store import Problem, Store


def import_manifest(store, vault, manifest):
    manifest = Path(manifest).resolve()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"voices"} or not isinstance(data["voices"], list):
        raise Problem(422, "voice_manifest_invalid", "清单需包含 voices 列表")
    result = []
    for item in data["voices"]:
        if not isinstance(item, dict) or set(item) - {"name", "provider_voice_id", "tags", "sample_file"}:
            raise Problem(422, "voice_manifest_invalid", "音色清单含未知字段")
        sample = None
        if item.get("sample_file"):
            relative = Path(item["sample_file"])
            path = (manifest.parent / relative).resolve()
            if relative.is_absolute() or not path.is_relative_to(manifest.parent) or not path.is_file():
                raise Problem(422, "voice_sample_invalid", "试听文件必须位于私有清单目录内")
            if path.stat().st_size > 5 * 1024 * 1024:
                raise Problem(422, "voice_sample_invalid", "试听文件不能超过5MB")
            sample = path.read_bytes()
        # A free query validates the original identity and exact target model; no create/TTS call.
        tone = voices.import_system(store, vault, item.get("name", ""), item.get("provider_voice_id", ""), item.get("tags", []))
        if sample:
            with store.read() as db:
                cached = db.execute("SELECT sample_file,sample_job_id FROM gateway_voices WHERE id=?", (tone["id"],)).fetchone()
            if not cached["sample_file"] and not cached["sample_job_id"]:
                voices.import_sample(store, tone["id"], sample)
        result.append(tone)
    return result


def main():
    parser = argparse.ArgumentParser(description="导入已有系统音色，只查询验证，不克隆、不生成收费试听")
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).parent / "data")
    args = parser.parse_args()
    store = Store(args.data_dir / "platform.sqlite3"); store.initialize()
    try:
        result = import_manifest(store, providers.Vault(args.data_dir), args.file)
    except (Problem, OSError, ValueError, TypeError):
        raise SystemExit("导入未完成，请检查私有清单、试听文件和音色所属百炼配置；不会自动重建音色") from None
    for tone in result:
        print(tone["name"], "已登记", tone["id"])


if __name__ == "__main__":
    main()
