"""Generate a public discovery feed for a verified full portable release."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import zipfile


def build(archive, output, package_url, notes=""):
    archive, output = Path(archive).resolve(strict=True), Path(output).resolve()
    url = urlsplit(package_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError("完整包地址必须使用无凭据的 HTTPS 地址")
    size = archive.stat().st_size
    if not 0 < size < 2 * 1024 ** 3:
        raise ValueError("GitHub 单附件必须小于 2 GiB，请重新构建发行包")
    with zipfile.ZipFile(archive) as package:
        roots = [name for name in package.namelist() if name.endswith("/RELEASE.json") and name.count("/") == 1]
        if len(roots) != 1:
            raise ValueError("完整包需要唯一的根发行身份")
        release = json.loads(package.read(roots[0]))
    for key in ("edition", "version", "channel", "platform", "runtime_id", "data_schema", "source_commit"):
        if key not in release:
            raise ValueError("完整包缺少发行身份：" + key)
    if (release["edition"] != "haike-workflow-2" or release["channel"] != "stable"
            or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", release["version"])
            or not re.fullmatch(r"[0-9a-f]{40}", release["source_commit"])):
        raise ValueError("完整包的发行身份无效")
    with archive.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    feed = {key: release[key] for key in ("edition", "version", "channel", "platform", "runtime_id", "data_schema")}
    feed.update(schema=1, base_version="0.0.0", notes=notes, package={"kind": "full", "url": package_url, "size": size, "sha256": checksum})
    hash_path = archive.with_name(archive.name + ".sha256")
    if output.exists() or hash_path.exists():
        raise ValueError("发行清单或校验文件已存在，请使用新的输出位置")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    hash_path.write_text(checksum + "  " + archive.name + "\n", encoding="ascii")
    return {"feed": str(output), "sha256": checksum, "archive": str(archive), "version": release["version"], "size": size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package-url", required=True)
    parser.add_argument("--notes-file", type=Path)
    args = parser.parse_args()
    notes = args.notes_file.read_text(encoding="utf-8-sig") if args.notes_file else ""
    print(json.dumps(build(args.archive, args.output, args.package_url, notes), ensure_ascii=False))


if __name__ == "__main__":
    main()
