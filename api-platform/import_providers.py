"""Operator-only import into encrypted ignored storage; never print credential values."""

import argparse
from pathlib import Path

from platform_app.providers import Vault


def main():
    parser = argparse.ArgumentParser(description="导入供应商配置，仅输出配置状态")
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).parent / "data")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    for provider in Vault(args.data_dir).import_file(args.file):
        print(provider["id"], "已配置" if provider["configured"] else "待配置")


if __name__ == "__main__":
    main()
