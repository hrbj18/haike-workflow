"""Persist a rotated session in one process and restore it in a fresh process."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def _worker(phase, directory, platform):
    import asyncio
    import json
    from types import SimpleNamespace
    import app.db as db
    import app.main as main
    from app.browser.identity import Identity
    from app.browser.manager import BrowserManager
    from app.models import DouyinAccount
    from tests.test_browser_session_snapshots import _Context

    root = Path(directory).resolve()
    assert Path(main.cfg.db_path).resolve().is_relative_to(root)
    assert Path(main.cfg.engine.profiles_dir).resolve().is_relative_to(root)
    assert Path(main.cfg.engine.media_dir).resolve().is_relative_to(root)
    db.init_db(str(root / "sessions.db"))
    profile = str(root / "profile")
    domain = ".kuaishou.com" if platform == "kuaishou" else ".weixin.qq.com"
    cookie = {"name": "fixture_session", "value": "freshly-rotated-fixture",
              "domain": domain, "path": "/", "expires": -1,
              "httpOnly": True, "secure": True}

    async def noop():
        pass

    async def run():
        manager = BrowserManager("fixture-UA", str(root),
                                session_state_callback=main._persist_account_session_state)
        if phase == "save":
            with db.get_session() as session:
                account = DouyinAccount(platform=platform, profile_dir=profile,
                    storage_state=json.dumps({"cookies": [{**cookie, "value": "old-fixture"}]}),
                    ua="fixture-UA", identity_mode="legacy")
                session.add(account)
                session.commit()
                session.refresh(account)
                identity = Identity.from_account(account, str(root), "fixture-UA")
            context = _Context()
            context.state = {"cookies": [cookie], "origins": []}
            assert await manager.snapshot_session(identity, context)
            await manager.stop()
            assert manager._session_snapshots.latest_state(identity) is None
        else:
            with db.get_session() as session:
                from sqlmodel import select
                account = session.exec(select(DouyinAccount)).one()
                assert json.loads(account.storage_state)["cookies"] == [cookie]
                assert account.creator_storage_state == account.storage_state
                identity = Identity.from_account(account, str(root), "fixture-UA")
            assert manager._session_snapshots.latest_state(identity) is None
            context = _Context()
            context.state = {"cookies": [], "origins": []}

            class Chromium:
                async def launch_persistent_context(self, **_kwargs):
                    return context

            manager._pw = SimpleNamespace(chromium=Chromium(), stop=noop)
            await manager.context_for(identity)
            assert await context.cookies() == [cookie]
            await manager.stop()
        db._engine.dispose()

    asyncio.run(run())


class SessionProcessRestartTests(unittest.TestCase):
    def test_kuaishou_and_channels_restore_from_disk_after_complete_process_exit(self):
        for platform in ("kuaishou", "shipinhao"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                config = root / "config.yaml"
                config.write_text(json.dumps({
                    "storage": {"db_path": str(root / "config.db")},
                    "engine": {"profiles_dir": str(root / "profiles"),
                               "media_dir": str(root / "media")},
                }), encoding="utf-8")
                env = {**os.environ, "CREATORHUB_CONFIG_PATH": str(config)}
                for phase in ("save", "restore"):
                    result = subprocess.run(
                        [sys.executable, "-X", "utf8", "-m", "tests.test_session_process_restart",
                         "--worker", phase, str(root), platform],
                        cwd=Path(__file__).resolve().parents[1], env=env,
                        capture_output=True, text=True, encoding="utf-8", timeout=30)
                    self.assertEqual(result.returncode, 0,
                                     f"{platform}/{phase}: {result.stderr}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        _worker(*sys.argv[2:])
    else:
        unittest.main()
