import pytest

from app.core.config import settings
from app.core.security import create_session_token


@pytest.mark.parametrize(
    "path",
    [
        "/plots/{id}/calculation-runs",
        "/plots/{id}/calculation-runs/{id}/approve",
        "/plots/{id}/publish",
    ],
)
def test_calculation_writes_require_cookie_csrf(client, manager, db_mock, path):
    client.cookies.set(settings.session_cookie_name, create_session_token(manager.id, "manager"))
    response = client.post("/api/v1" + path.replace("{id}", manager.id), json={})
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    db_mock.add.assert_not_called()
