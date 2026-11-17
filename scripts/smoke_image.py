"""Run one immutable image in staging and production using only env differences.

Creates two short-lived, localhost-only containers; removes only those containers.
No database or production credentials are needed for these foundation HTTP checks.
"""

import argparse
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from uuid import uuid4


def docker(*args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(["docker", *args], check=True, capture_output=True, text=True, env=env)
    return result.stdout.strip()


def smoke(image_id: str, environment: str) -> None:
    name = "mangrove-foundation-smoke-" + uuid4().hex
    env = {**os.environ, "JWT_SECRET": secrets.token_hex(32)}
    created = False
    try:
        docker(
            "run",
            "-d",
            "--name",
            name,
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "-p",
            "127.0.0.1::8080",
            "-e",
            f"ENVIRONMENT={environment}",
            "-e",
            "SESSION_COOKIE_SECURE=true",
            "-e",
            "JWT_SECRET",
            "-e",
            "DATABASE_URL=postgresql+asyncpg://smoke:smoke@127.0.0.1/unused",
            image_id,
            env=env,
        )
        created = True
        address = docker("port", name, "8080/tcp").splitlines()[0]
        base_url = "http://" + address
        deadline = time.monotonic() + 45
        while True:
            try:
                with urllib.request.urlopen(base_url + "/api/v1/health", timeout=2) as response:
                    assert json.load(response) == {"status": "ok"}
                    assert response.headers["X-Request-ID"]
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"{environment} container did not become ready") from None
                time.sleep(0.5)
        for path, expected in [("/api/v1/me", 401), ("/api/v1/public/plots?page_size=101", 422)]:
            try:
                urllib.request.urlopen(base_url + path, timeout=5)
                raise AssertionError(f"{path} unexpectedly succeeded")
            except urllib.error.HTTPError as error:
                assert error.code == expected
                body = json.load(error)
                assert set(body) == {"code", "message", "details", "request_id"}
                assert body["request_id"] == error.headers["X-Request-ID"]
        assert docker("exec", name, "id", "-u") == "10001"
        preflight = urllib.request.Request(
            base_url + "/api/v1/health",
            method="OPTIONS",
            headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"},
        )
        try:
            urllib.request.urlopen(preflight, timeout=5)
            raise AssertionError("Untrusted CORS preflight unexpectedly succeeded")
        except urllib.error.HTTPError as error:
            assert error.code == 400
            body = json.load(error)
            assert body["code"] == "cors_denied"
            assert body["request_id"] == error.headers["X-Request-ID"]
        logs = docker("logs", name)
        for line in logs.splitlines():
            json.loads(line)
        assert env["JWT_SECRET"] not in logs
        print(
            f"PASS {environment}: same image {image_id}; health, errors, pagination, non-root user and JSON logs"
        )
    finally:
        if created:
            docker("rm", "-f", name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", default="mangrove-be:task01", nargs="?")
    args = parser.parse_args()
    image_id = docker("image", "inspect", "--format", "{{.Id}}", args.image)
    for environment in ("staging", "production"):
        smoke(image_id, environment)


if __name__ == "__main__":
    main()
