from pathlib import Path

from fastapi.testclient import TestClient

from backlot import server


ROOT = Path(__file__).resolve().parents[2]


def test_retired_automation_page_redirects_to_the_current_release_calendar():
    client = TestClient(server.create_app())
    response = client.get("/automation", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/calendar"
    calendar = client.get(response.headers["location"])
    assert calendar.status_code == 200
    assert '<div id="root"></div>' in calendar.text
    assert "/ui/avatar-generator/assets/" in calendar.text


def test_retired_automation_assets_and_navigation_cannot_reappear():
    client = TestClient(server.create_app())
    for name in ("automation.html", "automation.css", "automation.js"):
        assert not (ROOT / "backlot/ui" / name).exists()
        assert client.get("/ui/" + name).status_code == 404

    navigation = client.get("/ui/navigation.js")
    assert navigation.status_code == 200
    assert '["/legacy/projects", "项目工作台"]' in navigation.text
    assert '["/material-library", "素材库"]' in navigation.text
    assert '"/automation"' not in navigation.text
