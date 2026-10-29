"""Build this feature snapshot from an explicit source allowlist, without data."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.1.0"
FILES = [
    "START_HERE.md",
    "INTEGRATE.md",
    "HTTP_API.md",
    "NOTICE.md",
    "LICENSE",
    "VERIFICATION.json",
    ".env.example",
    ".gitignore",
    "pyproject.toml",
    "image_refinement/__init__.py",
    "image_refinement/__main__.py",
    "image_refinement/provider.py",
    "image_refinement/presets.py",
    "image_refinement/service.py",
    "image_refinement/api.py",
    "image_refinement/client.py",
    "examples/python_embed.py",
    "examples/fastapi_router.py",
    "adapters/node-client.mjs",
    "web/refinement-widget.js",
    "web/example.html",
    "tests/test_refinement.py",
    "tests/node-client.test.mjs",
    "tests/widget.test.mjs",
    "tools/package.py",
]


def main():
    parser = argparse.ArgumentParser(
        description="Package only the reusable refinement feature"
    )
    parser.add_argument("--out-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    payloads = {}
    for name in FILES:
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            raise SystemExit("Missing or linked source: " + name)
        data = path.read_bytes()
        text = data.decode("utf-8")
        if (
            re.search(r"(?:sk-|hk_)[A-Za-z0-9_-]{18,}", text)
            or "C:\\Users\\Administrator" in text
            or "D:\\刘宇钊" in text
        ):
            raise SystemExit("Possible credential or private machine path: " + name)
        payloads[name] = data
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL, text=True
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--", str(ROOT)], cwd=ROOT, text=True
            ).strip()
        )
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    manifest = {
        "artifact": "responses-image-refinement-kit",
        "version": VERSION,
        "source_snapshot_git_commit": commit,
        "source_has_uncommitted_changes": dirty,
        "scope": "Explicit feature-file snapshot, not a full repository HEAD release.",
        "files": {
            name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in payloads.items()
        },
    }
    payloads["BUILD-MANIFEST.json"] = json.dumps(
        manifest, ensure_ascii=False, indent=2
    ).encode()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    target = args.out_dir / f"responses-image-refinement-kit-{VERSION}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payloads.items()):
            info = zipfile.ZipInfo(
                f"responses-image-refinement-kit-{VERSION}/{name}",
                date_time=(2026, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(
        digest + "  " + target.name + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "archive": str(target.resolve()),
                "bytes": target.stat().st_size,
                "sha256": digest,
                "files": len(payloads),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
