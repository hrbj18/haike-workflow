"""Browser regressions from the Backlot UI bug bash."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from lib.checkpoint import CANONICAL_STAGE_ARTIFACTS, init_project, write_checkpoint
from lib.native_probe import _stop_owned_probe
from lib.pipeline_loader import get_stage_order, load_pipeline
from scripts import backlot_screenshot_stage
from tests.backlot.isolated_browser_server import configure_private, local_browser_url
from tests.contracts.test_phase0_contracts import sample_artifact


pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402


def _local_page(browser, server_url, **kwargs):
    page = browser.new_page(**kwargs)
    page.route("**/*", lambda route: (
        route.continue_() if local_browser_url(route.request.url, server_url) else route.abort()
    ))
    page.route_web_socket("**/*", lambda route: (
        route.connect_to_server() if local_browser_url(route.url, server_url) else route.close()
    ))
    return page


APPROVAL_CASES = [
    ("gate-research", "framework-smoke", "research", "research_brief", "Test Topic"),
    ("gate-idea", "hybrid", "idea", "brief", "Did you know?"),
    ("gate-proposal", "cinematic", "proposal", "proposal_packet", "The Surprising Truth About X"),
    ("gate-script", "cinematic", "script", "script", "Hello world"),
    ("gate-scene-plan", "cinematic", "scene_plan", "scene_plan", "Host on camera"),
    ("gate-assets", "cinematic", "assets", "asset_manifest", "asset-1"),
    ("gate-edit", "documentary-montage", "edit", "edit_decisions", "cut-1"),
    ("gate-compose", "cinematic", "compose", "render_report", "renders/output.mp4"),
    ("gate-publish", "cinematic", "publish", "publish_log", "youtube"),
]


def _complete_predecessors(root, project_id: str, pipeline_type: str, stage: str) -> None:
    order = get_stage_order(load_pipeline(pipeline_type))
    for predecessor in order[: order.index(stage)]:
        artifact_name = CANONICAL_STAGE_ARTIFACTS.get(predecessor)
        if artifact_name:
            artifact = sample_artifact(artifact_name)
            if artifact_name == "edit_decisions":
                artifact["render_runtime"] = "ffmpeg"
            artifacts = {artifact_name: artifact}
        else:
            artifacts = {}
        write_checkpoint(
            root,
            project_id,
            predecessor,
            "completed",
            artifacts,
            pipeline_type=pipeline_type,
            human_approved=True,
        )


def _build_approval_projects() -> None:
    root = backlot_screenshot_stage.STAGE_DIR
    for project_id, pipeline_type, stage, artifact_name, _visible_text in APPROVAL_CASES:
        artifact = sample_artifact(artifact_name)
        if artifact_name == "edit_decisions":
            artifact["render_runtime"] = "ffmpeg"
        review_summary = (
            {
                "critical": 0,
                "suggestions": 1,
                "nitpicks": 0,
                "review_focus_met": "9/9",
                "schema_validation": "proposal_packet PASS",
            }
            if stage == "proposal"
            else "Artifact is ready for human review."
        )
        init_project(
            project_id,
            title=f"Approval fixture: {stage}",
            pipeline_type=pipeline_type,
            pipeline_dir=root,
        )
        _complete_predecessors(root, project_id, pipeline_type, stage)
        write_checkpoint(
            root,
            project_id,
            stage,
            "awaiting_human",
            {artifact_name: artifact},
            pipeline_type=pipeline_type,
            review={
                "round": 1,
                "decision": "pass",
                "critical": 0,
                "suggestions": 1,
                "nitpicks": 0,
                "summary": review_summary,
            },
        )

    # A manifest-declared custom stage/artifact proves the fallback is driven
    # by the stage contract rather than a hardcoded canonical-stage list.
    init_project(
        "gate-character-design",
        title="Approval fixture: character design",
        pipeline_type="character-animation",
        pipeline_dir=root,
    )
    _complete_predecessors(
        root,
        "gate-character-design",
        "character-animation",
        "character_design",
    )
    write_checkpoint(
        root,
        "gate-character-design",
        "character_design",
        "awaiting_human",
        {"character_design": {
            "version": "1.0",
            "characters": [{
                "id": "ada",
                "display_name": "Ada",
                "role": "explorer",
                "body_type": "round",
                "style": "flat graphic",
                "silhouette_notes": "Round explorer with a bright orange field jacket",
                "required_emotions": ["curious"],
                "required_actions": ["wave"],
            }],
        }},
        pipeline_type="character-animation",
    )

    avatar_project = init_project(
        "avatar-cloud-ready",
        title="双角色数字人页面回归",
        pipeline_type="avatar-spokesperson",
        pipeline_dir=root,
    )
    (avatar_project / "artifacts" / "script.json").write_text(json.dumps({
        "sections": [
            {"turn_id": "T001", "speaker_id": "yaya", "speaker_name": "雅雅", "text": "欢迎收看今天的科技快报。"},
            {"turn_id": "T002", "speaker_id": "mengmeng", "speaker_name": "檬檬", "text": "下面进入第二条消息。"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    from backlot.avatar_import import initialize_avatar_package
    from backlot.avatar_cloud import _refresh_readiness
    package = initialize_avatar_package(avatar_project, {"generation_mode": "dashscope_wan_s2v"})
    for binding in package["speaker_bindings"]:
        binding["presenter_shot"] = {
            "path": f"assets/incoming/avatar/presenter/{binding['speaker_id']}/presenter.png",
            "original_filename": f"{binding['name']}录音间.png", "sha256": ("a" if binding["speaker_id"] == "yaya" else "b") * 64,
            "size_bytes": 100, "uploaded_at": "2026-08-12T00:00:00Z",
            "media": {"width": 941, "height": 1672, "format": "PNG"},
        }
    for index, turn in enumerate(package["turns"]):
        turn["driving_audio"] = {
            "id": f"AVAC-{index:016d}", "path": f"assets/audio/avatar_driving/{turn['turn_id']}.wav",
            "provider_path": f"assets/audio/avatar_driving/{turn['turn_id']}_provider.wav",
            "original_filename": f"{turn['turn_id']}.wav", "sha256": str(index + 1) * 64,
            "size_bytes": 100, "duration_seconds": 4.5, "codec": "pcm_s16le", "state": "current",
            "source_type": "uploaded", "created_at": "2026-08-12T00:00:00Z",
        }
        turn["status"] = "audio_ready"
    _refresh_readiness(package)
    from backlot.avatar_import import _save_package
    _save_package(avatar_project, package)

    layered_project = init_project(
        "multilayer-workbench",
        title="语义双层画面回归",
        pipeline_type="animated-explainer",
        pipeline_dir=root,
    )
    layered_script = {
        "version": "1.0", "title": "机器鸭重点画面",
        "sections": [{"id": "sec-01", "text": "机器鸭正在学习行走。", "start_seconds": 0, "end_seconds": 4}],
    }
    (layered_project / "artifacts" / "script.json").write_text(
        json.dumps(layered_script, ensure_ascii=False), encoding="utf-8"
    )
    (layered_project / "artifacts" / "scene_plan.json").write_text(json.dumps({
        "version": "1.0",
        "scenes": [{
            "id": "scene-01", "title": "机器鸭演示", "description": "机器鸭正在学习行走",
            "start_seconds": 0, "end_seconds": 4, "script_section_id": "sec-01",
        }],
    }, ensure_ascii=False), encoding="utf-8")
    from PIL import Image
    hero = layered_project / "assets" / "duck.png"
    hero.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (320, 180), (40, 180, 210)).save(hero)
    (layered_project / "artifacts" / "asset_manifest.json").write_text(json.dumps({
        "assets": [{
            "id": "duck", "name": "机器鸭演示素材", "type": "image",
            "path": "assets/duck.png", "scene_id": "scene-01", "source_tool": "provided_asset",
        }],
    }, ensure_ascii=False), encoding="utf-8")
    from backlot.workbench import bootstrap_workbench
    bootstrap_workbench(layered_project)


@pytest.fixture(scope="module")
def isolated_screenshot_stage(tmp_path_factory):
    with pytest.MonkeyPatch.context() as scoped:
        stage = tmp_path_factory.mktemp("ui-bug-bash") / "projects"
        scoped.setattr(backlot_screenshot_stage, "STAGE_DIR", stage)
        configure_private(stage.parent / "private", setter=scoped.setattr)
        yield stage


@pytest.fixture(scope="module")
def staged_backlot_server(isolated_screenshot_stage):
    backlot_screenshot_stage.build_stage()
    _build_approval_projects()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    env = dict(os.environ)
    env["OPENMONTAGE_PROJECTS_DIR"] = str(backlot_screenshot_stage.STAGE_DIR)
    env["PYTHON_DOTENV_DISABLED"] = "1"
    env["HAIKE_DOWNLOAD_CREDENTIALS_DIR"] = str(isolated_screenshot_stage.parent / "private/download-credentials")
    options = (
        {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt" else {"start_new_session": True}
    )
    server = subprocess.Popen(
        [sys.executable, "-m", "tests.backlot.isolated_browser_server", "serve", "--port", str(port)],
        cwd=backlot_screenshot_stage.REPO_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        **options,
    )
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            if server.poll() is not None:
                raise RuntimeError("Backlot server exited before becoming healthy")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1):
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("Backlot server did not become healthy")
        yield f"http://127.0.0.1:{port}"
    finally:
        _stop_owned_probe(server)


def test_project_pages_fit_mobile_and_tablet_widths(staged_backlot_server):
    project_paths = [
        "/p/signal-in-the-static?static=1",
        "/p/the-slow-orchard?static=1",
        "/p/the-last-lighthouse?static=1",
        "/p/paper-boats?static=1",
        "/p/gate-proposal?static=1",
        "/p/gate-character-design?static=1",
        "/p/multilayer-workbench",
    ]
    viewports = [
        {"width": 390, "height": 844},
        {"width": 768, "height": 1024},
    ]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = _local_page(browser, staged_backlot_server)
        try:
            for viewport in viewports:
                page.set_viewport_size(viewport)
                for path in project_paths:
                    static = "static=1" in path
                    page.goto(
                        staged_backlot_server + path,
                        wait_until="networkidle" if static else "domcontentloaded",
                    )
                    if static:
                        page.locator("#app h1").wait_for(state="visible")
                    else:
                        page.get_by_role("button", name="片段工作台", exact=True).wait_for(state="visible")
                    sizes = page.evaluate(
                        """() => ({
                            scrollWidth: document.documentElement.scrollWidth,
                            clientWidth: document.documentElement.clientWidth
                        })"""
                    )
                    assert sizes["scrollWidth"] <= sizes["clientWidth"], (
                        path,
                        viewport,
                        sizes,
                    )
        finally:
            browser.close()


def test_retired_automation_entry_opens_responsive_publication_calendar(staged_backlot_server):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = _local_page(browser, staged_backlot_server)
        try:
            for viewport in ({"width": 390, "height": 844}, {"width": 1440, "height": 1000}):
                page.set_viewport_size(viewport)
                response = page.goto(staged_backlot_server + "/automation", wait_until="domcontentloaded")
                assert response and response.status == 200
                redirected = response.request.redirected_from
                assert redirected and redirected.url == staged_backlot_server + "/automation"
                redirect_response = redirected.response()
                assert redirect_response and redirect_response.status == 307
                assert redirect_response.headers["location"] == "/calendar"
                assert page.url == staged_backlot_server + "/calendar"
                page.get_by_role("heading", name="发布日历", exact=True).wait_for(state="visible")
                page.locator(".calendar-panel").wait_for(state="visible")
                sizes = page.evaluate("""() => ({
                    scrollWidth: document.documentElement.scrollWidth,
                    clientWidth: document.documentElement.clientWidth
                })""")
                assert sizes["scrollWidth"] <= sizes["clientWidth"], (viewport, sizes)
                assert page.get_by_role("button", name="新建排期", exact=True).is_visible()
                assert page.get_by_text("每日科技快报生产中心").count() == 0
        finally:
            browser.close()


def test_static_navigation_invalid_route_and_active_takes(staged_backlot_server):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = _local_page(browser, staged_backlot_server, viewport={"width": 1560, "height": 1000})
        try:
            page.goto(staged_backlot_server + "/?static=1", wait_until="domcontentloaded")
            page.get_by_role("heading", name="图文视频", exact=True).wait_for(state="visible")
            assert page.locator("#root .graphic-editor").is_visible()
            assert page.locator("a.lib-card-link").count() == 0

            page.goto(staged_backlot_server + "/legacy/projects?static=1", wait_until="networkidle")
            page.locator("a.lib-card-link").first.wait_for(state="visible")
            href = page.locator("a.lib-card-link").first.get_attribute("href")
            assert href and "static=1" in href
            page.locator("a.lib-card-link").first.click()
            page.locator("#app h1").wait_for(state="visible")
            assert page.url == staged_backlot_server + href

            response = page.goto(
                staged_backlot_server + "/p/..%2FAGENT_GUIDE.md?static=1",
                wait_until="networkidle",
            )
            assert response and response.status == 200
            assert "PROJECT NOT FOUND" in page.locator("body").inner_text()

            page.goto(staged_backlot_server + "/p/the-last-lighthouse?static=1", wait_until="networkidle")
            page.locator(".takes .tk.active").first.wait_for(state="visible")
            assert page.locator(".takes .tk.active").count() >= 1
        finally:
            browser.close()


@pytest.mark.parametrize(
    ("project_id", "_pipeline_type", "stage", "artifact_name", "visible_text"),
    APPROVAL_CASES,
)
def test_every_canonical_gate_promotes_its_artifact_before_approval(
    staged_backlot_server,
    project_id,
    _pipeline_type,
    stage,
    artifact_name,
    visible_text,
):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = _local_page(browser, staged_backlot_server, viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                staged_backlot_server + f"/p/{project_id}?static=1",
                wait_until="networkidle",
            )
            review = page.locator(f'.approval-review[data-stage="{stage}"]')
            assert review.is_visible()
            assert review.get_by_text("PENDING APPROVAL", exact=True).is_visible()
            assert "[object Object]" not in review.inner_text()
            artifact = review.locator(f'[data-artifact="{artifact_name}"]')
            assert artifact.is_visible()
            assert visible_text in artifact.inner_text()

            review.get_by_role("button", name="OPEN FULL ARTIFACT").click()
            assert page.locator(".drawer").is_visible()
            assert visible_text in page.locator(".drawer").inner_text()
        finally:
            browser.close()


def test_script_gate_keeps_script_visible_and_marks_pending_approval(staged_backlot_server):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = _local_page(browser, staged_backlot_server, viewport={"width": 1280, "height": 900})
        try:
            page.goto(staged_backlot_server + "/p/gate-script?static=1", wait_until="networkidle")
            assert page.locator(".script-card").is_visible()
            assert page.locator(".script-pending").inner_text() == "PENDING APPROVAL"
        finally:
            browser.close()


def test_manifest_declared_custom_gate_uses_generic_review_fallback(staged_backlot_server):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = _local_page(browser, staged_backlot_server, viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                staged_backlot_server + "/p/gate-character-design?static=1",
                wait_until="networkidle",
            )
            review = page.locator('.approval-review[data-stage="character_design"]')
            assert review.is_visible()
            artifact = review.locator('[data-artifact="character_design"]')
            assert artifact.is_visible()
            assert "Ada" in artifact.inner_text()
            assert "Round explorer" in artifact.inner_text()
        finally:
            browser.close()


def test_avatar_role_library_form_fields_are_visible_when_optional_panel_is_open(staged_backlot_server):
    """Regression: a broad CSS selector previously hid all role text inputs."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = _local_page(browser, staged_backlot_server, viewport={"width": 1440, "height": 1000})
        try:
            page.goto(staged_backlot_server + "/p/avatar-cloud-ready", wait_until="domcontentloaded")
            page.get_by_text("数字人素材", exact=True).wait_for(state="visible")
            page.get_by_text("数字人素材", exact=True).click()
            page.get_by_text("可选：通用角色库（跨项目复用）", exact=True).click()
            field = page.get_by_label("角色名称")
            assert field.is_visible()
            assert field.evaluate("element => getComputedStyle(element).pointerEvents") == "auto"
            assert page.get_by_text("出镜图").first.is_visible()
            assert page.get_by_role("button", name="生成每位角色的试片").is_visible()
        finally:
            browser.close()


