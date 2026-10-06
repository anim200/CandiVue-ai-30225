# CandiVue AI

AI-powered recruitment and interview platform (BJIT AI Trainee final project).

> Work in progress: this README currently covers the platform foundation
> (backend, database and frontend skeleton). Architecture, usage, data
> providers and known limitations will be added as the features are built.

## Prerequisites

- Docker Desktop (Docker Engine with Docker Compose v2)
- Git

Nothing else is needed to run the app. Python and Node.js are only needed to
run the tests or the frontend development server locally.

## Setup

Create your own `.env` from the template and change the placeholder values
(the database password should use letters and digits only):

```bash
cp .env.example .env              # macOS / Linux / Git Bash
Copy-Item .env.example .env       # Windows PowerShell
```

`.env` is git-ignored. Never commit it.

Before the first start, also set in `.env`:

- `JWT_SECRET`: a long random value (32+ characters) that signs login
  tokens. Create one with
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- `DEMO_INTERVIEWER_PASSWORD`: the password of the first interviewer
  account (8+ characters). The account is created on the first start; later
  changes to these settings do not change an existing account (use a full
  reset to start again).

## Commands

| Task | Command |
|---|---|
| Build the images | `docker compose build` |
| Run (build if needed, in the background) | `docker compose up --build -d` |
| Check status | `docker compose ps` |
| Open the app | <http://localhost:5173> |
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
last completed step. Alembic is set to ignore these tables, so migrations
never change or drop them.

## Background AI runs

Long AI work (CV screening, interview Q&A analysis, final assessment) runs in
the background, so the API answers at once and the screen stays responsive.

- Each run has a status: `pending` → `running` → `completed`, `failed`, or
  `waiting_for_review` (paused until the interviewer reviews the result).
- Screening runs also show progress, e.g. 12 of 20 CVs.
- A failed run stores a short, plain-language message (no technical details).
- If the backend stops in the middle of a run, the run starts again
  automatically on the next start and continues from its last saved step.
- Known limitation: background runs execute inside the backend container (two
  at a time), which is sufficient for the single-machine local setup this
  project requires.

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

- App: <http://localhost:5173> opens the sign-in page. After signing in,
  the header shows a green **Connected** badge (red **Server unavailable**
  if the backend cannot be reached). With a certificate in `certs/`, the
  same app is also on <https://localhost:5443> (see "Transport security").
- Health check: <http://localhost:8000/api/health> returns
  `{"status":"ok","database":"ok"}`
- API documentation (OpenAPI): <http://localhost:8000/docs>

The ports can be changed with `FRONTEND_PORT` and `BACKEND_PORT` in `.env`.
If you change `FRONTEND_PORT`, change the port in `CORS_ORIGINS` too.

## Frontend

The interviewer and candidate screens are a single-page web app in
`frontend/`, built from the design handoff in
[`docs/design_handoff_candivue_ui/`](docs/design_handoff_candivue_ui/README.md).

| Part | Choice | Why |
|---|---|---|
| UI framework | React 19 (JavaScript) | Widely used, large ecosystem, well suited to live screens such as the interview page. |
| Build tool | Vite | Fast development server with live reload; builds plain HTML/CSS/JS files. |
| Components | Mantine 9 | Ready-made, accessible components (tables, forms, date pickers, charts, notifications) that fit a data-heavy tool, with no CSS framework to learn. |
| Navigation | React Router 8 | One address per screen, so pages can be bookmarked and shared between tabs. |
| Icons / fonts | Tabler Icons, Public Sans, IBM Plex Mono | Installed as npm packages, so the app loads no files from external sites. |

How it runs:

- **Docker:** the `frontend` image builds the app with Node and serves the
  result with nginx. nginx forwards every `/api/...` request to the backend,
  so the browser uses one address for both and no CORS is needed.
- **Development:** `npm run dev` gives live reload on the same address and
  forwards `/api` to the backend in the same way. Stop the Docker frontend
  first, because both use port 5173:

```bash
docker compose stop frontend
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

All backend calls go through `frontend/src/api/client.js`, which turns any
failure into a plain-language message (no technical details on screen).

The app is responsive: it works on phones, tablets and desktops. Below
768px wide the left menu folds into a menu button in the header. Every
screen is checked at phone (375px), tablet (768px) and desktop (1280px)
width.

## Services

| Service | Image | Notes |
|---|---|---|
| `db` | `pgvector/pgvector:0.8.7-pg17-bookworm` | PostgreSQL 17 with pgvector. Data in the named volume `pgdata`. Not exposed to the host. |
| `backend` | built from `backend/Dockerfile` (target `runtime`) | FastAPI on Python 3.13. Applies migrations on start. |
| `tests` | built from `backend/Dockerfile` (target `test`) | Only runs on demand (see below). |
| `frontend` | built from `frontend/Dockerfile` | React app served by nginx 1.31 (HTTP, and HTTPS when `certs/` has a certificate); forwards `/api` to the backend. |

## AI provider and data sent to it

| Setting (`.env`) | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` / `LLM_MODEL` | `google_genai` / `gemini-2.5-flash` | Which AI model is used. |
| `LLM_API_KEY` | none | Your own key (Gemini: free from Google AI Studio). |
| `LLM_TIMEOUT_SECONDS` | `60` | Longest wait for one answer. |
| `LLM_MAX_RETRIES` | `2` | Extra tries after a failure, with a growing pause. |
| `LLM_TEMPERATURE` | `0` | Randomness of answers. `0` keeps candidate scores repeatable. |

