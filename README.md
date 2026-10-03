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

## Check that it works

- Health check: <http://localhost:8000/api/health> returns
  `{"status":"ok","database":"ok"}`
- API documentation (OpenAPI): <http://localhost:8000/docs>

The port can be changed with `BACKEND_PORT` in `.env`.

## Services

| Service | Image | Notes |
|---|---|---|
| `db` | `pgvector/pgvector:0.8.7-pg17-bookworm` | PostgreSQL 17 with pgvector. Data in the named volume `pgdata`. Not exposed to the host. |
| `backend` | built from `backend/Dockerfile` | FastAPI on Python 3.13. |

## Security note (local development)

The backend uses plain HTTP and is bound to `127.0.0.1` only, so it is not
reachable from other machines. This is a local-development exception; it
must not be exposed on a network without HTTPS.

## Running the tests locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows (source .venv/bin/activate on macOS/Linux)
pip install -r requirements-dev.txt
pytest
```
