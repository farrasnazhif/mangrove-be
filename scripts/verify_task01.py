"""Read-only checks of the running Foundation API. No login or database writes."""

import argparse
import json
from pathlib import Path
from uuid import UUID, uuid4

import httpx


def check(response: httpx.Response, status: int, label: str) -> None:
    if response.status_code != status:
        raise RuntimeError(f"FAIL {label}: expected HTTP {status}, got {response.status_code}")
    UUID(response.headers["X-Request-ID"])
    if status >= 400:
        body = response.json()
        assert set(body) == {"code", "message", "details", "request_id"}
        assert body["request_id"] == response.headers["X-Request-ID"]
        if status == 422:
            assert body["details"] and body["details"][0]["field"]
    print(f"PASS {label}: HTTP {status}, request ID and response contract")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=15) as client:
        request_id = str(uuid4())
        response = client.get("/api/v1/health", headers={"X-Request-ID": request_id})
        check(response, 200, "Health")
        assert response.headers["X-Request-ID"] == request_id
        check(client.get("/api/v1/me"), 401, "Anonymous manager access denied")
        check(client.get("/api/v1/missing-resource"), 404, "Controlled missing resource")
        check(client.get("/api/v1/public/plots"), 501, "Planned feature reported honestly")
        check(client.get("/api/v1/public/plots?page_size=101"), 422, "Pagination hard limit")
        check(client.get("/api/v1/public/plots?sort=hashed_password"), 422, "Sort allowlist")
        check(client.get("/api/v1/public/plots?filter=password:invalid"), 422, "Filter allowlist")
        check(client.get("/docs"), 200, "Swagger docs")
        response = client.get("/openapi.json")
        check(response, 200, "OpenAPI")
        snapshot = Path(__file__).resolve().parents[1] / "contracts" / "openapi.json"
        assert response.json() == json.loads(snapshot.read_text(encoding="utf-8")), (
            "OpenAPI differs from reviewed contract"
        )
    print(
        "All Task 01 API checks passed. Check the server terminal for JSON logs with matching request IDs."
    )


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, RuntimeError, AssertionError, KeyError, ValueError) as error:
        raise SystemExit(str(error)) from None