- **Provider:** Google Gemini API (external service). The provider can be
  changed in `.env` without code changes.
- **What is sent:** job profiles, CV text, interview transcripts and the
  instructions (prompts) needed to screen and assess candidates.
- **Free-tier notice:** on Gemini's free tier, Google may use the data it
  receives to improve its products. Use only synthetic or sample data with a
  free key, never real candidate data.
- **If the AI fails** (timeout, outage, wrong key, rate limit) after all
  retries, the API answers `503` with a clear message instead of crashing.

## Signing in and roles

There are two roles (N9). The backend checks the role on every request,
not only the screens.

| Role | How they get in | What they can use |
|---|---|---|
| Interviewer | Email and password at <http://localhost:5173/login>. The first account comes from `DEMO_INTERVIEWER_EMAIL` / `DEMO_INTERVIEWER_PASSWORD` in `.env`. | Everything for interviewers: jobs, screening, interviews, reports. |
| Candidate | No account. The private link in the invitation email (`/join/<link>`) gives a token for that one interview only. | Their own interview only. Never scores, rankings, transcripts or reports. |

- Passwords are stored as Argon2 hashes, never as text. Interview links are
  stored only as SHA-256 hashes.
- Sign-in gives a signed token (JWT) valid for `ACCESS_TOKEN_MINUTES`
  (default 480, one working day). After it expires the user signs in again.
- A wrong email and a wrong password give the same message, so the login
  form does not reveal which accounts exist. Logs never contain emails or
  passwords.
- The token is kept per browser tab (`sessionStorage`), so an interviewer
  tab and a candidate tab can run side by side (two-tab demo). Closing the
  tab signs out.
- A test (`backend/tests/test_auth_routes.py`) checks every API route and
  fails if one is missing the interviewer check.

Known limitations: signing out removes the token from the tab, but the
token itself stays valid until it expires; there is no limit on login
attempts and no password-change screen (local demo only).

## Transport security

How each connection is protected (N10):

| Connection | Protection |
|---|---|
| Browser → app and API (nginx) | HTTPS on <https://localhost:5443> when a certificate is in `certs/` (see below). Without one: plain HTTP on <http://localhost:5173>, bound to `127.0.0.1` only (local-development exception). |
| Browser → backend directly (`/docs`, port 8000) | Plain HTTP, bound to `127.0.0.1` only (local-development exception, for the API documentation). |
| nginx → backend, backend → database | Inside Docker's private network only; never leaves the machine. The database has no published port. |
| Backend → AI provider (Google Gemini) and other external services | HTTPS (TLS), handled by the providers' client libraries. |
| Interview audio and video (WebRTC, built with F3) | Always encrypted by the browsers (DTLS-SRTP). |

**Local-development exceptions.** Plain HTTP is used only on `127.0.0.1`,
so nothing is reachable from other machines. Never open the HTTP ports to a
network; use HTTPS for that.

**Turn on HTTPS (optional).** Create a certificate that your browser trusts
with [mkcert](https://github.com/FiloSottile/mkcert) (install once, for
example `winget install FiloSottile.mkcert` on Windows or
`brew install mkcert` on macOS), then from the project folder:

```bash
mkcert -install
mkcert -cert-file certs/cert.pem -key-file certs/key.pem localhost 127.0.0.1 ::1
docker compose up -d --build
```

Open <https://localhost:5443>. The frontend log shows
`CandiVue: certificate found, HTTPS enabled`. Delete the two `.pem` files
and restart to go back to HTTP. Certificates are git-ignored.

**Using a phone on the same network.** Browsers only allow camera and
microphone on HTTPS (or on `localhost`), so a phone needs HTTPS. Add your
computer's network address to the certificate (for example
`mkcert -cert-file certs/cert.pem -key-file certs/key.pem localhost 127.0.0.1 192.168.1.20`),
set `HTTPS_BIND_ADDRESS=0.0.0.0` in `.env`, restart, and install mkcert's
root certificate on the phone (`mkcert -CAROOT` shows where it is). Plain
HTTP stays on localhost even then.

**Other protections in nginx** (all responses, including `/api`):

- `Content-Security-Policy`: only CandiVue's own scripts, fonts and API
  may load; no other site may frame the app.
- `Referrer-Policy: no-referrer`: addresses such as interview links are
  never sent to other sites.
- `X-Content-Type-Options`, `X-Frame-Options`, and a `Permissions-Policy`
  that allows camera and microphone only for CandiVue itself.
- `Strict-Transport-Security` when HTTPS is used.
- The access log hides interview link tokens (`/join/[hidden]`), and nginx
  does not reveal its version.

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

Frontend tests (no backend needed; requires Node.js 22.22 or later):

```bash
cd frontend
npm install
npm test
```
