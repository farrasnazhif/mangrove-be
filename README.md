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
uv run uvicorn app.main:app --reload --port 8080
```

## Test

```sh
uv run pytest
```

## Layout

- `app/api/v1/` routers, `app/models/` ORM, `app/schemas/` Pydantic (public vs manager separate)
- `app/calc/` pure scientific functions, no DB/FastAPI imports
- `app/services/` publication, export, chat orchestration
- `langflow/flows/` exported, version-controlled flows
