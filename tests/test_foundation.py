import asyncio
import io
import json
import logging
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.api.pagination import Pagination, plot_pagination
from app.core.cors import APICORSMiddleware
from app.core.errors import HiddenResourceError, install_error_handlers
from app.core.observability import JSONFormatter, RequestContextMiddleware, logger
from app.schemas.inventory import CalculationResponse


@pytest.fixture
def foundation_app():
    application = FastAPI()
    install_error_handlers(application)
    application.add_middleware(
        APICORSMiddleware,
        allow_origins=["https://frontend.example"],
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["X-Request-ID"],
    )
    application.add_middleware(RequestContextMiddleware)

    @application.get("/pagination")
    async def page(pagination: Pagination = Depends(plot_pagination)):
        return {**pagination.model_dump(), "offset": pagination.offset}

    @application.get("/records/{record_id}")
    async def record(record_id: str):
        # Neither hidden nor missing objects disclose their existence.
        if record_id == "hidden":
            raise HiddenResourceError()
        raise HTTPException(404)

    @application.get("/crash")
    async def crash():
        raise RuntimeError("password=never-return-or-log-this-value")

    return application


def test_cors_denial_uses_error_envelope(foundation_app):
    response = TestClient(foundation_app).options(
        "/pagination",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/json"
    assert set(response.json()) == {"code", "message", "details", "request_id"}
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert response.json()["code"] == "cors_denied"
    assert "access-control-allow-origin" not in response.headers


def test_allowed_cors_preflight_still_succeeds(foundation_app):
    response = TestClient(foundation_app).options(
        "/pagination",
        headers={
            "Origin": "https://frontend.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "https://frontend.example"
    assert response.headers["X-Request-ID"]


def test_pagination_defaults_and_offset(foundation_app):
    client = TestClient(foundation_app)
    assert client.get("/pagination").json() == {
        "page": 1,
        "page_size": 25,
        "sort": "code",
        "descending": False,
        "filters": {},
        "offset": 0,
    }
    body = client.get(
        "/pagination?page=3&page_size=10&sort=-survey_date&filter=status:draft"
    ).json()
    assert body["offset"] == 20
    assert body["descending"] is True
    assert body["filters"] == {"status": "draft"}


@pytest.mark.parametrize(
    "query",
    [
        "page_size=101",
        "page_size=0",
        "page=0",
        "page=not-a-number",
        "sort=hashed_password",
        "sort=code;DROP TABLE users",
        "filter=password:guess",
        "filter=status:draft&filter=status:published",
        "filter=status",
        "role=manager",
    ],
)
def test_pagination_limits_and_allowlists(foundation_app, query):
    response = TestClient(foundation_app).get("/pagination?" + query)
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"code", "message", "details", "request_id"}
    assert body["details"]
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_hidden_and_missing_records_are_indistinguishable(foundation_app):
    client = TestClient(foundation_app)
    hidden = client.get("/records/hidden")
    missing = client.get("/records/missing")
    assert hidden.status_code == missing.status_code == 404
    first, second = hidden.json(), missing.json()
    first.pop("request_id")
    second.pop("request_id")
    assert first == second
    assert first == {"code": "not_found", "message": "Resource not found", "details": []}


@pytest.fixture
def json_events(monkeypatch):
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JSONFormatter())
    monkeypatch.setattr(logger, "handlers", [handler])
    return buffer


def test_errors_and_logs_do_not_leak_secrets(foundation_app, json_events):
    response = TestClient(foundation_app).get(
        "/crash?token=never-log-query", headers={"Authorization": "Bearer never-log-header"}
    )
    assert response.status_code == 500
    assert response.json()["message"] == "Internal server error"
    assert "never-" not in response.text + json_events.getvalue()
    events = [json.loads(line) for line in json_events.getvalue().splitlines()]
    assert {event["event"] for event in events} == {"http.error", "http.request"}
    assert all(event["request_id"] == response.headers["X-Request-ID"] for event in events)
    assert events[0]["exception_type"] == "RuntimeError"


def test_validation_does_not_echo_password_input(client):
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    password = "do-not-reflect-this-password" * 5
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "manager@example.test", "password": password},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422
    body = response.json()
    assert password not in response.text
    assert any(detail["field"] == "body.password" for detail in body["details"])


def test_request_ids_are_isolated_between_concurrent_requests(foundation_app, json_events):
    async def check():
        async with AsyncClient(
            transport=ASGITransport(app=foundation_app), base_url="http://test"
        ) as client:
            ids = [str(uuid4()) for _ in range(8)]
            responses = await asyncio.gather(
                *[
                    client.get("/pagination", headers={"X-Request-ID": request_id})
                    for request_id in ids
                ]
            )
            assert [response.headers["X-Request-ID"] for response in responses] == ids
            invalid = await client.get("/pagination", headers={"X-Request-ID": "untrusted-id"})
            UUID(invalid.headers["X-Request-ID"])

    asyncio.run(check())
    events = [json.loads(line) for line in json_events.getvalue().splitlines()]
    assert len({event["request_id"] for event in events}) == 9


def test_timestamp_contract_rejects_naive_values():
    from pydantic import ValidationError

    data = {
        "id": str(uuid4()),
        "plot_id": str(uuid4()),
        "method_version_id": str(uuid4()),
        "input_revision": 1,
        "input_hash": "sample",
        "qa_flags": [],
        "qa_status": "draft",
        "carbon_stock": dict.fromkeys(
            ["agc_mg_c_ha", "bgc_mg_c_ha", "soc_mg_c_ha", "total_mg_c_ha", "co2e_mg_ha"]
        ),
        "created_at": "2026-11-16T12:00:00",
    }
    with pytest.raises(ValidationError):
        CalculationResponse.model_validate(data)
    data["created_at"] += "+07:00"
    value = CalculationResponse.model_validate(data)
    assert value.model_dump(mode="json")["created_at"] == "2026-11-16T12:00:00+07:00"