def test_workbench_light_theme_is_default_and_dark_choice_persists_after_reload(
    staged_backlot_server, tmp_path, record_property,
):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = _local_page(browser, staged_backlot_server, viewport={"width": 1440, "height": 1000})

        def open_controls():
            page.get_by_role("button", name="数字人素材", exact=True).click()
            # The real initial role lookup re-renders this optional panel.
            # Wait for that response-derived state before opening its details.
            page.get_by_text("目前没有通用角色档案；这不会阻止本期生成。", exact=True).wait_for(state="attached")
            page.get_by_text("可选：通用角色库（跨项目复用）", exact=True).click()
            page.get_by_label("角色名称").wait_for(state="visible")

        def palette():
            return page.evaluate("""() => {
                const luminance = color => {
                    const rgb = color.match(/[0-9.]+/g).slice(0, 3).map(Number);
                    const linear = rgb.map(value => {
                        const channel = value / 255;
                        return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
                    });
                    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
                };
                const read = element => {
                    const style = getComputedStyle(element);
                    const background = luminance(style.backgroundColor), foreground = luminance(style.color);
                    return {background: style.backgroundColor, foreground: style.color,
                        background_luminance: background,
                        contrast: (Math.max(background, foreground) + 0.05) / (Math.min(background, foreground) + 0.05),
                        font: style.fontFamily, radius: style.borderRadius};
                };
                return {scheme: getComputedStyle(document.documentElement).colorScheme,
                    body: read(document.body), panel: read(document.querySelector('.avatar-role-library-optional')),
                    input: read(document.querySelector('input[aria-label="角色名称"]'))};
            }""")

        def screenshot(theme):
            target = (tmp_path / f"workbench-{theme}.png").resolve()
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(target), full_page=True, animations="disabled")
            record_property(f"theme_{theme}_screenshot", str(target))
            print(f"THEME_{theme.upper()}_SCREENSHOT={target}")

        try:
            page.goto(staged_backlot_server + "/p/avatar-cloud-ready", wait_until="domcontentloaded")
            page.evaluate("""() => {
                localStorage.setItem('backlot.editorial-theme-v1', 'done');
                localStorage.removeItem('backlot.theme');
            }""")
            page.reload(wait_until="domcontentloaded")

            assert page.locator("html").get_attribute("data-theme") == "light"
            assert page.evaluate("localStorage.getItem('backlot.theme')") == "light"
            toggle = page.locator(".theme-toggle")
            toggle.wait_for(state="visible")
            assert toggle.get_attribute("aria-label") == "切换至深色主题"
            assert toggle.is_visible()
            open_controls()
            light = palette()
            assert light["scheme"] == "light"
            assert light["body"]["background"] == "rgb(247, 248, 250)"
            assert light["panel"]["background"] == light["input"]["background"] == "rgb(255, 255, 255)"
            screenshot("light")
            toggle.click()
            assert page.locator("html").get_attribute("data-theme") == "dark"
            assert page.evaluate("localStorage.getItem('backlot.theme')") == "dark"
            open_controls()
            dark = palette()
            assert dark["scheme"] == "dark"
            for element in ("body", "panel", "input"):
                assert dark[element]["background"] != light[element]["background"]
                assert dark[element]["foreground"] != light[element]["foreground"]
                assert dark[element]["background_luminance"] < .15 < light[element]["background_luminance"]
                assert dark[element]["contrast"] >= 4.5 and light[element]["contrast"] >= 4.5
                assert dark[element]["font"] == light[element]["font"]
                assert dark[element]["radius"] == light[element]["radius"]
            screenshot("dark")

            page.reload(wait_until="domcontentloaded")
            assert page.locator("html").get_attribute("data-theme") == "dark"
            toggle = page.locator(".theme-toggle")
            toggle.wait_for(state="visible")
            assert toggle.get_attribute("aria-label") == "切换至浅色主题"
            open_controls()
            assert palette() == dark
            evidence = (tmp_path / "theme-palette.json").resolve()
            evidence.write_text(json.dumps({"light": light, "dark": dark}, ensure_ascii=False, indent=2), encoding="utf-8")
            record_property("theme_palette", str(evidence))
            print(f"THEME_PALETTE={evidence}")
            toggle.click()
            assert page.locator("html").get_attribute("data-theme") == "light"
            assert page.evaluate("localStorage.getItem('backlot.theme')") == "light"
            open_controls()
            assert palette() == light
        finally:
            browser.close()


