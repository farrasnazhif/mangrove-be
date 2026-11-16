"""Interactive API check against a running dev server; never prints credentials/tokens."""

import argparse
import getpass

import httpx


def expect(label: str, response: httpx.Response, status: int) -> None:
    if response.status_code != status:
        raise RuntimeError(f"FAIL {label}: expected HTTP {status}, got {response.status_code}")
    print(f"PASS {label}: HTTP {status}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--email", default="manager.synthetic@example.test")
    args = parser.parse_args()
    password = getpass.getpass("Password manager sintetis: ")
    with httpx.Client(base_url=args.base_url, timeout=15) as client:
        expect("Health anonim", client.get("/api/v1/health"), 200)
        expect("Manager route menolak anonim", client.get("/api/v1/me"), 401)
        expect(
            "Role header tidak memberi akses",
            client.get("/api/v1/me", headers={"X-Role": "manager"}),
            401,
        )
        credentials = {"email": args.email, "password": password}
        expect("Login tanpa CSRF ditolak", client.post("/api/v1/auth/login", json=credentials), 403)
        response = client.get("/api/v1/auth/csrf")
        expect("CSRF awal", response, 200)
        csrf = response.json()["csrf_token"]
        expect(
            "Role dari body ditolak",
            client.post(
                "/api/v1/auth/login",
                json={**credentials, "role": "manager"},
                headers={"X-CSRF-Token": csrf},
            ),
            422,
        )
        response = client.post(
            "/api/v1/auth/login", json=credentials, headers={"X-CSRF-Token": csrf}
        )
        expect("Login manager", response, 200)
        user = response.json()["user"]
        if user["role"] != "manager" or "hashed_password" in user:
            raise RuntimeError("FAIL role atau privasi response login")
        session_cookies = [
            cookie for cookie in client.cookies.jar if cookie.has_nonstandard_attr("HttpOnly")
        ]
        if len(session_cookies) != 1:
            raise RuntimeError("FAIL cookie session HttpOnly")
        session_cookie = session_cookies[0]
        old_token = session_cookie.value
        session_name = session_cookie.name
        csrf = response.json()["csrf_token"]
        print("PASS role manager dari server dan cookie session HttpOnly")
        expect("Me manager", client.get("/api/v1/me"), 200)
        expect("Alias me manager", client.get("/api/v1/auth/me"), 200)
        expect("Logout tanpa CSRF ditolak", client.post("/api/v1/auth/logout"), 403)
        expect(
            "Logout dengan CSRF salah ditolak",
            client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "wrong"}),
            403,
        )
        expect(
            "Logout valid", client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}), 200
        )
        if session_name in client.cookies:
            raise RuntimeError("FAIL cookie session masih tersimpan setelah logout")
        expect("Me setelah logout ditolak", client.get("/api/v1/me"), 401)
        expect(
            "Replay token lama ditolak",
            client.get("/api/v1/me", headers={"Authorization": f"Bearer {old_token}"}),
            401,
        )
    print("Semua pemeriksaan API berhasil. Logout mencabut seluruh sesi manager ini.")


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
