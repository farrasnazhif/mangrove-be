import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config

from app.main import app
from app.schemas.inventory import PublicPlot
from scripts.check_migrations import check_heads
from scripts.export_openapi import SNAPSHOT
from tests.conftest import authenticate

P0_OPERATIONS = {
    ("get", "/api/v1/me"),
    ("get", "/api/v1/public/plots"),
    ("get", "/api/v1/public/plots/{plot_id}"),
    ("get", "/api/v1/plots"),
    ("post", "/api/v1/plots"),
    ("patch", "/api/v1/plots/{plot_id}"),
    ("get", "/api/v1/plots/{plot_id}/trees"),
    ("post", "/api/v1/plots/{plot_id}/trees"),
    ("post", "/api/v1/plots/{plot_id}/cores"),
    ("post", "/api/v1/cores/{core_id}/layers"),
    ("post", "/api/v1/plots/{plot_id}/calculation-runs"),
    ("post", "/api/v1/plots/{plot_id}/publish"),
    ("post", "/api/v1/reports/exports"),
    ("get", "/api/v1/reports/exports/{export_id}"),
    ("post", "/api/v1/chat/messages"),
    ("get", "/api/v1/public/map/plots"),
    ("get", "/api/v1/map/layers"),
    ("post", "/api/v1/dbh-imports"),
    ("get", "/api/v1/plots/{plot_id}/dbh-recap"),
}


def test_reviewed_openapi_has_no_drift():
    assert app.openapi() == json.loads(SNAPSHOT.read_text(encoding="utf-8")), (
        "Review contract drift and export a new snapshot"
    )


def test_all_prd_p0_operations_have_typed_responses_and_access():
    schema = app.openapi()
    for method, path in P0_OPERATIONS:
        operation = schema["paths"][path][method]
        assert operation["x-access-role"] in {"manager", "visitor-or-manager"}
        assert operation["security"]
        successes = [
            response for code, response in operation["responses"].items() if code.startswith("2")
        ]
        assert successes and all(
            response["content"]["application/json"]["schema"] for response in successes
        )
        if method in {"post", "patch"}:
            assert operation["requestBody"]["required"]
            assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        assert operation["responses"]["422"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }


def test_public_schema_has_no_private_fields():
    properties = PublicPlot.model_json_schema()["properties"]
    assert (
        not {"researcher", "reviewer", "approved_by", "hashed_password", "qa_status"}
        & properties.keys()
    )


def test_unimplemented_route_returns_honest_501_without_writing(client, manager, db_mock):
    headers = authenticate(client, manager)
    response = client.post(
        "/api/v1/plots",
        json={
            "zone_id": str(uuid4()),
            "code": "VAK-1",
            "area_m2": 100,
            "latitude": -7.3,
            "longitude": 112.7,
            "survey_date": "2026-11-16",
        },
        headers=headers,
    )
    assert response.status_code == 501
    assert response.json()["code"] == "not_implemented"
    db_mock.commit.assert_not_awaited()
    db_mock.add.assert_not_called()


def test_public_contract_does_not_fabricate_data(client):
    response = client.get("/api/v1/public/plots")
    assert response.status_code == 501
    assert "items" not in response.json()


def test_second_migration_head_is_rejected(tmp_path: Path):
    versions = tmp_path / "versions"
    versions.mkdir()
    for revision in ["first", "second"]:
        (versions / f"{revision}.py").write_text(
            f"revision = '{revision}'\ndown_revision = None\n", encoding="utf-8"
        )
    config = Config()
    config.set_main_option("script_location", str(tmp_path))
    with pytest.raises(ValueError, match="exactly one Alembic head"):
        check_heads(config)
