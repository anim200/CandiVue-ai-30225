# CandiVue AI – Project Status

Update this file at the end of each work session. Every Claude thread reads it.

## Done
- 30-09-2026: Requirement analysis, clarification, product identity, technology research
- 30-09-2026 to 02-10-2026: High-level system diagram (Fig 1), detailed architecture diagram (Fig 2), LangGraph designs (Fig 3–6)
- 01-10-2026: GitHub repository created (candivue-ai-30225); README and .gitignore committed (#646013)

## Current design (summary)
- LangGraph 1 – Hiring Assistant chatbot (agent): job profile, JD with optional RAG, JD approval (HITL), job post with Google Form link via MCP, candidate selection, invitation approval (HITL), calendar + email via MCP, interview-question suggestions (RAG question bank) on the interview page
- CV Collector service: Google Form → Google Drive → data/cv_intake (Drive API)
- LangGraph 2 – CV Screening & Scoring (workflow, started from the app)
- LangGraph 3 – Interview Q&A Analysis (workflow, starts when the interview ends)
- LangGraph 4 – Final Assessment (workflow, HITL review in Reports screen)

## In progress
- Platform foundation (WBS Day 4 work package), branch module/platform-foundation:
  - Done 02-10-2026: .env.example, FastAPI skeleton with GET /api/health (DB check), JSON logging, generic error handler, backend Dockerfile, Docker Compose with PostgreSQL 17 + pgvector 0.8.7, health tests, README run/stop/reset commands. Verified: stack healthy, pgvector enabled.
  - Merged into dev 03-10-2026 (PR #1). Work continues on the same branch until module 2 is complete.
  - Done 03-10-2026 (WBS 2.3 persistent records + LangGraph state): Alembic with first migration (10 tables: users, jobs, job_descriptions, candidates, screening_runs, candidate_scores, interview_sessions, transcript_turns, qa_analyses, assessment_reports), migrations applied on backend start, LangGraph Postgres checkpointer opened at startup, tests in Docker (`docker compose run --rm tests`): tables exist, candidate delete cascades (N19), no protected-attribute columns (N20), graph resumes after restart (N26). Candidates have no account: they join by unique link only.
  - Done 04-10-2026 (#646479 AI model access layer): `app/ai/llm.py` with `invoke_llm()` (timeout, retries with growing pause, one `AIServiceError`), API answers 503 on AI failure (N6), provider set in .env (default Google Gemini free tier, switchable without code change), provider disclosure in README (N18), tests with fake models (no API key needed).
  - Done 04-10-2026: `LLM_TEMPERATURE` (default 0) so scores are repeatable (F2, B2).
  - Done 04-10-2026 (#646480 background runs): `app/runs/runner.py` runs long AI work in 2 worker threads; status pending/running/waiting_for_review/completed/failed with plain-language errors; screening progress (processed/total); interrupted runs resume at startup with the same LangGraph thread_id (`graph_config()`); `RunStatusOut` has no scores (N9). All three run tables (screening_runs, qa_analyses, assessment_reports) now share `RunStateMixin`. Alembic now ignores LangGraph's checkpoint* tables (autogenerate had tried to drop them); a test checks models and migrations match.
  - Feature work must: register its run kind with `register_run_kind()`, use `graph_config()` for the graph, call `save_progress()` per item, and add interviewer-only start/status endpoints (#646482).
  - Done 05-10-2026 (#646481 frontend): UI design handoff from Claude Design committed in `docs/design_handoff_candivue_ui/` (all screens, synthetic data). `frontend/`: React 19 + Vite 8 + Mantine 9 + React Router 8, plain JavaScript; harbor theme from the handoff; app shell (logo, left menu: Jobs, Interviews, Reports, Hiring Assistant, Knowledge base) with "coming soon" pages, plain-language 404 and crash pages; `src/api/client.js` is the only code that calls the backend (plain-language errors, 15 s timeout); header badge Connected / Server unavailable from `/api/health`. Docker: Node builds, nginx 1.31 serves and forwards `/api` to the backend (same address, no CORS); `frontend` service on 127.0.0.1:5173 (`FRONTEND_PORT`). 5 Vitest tests; npm audit clean.
  - Done 06-10-2026 (#646482 login + roles): backend `app/auth/` (pwdlib Argon2 passwords, PyJWT HS256 tokens with role interviewer/candidate, `require_interviewer` / `require_candidate` guards, first interviewer created at startup from `DEMO_INTERVIEWER_*` in .env), routes `POST /api/auth/login`, `POST /api/auth/candidate` (link token → token for that one session; refused when ended/cancelled), `GET /api/auth/me`. `JWT_SECRET` (32+ chars) required. Test `test_every_api_route_is_guarded` fails if any /api route lacks the interviewer guard (allowlist: health, login, candidate, me). Frontend: login page from the design (responsive), per-tab session in sessionStorage, token sent by `client.js`, 401 → sign out to `/login?expired=1`, route guard, user menu with Sign out, candidate page `/join/:linkToken`. Login headline is still the design's placeholder: replace with own positioning statement (E6). 45 backend + 9 frontend tests.
  - New routers must use `dependencies=[Depends(require_interviewer)]` (or be listed in the test's allowlist on purpose). Interview-link time window and one-connection rule: build with F3 sessions.
  - Done 06-10-2026 (#646483 transport security, N10): nginx split into `frontend/nginx/` (default.conf HTTP, app.conf shared, https.conf); optional HTTPS on https://localhost:5443, switched on at container start by `enable-https.sh` when `certs/cert.pem` + `key.pem` exist (mkcert; git-ignored); HTTP always 127.0.0.1 only; `HTTPS_BIND_ADDRESS` opt-in for phones on the LAN (camera/mic need HTTPS). Security headers on all responses (CSP, Referrer-Policy no-referrer, X-Frame-Options, nosniff, Permissions-Policy camera/mic self, HSTS on HTTPS). nginx access log hides `/join/<token>`. `.gitattributes` keeps `*.sh` LF. README "Transport security" documents every connection and the local exceptions. Extend the CSP in `frontend/nginx/app.conf` when a feature needs a new source (e.g. WebSocket/WebRTC servers).
  - **Module 2 (story #646469) complete 06-10-2026**; merged into dev.

## Design notes to apply in later modules
- Two roles: Interviewer logs in with email + password; Candidate authenticates with the unique interview link. Both get a role-based JWT; the backend enforces the role (N9). Candidate token is limited to one session.
- Interview link safeguards (WBS 4.1–4.2): link valid only from shortly before the scheduled time until the interview ends; disabled after the interview; one candidate connection at a time; only the token hash is stored (done).
- F7: the reference face/voice must be captured with consent BEFORE the interview (e.g. when the candidate confirms the invitation), not just before the call. "Link for access, F7 for identity."
- One-laptop demo (two tabs, allowed by F3 clarification):
  - Same microphone hears both speakers: use the in-call mute on the tab not speaking, or a separate mic per tab (headset + laptop mic); headphones against echo.
  - Keep the login token per tab (sessionStorage) so interviewer and candidate tabs do not overwrite each other (WBS 2.4); Incognito window as backup.
  - Use the same browser for both tabs so they can share the webcam.

## UI design decisions (from the design handoff)
- Build every screen from `docs/design_handoff_candivue_ui/` with Mantine; the `.dc.html` files are references, not code to copy.
- Responsive for all devices (decided 05-10-2026; overrides the handoff's "desktop-first 1280px+"). Mobile/tablet layouts are adapted in code, not designed in Claude Design. Check each screen at 375 / 768 / 1280 px before committing. App shell done: burger menu below 768px, icon-only connection badge on phones.
- Still to decide: Live Interview identity layout (1a fixed right column / 1b tabs / 1c strip over video; tabs hide the identity result, so 1a or 1c); biometric retention period and consent wording (N17; design shows "30 days" as a placeholder).
- Login (#646482, done): "Forgot password?" and "Keep me signed in" left out (not required; "keep me signed in" conflicts with per-tab sessionStorage tokens).
- Interview Analysis tabs F8, F9, F10 are stretch: build only after F1–F7 and F11 work (§11.4).
- Dark mode is designed but postponed; add later with Mantine's colour-scheme manager (`localStorage` key `candivue-theme`).
- Knowledge Base "personal data found" scan is a design proposal that needs its own backend step.

## Git workflow
- Branches: main (initial structure only), dev, module/<name> per WBS module (not per task)
- module/* branches start from dev and merge into dev by pull request; dev merges into main when the project is complete
- Git Bash is used for git commands; check the branch name in the prompt before committing

## Next
- Start the next WBS module on a new module/<name> branch created from dev
- Technical risk prototype: two-party video call, speech-to-text trial, multi-node LangGraph trial

## Open decisions (need trainer confirmation)
- Job-board posting via MCP (out of scope in the BID)
- Calendar MCP integration (out of scope in the BID unless it is the F11 innovation feature)
- F5 split: job-related answers → LLM, company-related answers → RAG
- F7 face/voice recognition: keep or drop?

## Redmine task IDs
- #646013 Initialize and share the BJIT GitHub repository, README and .gitignore
- #646476 Platform foundation: backend skeleton, health endpoint, Docker Compose with PostgreSQL + pgvector (closed 02-10-2026)
- Story #646469 Platform Foundation & Role Access (module/platform-foundation) — complete 06-10-2026:
  - #646475 Project structure, pinned dependencies, .env.example
  - #646476 Docker/Compose, named volumes, one-command startup
  - #646477 FastAPI, Pydantic, OpenAPI docs, error handling, structured logs
  - #646478 Persistent records + LangGraph state with recovery after restart (done 03-10-2026)
  - #646479 AI model access layer: timeouts, retries, clear failure state (done 04-10-2026)
  - #646480 Long AI operations run async with processing status (done 04-10-2026)
  - #646481 Frontend navigation and connection to backend (done 05-10-2026)
  - #646482 Lightweight auth; block Candidate access to scores, rankings, assessments (done 06-10-2026)
  - #646483 Secure transport for APIs and media; document local exceptions (done 06-10-2026)
