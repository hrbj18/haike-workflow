"""Run only the works UI; never start producer recovery or daily automation."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from backlot.work_api import router, UI
from lib.paths import PROJECTS_DIR


def create_app(projects_root=PROJECTS_DIR, main_url="http://127.0.0.1:14754"):
    app = FastAPI(docs_url=None, redoc_url=None)
    app.state.works_projects_root = Path(projects_root)
    app.include_router(router)
    app.mount("/ui", StaticFiles(directory=UI), name="ui")

    @app.get("/")
    def root():
        return RedirectResponse(main_url + "/")

    @app.get("/p/{project_id}")
    def project(project_id: str):
        return RedirectResponse(main_url + "/p/" + project_id)

    @app.get("/{page}")
    def original(page: str):
        return RedirectResponse(main_url + "/" + page)

    return app


if __name__ == "__main__":
    import uvicorn
    parser = argparse.ArgumentParser(description="只启动作品管理，不恢复生产任务")
    parser.add_argument("--port", type=int, default=14756)
    parser.add_argument("--projects", type=Path, default=PROJECTS_DIR)
    parser.add_argument("--main-url", default="http://127.0.0.1:14754")
    args = parser.parse_args()
    uvicorn.run(create_app(args.projects, args.main_url), host="127.0.0.1", port=args.port)
