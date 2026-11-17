# mangrove-be

FastAPI backend for the Mangrove Carbon Stock Inventory. Spec: [PRD.md](PRD.md).

## Setup

1. Clone the repo:

```sh
git clone https://github.com/farrasnazhif/mangrove-be
cd mangrove-be
```

2. Install [Docker](https://docs.docker.com/get-docker/) and [uv](https://docs.astral.sh/uv/) (Python package manager):

macOS:

```sh
brew install uv
```

macOS / Linux without Homebrew:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
winget install --id astral-sh.uv
# or
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen the terminal afterwards, then check with `uv --version`.

3. Create your env file:

macOS / Linux:

```sh
cp .env.example .env
```

Windows (PowerShell):

```powershell
Copy-Item .env.example .env
```

## Run

1. Start the database (stays in the foreground; use `docker compose up -d` to run it in the background):

```sh
docker compose up
```

2. In a new terminal, install the dependencies (first time, and whenever `pyproject.toml` changes):

```sh
uv sync
```

3. Start the API, then open http://localhost:8080/docs:

```sh
uv run uvicorn app.main:app --reload --port 8080 --no-access-log --log-config logging.json
```

## Test

```sh
uv run pytest
```

Task 03: ikuti [panduan seed, migrasi, dan pemeriksaan bersama](TASK03_TESTING.md).
Tes PostGIS hanya berjalan jika `TEST_DATABASE_URL` diatur; selain itu ditandai skipped.
Seed dijalankan dengan `uv run python -m app.db.seed` setelah `uv run alembic upgrade head`.
Login membutuhkan token dari `GET /api/v1/auth/csrf` pada header `X-CSRF-Token`.

Task 01: [panduan Foundation dan pemeriksaan pengguna](TASK01_TESTING.md).
Task 02: [skema, migrasi, provenance dan verifikasi constraint PostGIS](TASK02_TESTING.md).
Kontrak frontend: [contracts/openapi.json](contracts/openapi.json), dengan
[penjelasan status implementasi dan perubahan kontrak](contracts/README.md).
Route fitur planned mengembalikan 501; schema 2xx-nya belum berarti fitur tersebut tersedia.
Error API sekarang memakai `{code, message, details, request_id}`, menggantikan `detail`.

Untuk log JSON beserta request ID:

```sh
uv run uvicorn app.main:app --reload --port 8080 --no-access-log --log-config logging.json
```

Image produksi dibangun dengan `docker build -t mangrove-be:task01 .`; jalankan image
yang sama pada staging/production dengan env masing-masing. Contoh env tersedia di
`config/`; secret lokal dan file `.env.*` tidak dimasukkan Git maupun build context.

## Layout

- `app/api/v1/` routers, `app/models/` ORM, `app/schemas/` Pydantic (public vs manager separate)
- `app/calc/` pure scientific functions, no DB/FastAPI imports
- `app/services/` publication, export, chat orchestration
- `langflow/flows/` exported, version-controlled flows