def test_workbench_focus_card_can_be_saved_and_survives_reload(staged_backlot_server):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = _local_page(browser, staged_backlot_server, viewport={"width": 1440, "height": 1000})
        try:
            page.goto(staged_backlot_server + "/p/multilayer-workbench", wait_until="domcontentloaded")
            page.get_by_role("button", name="片段工作台", exact=True).wait_for(state="visible")
            page.get_by_role("button", name="片段工作台", exact=True).click()
            layout = page.get_by_label("画面布局")
            layout.select_option("focus_card")
            page.get_by_role("button", name="添加重点素材").click()
            page.get_by_label("重点素材 1").select_option("S-001")
            page.get_by_role("button", name="保存画面组合").click()
            page.wait_for_function("() => document.querySelector('#toast').textContent.includes('画面布局已保存')")

            saved = page.evaluate("""async () => (await fetch('/api/project/multilayer-workbench/workbench')).json()""")
            composition = saved["scenes"][0]["visual_composition"]
            assert composition["layout_recipe"] == "focus_card"
            assert composition["overlays"][0]["asset_id"] == "S-001"

            page.reload(wait_until="domcontentloaded")
            page.get_by_role("button", name="片段工作台", exact=True).wait_for(state="visible")
            page.get_by_role("button", name="片段工作台", exact=True).click()
            assert page.get_by_label("画面布局").input_value() == "focus_card"
            assert page.get_by_label("重点素材 1").input_value() == "S-001"
            assert page.locator(".visual-layer-card").count() == 1
        finally:
            browser.close()
