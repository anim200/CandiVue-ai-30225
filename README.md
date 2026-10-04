# CandiVue AI

AI-powered recruitment and interview platform (BJIT AI Trainee final project).

> Work in progress: this README currently covers the platform foundation
> (backend + database). Architecture, usage, data providers and known
> limitations will be added as the features are built.

## Prerequisites

- Docker Desktop (Docker Engine with Docker Compose v2)
- Git

Nothing else is needed to run the app. Python is only needed to run the
tests locally.

## Setup

Create your own `.env` from the template and change the placeholder values
(the database password should use letters and digits only):

```bash
cp .env.example .env              # macOS / Linux / Git Bash
Copy-Item .env.example .env       # Windows PowerShell
```

`.env` is git-ignored. Never commit it.

## Commands

| Task | Command |
|---|---|
| Build the images | `docker compose build` |
| Run (build if needed, in the background) | `docker compose up --build -d` |
| Check status | `docker compose ps` |
| Follow backend logs | `docker compose logs -f backend` |
| Stop (keeps the database data) | `docker compose down` |
| Full reset (deletes the database volume) | `docker compose down -v` |
| Full reset including built images | `docker compose down -v --rmi local` |

After a full reset, run `docker compose up --build -d` again. The database
is recreated from scratch and the pgvector extension is enabled
automatically.

## Database and migrations

Tables are defined in `backend/app/db/models/` and created by
[Alembic](https://alembic.sqlalchemy.org/) migrations in
`backend/migrations/versions/`. The backend applies all pending migrations
every time it starts (`alembic upgrade head`), so no manual step is needed.

LangGraph saves workflow state (checkpoints) in the same database, in its
own `checkpoint*` tables. A stopped or restarted workflow continues from its
last completed step.

| Task | Command |
|---|---|
| Show the current migration | `docker compose exec backend alembic current` |
| Create a migration after changing a model | see below |

To create a migration after changing a model, rebuild the image and let
Alembic compare the models with the database. The new file is written into
`backend/migrations/versions/`; review it before committing.

```bash
docker compose build backend
docker compose run --rm -v "$(pwd)/backend/migrations:/app/migrations" backend   alembic revision --autogenerate -m "describe the change"
```

On Windows Git Bash, prefix the second command with `MSYS_NO_PATHCONV=1`.

## Check that it works

- Health check: <http://localhost:8000/api/health> returns
  `{"status":"ok","database":"ok"}`
- API documentation (OpenAPI): <http://localhost:8000/docs>

The port can be changed with `BACKEND_PORT` in `.env`.

## Services

| Service | Image | Notes |
|---|---|---|
| `db` | `pgvector/pgvector:0.8.7-pg17-bookworm` | PostgreSQL 17 with pgvector. Data in the named volume `pgdata`. Not exposed to the host. |
| `backend` | built from `backend/Dockerfile` (target `runtime`) | FastAPI on Python 3.13. Applies migrations on start. |
| `tests` | built from `backend/Dockerfile` (target `test`) | Only runs on demand (see below). |

## Security note (local development)

The backend uses plain HTTP and is bound to `127.0.0.1` only, so it is not
reachable from other machines. This is a local-development exception; it
must not be exposed on a network without HTTPS.

## Running the tests

All tests, against the real database (the stack must be running):

```bash
docker compose run --rm --build tests
```

Locally without Docker (tests that need the database are skipped):

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows (source .venv/bin/activate on macOS/Linux)
pip install -r requirements-dev.txt
pytest
```
