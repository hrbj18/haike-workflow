"""Project-owned adapter to the workspace's private download credential store."""
from __future__ import annotations

import importlib.util
import copy
import os
import sys
from functools import lru_cache
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[4]


@lru_cache(maxsize=1)
def credential_module():
    path = WORKSPACE / "creatorhub/app/download_credentials.py"
    spec = importlib.util.spec_from_file_location("haike_download_credentials", path)
    if spec is None or spec.loader is None or not path.is_file():
        raise RuntimeError("下载账号凭据模块尚未安装")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def credential_store():
    root = os.environ.get("HAIKE_DOWNLOAD_CREDENTIALS_DIR")
    return credential_module().DownloadCredentialStore(
        Path(root).expanduser().resolve() if root else WORKSPACE / "creatorhub/data/download-credentials")


def selected_account_id(explicit=None):
    if explicit is None:
        return credential_store().selected_account("douyin")
    if isinstance(explicit, bool) or not str(explicit).isdigit() or int(explicit) <= 0:
        raise ValueError("下载账号编号无效")
    return int(explicit)


def account_cookies(account_id):
    return account_record(account_id)["cookies"]


def account_record(account_id):
    record = credential_store().read_record("douyin", selected_account_id(account_id))
    if str(record.get("proxy") or "").strip():
        raise credential_module().DownloadCredentialError(
            "该下载账号配置了代理，当前MediaCrawler适配尚不支持；请使用已支持的账号下载入口")
    return record


def download_collection_config(config):
    """Give each selected account a separate collector profile and CDP port."""
    account_id = selected_account_id(config["media_crawler"].get("download_account_id"))
    if account_id is None:
        return config
    account_record(account_id)  # Transport must be supported before Chrome opens.
    port = 10000 + account_id
    if port > 65535:
        raise ValueError("下载账号编号超出专用浏览器端口范围，请联系管理员")
    result = copy.deepcopy(config)
    crawler = result["media_crawler"]
    base = Path(crawler.get("download_accounts_root") or
                (Path(crawler["user_data_dir"]).parent / "download-accounts"))
    account_root = base / str(account_id)
    runs = Path(crawler.get("download_runs_root") or crawler["runs_output"])
    crawler.update(download_account_id=account_id, download_accounts_root=str(base),
                   download_runs_root=str(runs),
                   user_data_dir=str(account_root / "browser-profile"),
                   browser_lease_root=str(account_root / "leases"),
                   browser_state_path=str(account_root / "browser-status.json"),
                   runs_output=str(runs / f"download-account-{account_id}"), cdp_port=port)
    return result


def crawler_account_args(config):
    account_id = selected_account_id(config["media_crawler"].get("download_account_id"))
    return ["--download-account-id", str(account_id)] if account_id is not None else []


async def inject_download_cookies(context, cookies):
    """Actually seed the isolated collector context; never open publishing profiles."""
    await context.add_cookies(cookies)


async def inherit_download_user_agent(context, page, user_agent):
    if not user_agent:
        return
    session = await context.new_cdp_session(page)
    try:
        await session.send("Network.setUserAgentOverride", {"userAgent": user_agent})
    finally:
        await session.detach()


def configure_cookie_login(config_module, remainder, cookies):
    """Use upstream's supported cookie path without putting secrets in argv."""
    config_module.LOGIN_TYPE = "cookie"
    config_module.COOKIES = "; ".join(f"{item['name']}={item['value']}" for item in cookies)
    args = list(remainder)
    for index, value in enumerate(args[:-1]):
        if value in {"--lt", "--login_type"}:
            args[index + 1] = "cookie"
            break
    else:
        args += ["--lt", "cookie"]
    return args
