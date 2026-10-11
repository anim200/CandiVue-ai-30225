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

The first start also downloads the Ollama image and the embedding model
(a few GB in total), so it takes several minutes once.

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
| `ollama` | `ollama/ollama:0.35.1` | Local embedding model for the knowledge base. Not exposed to the host; models kept in the `ollama_models` volume. |
| `ollama-pull` | `ollama/ollama:0.35.1` | One-time job: downloads the embedding model on the first start, then exits. |
| `jobboard-mcp` | built from `jobboard-mcp/Dockerfile` (target `runtime`) | Our small MCP server that posts approved JDs to Blogger. The only service that holds the Blogger credentials. Not exposed to the host. |
| `jobboard-tests` | built from `jobboard-mcp/Dockerfile` (target `test`) | Only runs on demand (see below). |
| `email-mcp` | built from `email-mcp/Dockerfile` (target `runtime`) | Our small MCP server that emails interview invitations (Gmail SMTP). The only service that holds the email login. Not exposed to the host. |
| `email-tests` | built from `email-mcp/Dockerfile` (target `test`) | Only runs on demand (see below). |
| `calendar-mcp` | built from `calendar-mcp/Dockerfile` (target `runtime`) | Our small MCP server for the interviewer's Google Calendar (busy times, interview events). The only service that holds the calendar sign-in. Not exposed to the host. |
| `calendar-tests` | built from `calendar-mcp/Dockerfile` (target `test`) | Only runs on demand (see below). |
| `livekit` | `livekit/livekit-server:v1.13.9` | Open-source video server for the interviews. Signalling through nginx (`/rtc`); video and audio on ports 7881/tcp and 7882/udp, bound to `127.0.0.1`. Nothing is recorded. |
| `cv-collector` | built from `backend/Dockerfile` (target `runtime`), command `python -m app.collector` | Copies new CVs from the Google Form into the `cv_intake` volume every few minutes. The only service that holds the Google key (read-only). No ports. |
| `frontend` | built from `frontend/Dockerfile` | React app served by nginx 1.31 (HTTP, and HTTPS when `certs/` has a certificate); forwards `/api` to the backend. |

## AI provider and data sent to it

| Setting (`.env`) | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` / `LLM_MODEL` | `google_genai` / `gemini-3.5-flash-lite` | Which AI model is used until the interviewer picks one under the chat. |
| `LLM_MODELS` | `gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite` | Models the interviewer may switch to under the chat (allowed list). |
| `LLM_API_KEY` | none | Your own key (Gemini: free from Google AI Studio). |
| `LLM_TIMEOUT_SECONDS` | `60` | Longest wait for one answer. |
| `LLM_MAX_RETRIES` | `2` | Extra tries after a failure, with a growing pause. |
| `LLM_TEMPERATURE` | `0` | Randomness of answers. `0` keeps candidate scores repeatable. |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | `ollama` / `qwen3-embedding:0.6b` | Model that turns knowledge-base text into embeddings for search. Runs locally in Docker (no key). `google_genai` / `gemini-embedding-001` uses Gemini with the LLM key instead. |
| `MAX_UPLOAD_MB` | `20` | Largest knowledge-base document accepted. |

- **Provider:** Google Gemini API (external service). The provider can be
  changed in `.env` without code changes.
- **What is sent:**
  - Hiring Assistant: the interviewer's chat messages, the job profile,
    knowledge-base passages found by search, and interviewer feedback on
    job descriptions.
  - Knowledge base: **nothing**. Embeddings are made by the local Ollama
    model, so document text and search questions stay on this machine.
    Only passages that the Hiring Assistant chooses to use are sent, as
    part of the chat.
  - Later steps: CV text, interview transcripts and the instructions
    (prompts) needed to screen and assess candidates.

Other external services (N18):

| Service | What it receives |
|---|---|
| Blogger (Google), through `jobboard-mcp` | The approved job description (title, text, requirements) and the Google Form link. No candidate data. |
| Gmail (Google), through `email-mcp` | Interview invitations and cancellations: the candidate's name and email address, the job title, the interview date and time, and the private interview link (also in the attached calendar invite). While `EMAIL_TEST_RECIPIENT` is set, every email goes to that test address instead. |
| Google Calendar, through `calendar-mcp` | The interviewer's own calendar: one event per interview with the candidate's name, the job title, the time and the interviewer's room link (no email address, no scores). To find busy times only the start and end of events are read, never their titles. |
| Google Forms, Google Drive and Google Sheets | Applicants send their name, email address, the job they apply for and their CV file through the form; Google stores the file in Drive and the answers in the response Sheet. The `cv-collector` only **reads** them. |

- **Free-tier notice:** on Gemini's free tier, Google may use the data it
  receives to improve its products. Use only synthetic or sample data with a
  free key, never real candidate data.
- **If the AI fails** (timeout, outage, wrong key, rate limit) after all
  retries, the API answers `503` with a clear message instead of crashing.

**Choosing the model and seeing the quota.** Under the Hiring Assistant's
chat box the interviewer can switch the AI model (only models in
`LLM_MODELS`). The choice is saved (table `llm_models`) and used for every
AI call. Gemini's free tier has a daily request limit **per model** (for
example 20 a day for `gemini-3.5-flash`), and one job needs about 5-8
requests.

- Google has no API that tells how much quota is left, so CandiVue counts
  its own requests per model and day (the count restarts at midnight
  Pacific time, like Google's).
- When Google answers "limit reached" (HTTP 429), the limit and the reset
  time are read from Google's answer and shown: "20 of 20 requests today ·
  limit reached, resets in 13 h". A daily limit is not retried (it would
  only fail again); a short per-minute limit is.
- Requests made with the same key elsewhere are not counted. "Usage on
  Google" opens <https://ai.dev/rate-limit> for Google's exact numbers.
- API: `GET /api/ai/models`, `PUT /api/ai/model` (interviewers only).

## Hiring Assistant (LangGraph 1)

The interviewer prepares a job by chatting with the Hiring Assistant
(Figure 3 in `docs/diagrams/`). One chat thread per job, saved in the
database, so it continues after a restart.

```
START -> load_context -> assistant --(tool call)--> tools --> assistant ...
                                   \--(reply)-----> END
         tools --(a JD was written)--> human_review (pause)
         human_review --approve----> confirm_posting (pause)
         human_review --reject-----> assistant
         human_review --edit-------> human_review
         confirm_posting --post----> post_to_job_board --> assistant
         confirm_posting --skip----> assistant
         tools --(request_job_posting)--> confirm_posting
```

- **assistant**: the LLM reads the chat and decides the next step.
- **tools** (the LLM decides which to call):
  - `save_job_profile`: title, minimum experience, and every requirement
    as mandatory / required / preferred.
  - `rag_search`: searches the knowledge base, only when useful.
  - `write_job_description`: drafts the JD from the profile and any
    passages found; records which documents it used.
  - `save_job_profile` also saves the **scoring weights** the assistant
    suggests (with a reason), and for each requirement short lists of
    names that **also count** (e.g. Docker: Docker Compose, Laravel Sail)
    and **related** close substitutes (e.g. Podman). Screening uses them
    (see "CV screening"). Weights the interviewer states in the chat are
    saved as the interviewer's.
  - `save_application_form`: saves the Google Form link applicants use
    to send their CV (only Google Forms links are accepted).
  - `request_job_posting`: when the interviewer later asks to post a job
    they did not post, this asks them again. It cannot post by itself.
- **human_review**: the graph pauses (LangGraph `interrupt`) until the
  interviewer approves, edits (saved as a new version that still needs
  approval) or rejects with feedback (the assistant writes a new
  version). Nothing is posted before approval.
- **confirm_posting**: after approval the graph pauses again and asks
  "Post this job to the job board?" with **Post to job board** and
  **Don't post**. Don't post keeps the JD approved (job list: "Approved ·
  not posted"); the interviewer can ask in the chat to post it later.
- **post_to_job_board**: runs only after the interviewer chose Post. Posts the approved JD
  and the form link to the job board (see below) and adds the result to
  the chat. If the form link is missing, it asks for it first; if the
  job board fails after 3 tries, the chat shows **Try again** and
  **Copy job description**.
- **Retry path**: a tool call with invalid arguments goes back to the LLM
  as an error so it can correct itself; a turn that never ends is stopped
  after 30 steps with a clear message; "Try again" continues a turn that
  failed without sending the message twice.

## Job board (Blogger)

Approved JDs are posted to a **private Blogger blog** (free, no paid API),
through our own small MCP server in `jobboard-mcp/`:

```
backend --MCP (create_job_post)--> jobboard-mcp --HTTPS--> Blogger API v3
```

The backend only knows the MCP address; the Google credentials stay in
the `jobboard-mcp` container. Without them the app still works and the
chat says "The job board is not set up yet".

**One-time setup** (about 10 minutes, with your own Google account):

1. **Blog:** on <https://www.blogger.com> create a blog, then
   *Settings → Permissions → Reader access → Private* (only you can read
   it; it is a demo job board). The **blog ID** is the number in the
   address bar of the blog's dashboard (`.../blog/posts/<blog ID>`).
2. **Google Cloud project:** on <https://console.cloud.google.com> create
   a project and enable **Blogger API v3** (*APIs & Services → Library*).
3. **OAuth consent screen:** user type *External*, status *Testing*, and
   add your own Google account as a test user.
4. **OAuth client:** *Credentials → Create credentials → OAuth client ID*,
   type **Desktop app**. Keep the client ID and secret private.
5. **Refresh token** (on your computer, not in Docker):

   ```bash
   cd jobboard-mcp
   python -m venv .venv
   .venv\Scripts\activate            # Windows (source .venv/bin/activate on macOS/Linux)
   pip install -r requirements-dev.txt
   python get_refresh_token.py <client ID> <client secret>
   ```

   A browser opens; sign in with the same account and allow access. The
   script prints `BLOGGER_REFRESH_TOKEN=...`.
6. Put the four values in `.env` (never in code or chat):
   `BLOGGER_CLIENT_ID`, `BLOGGER_CLIENT_SECRET`, `BLOGGER_REFRESH_TOKEN`,
   `BLOGGER_BLOG_ID`. Then restart: `docker compose up -d`.

Sign in with the Google account that **owns the blog** (add it as a test
user first). While the consent screen is in *Testing*, Google ends the
refresh token after 7 days: the chat then says "The job board sign-in
failed"; run step 5 again and replace the token (do it before a demo).

The token only allows managing your Blogger blogs. To revoke it, remove
CandiVue at <https://myaccount.google.com/permissions>.

## Video calls (interviews)

Interviews are 1-on-1 video calls in the browser, using **LiveKit**, an
open-source video server that runs here in Docker (no cloud, no account).

```
Interviewer (signed in): Interviews → "Join now" ─┐
Candidate: private link → welcome → camera check ──┤ ticket from the backend
                                                   ▼ (this room only)
             browser ⇄ LiveKit (Docker) ⇄ browser   video + audio, encrypted
                         │ signed webhooks
                         ▼
             backend: Live + start time, who joined; End session → Ended
```

- The backend gives each person a **ticket** (a signed LiveKit token) for
  their interview's room only: the interviewer after signing in, the
  candidate after opening their private link. Camera and microphone only.
- **Join any time** once the invitation email was sent, until the
  interviewer clicks **End session** (or the interview is cancelled). The
  email is the only way the candidate gets their link; before it is sent
  nobody can join. Ending closes the call for everyone and the candidate's
  link stops working.
- **Reconnect:** LiveKit reconnects a dropped connection by itself (the
  bar shows "Reconnecting…"); a reloaded candidate tab goes straight back
  into the call.
- The candidate sees only the call: no transcript, scores or assistant.
- Video and audio are not recorded or stored (N16).

Setup: `LIVEKIT_API_SECRET` in `.env` (32+ random characters, see
`.env.example`); it signs the tickets and LiveKit's webhooks.

**Try it on one computer:** sign in, open **Interviews → Join now**; open the
candidate's link from the invitation email (with `EMAIL_TEST_RECIPIENT` it
comes to you) in a second window of the **same browser** (a private window
works), so both tabs can use the camera. Use a headset,
or mute the tab that is not speaking, to avoid echo.

**From a phone or a second computer on the same network:** set
`LIVEKIT_NODE_IP` and `LIVEKIT_BIND_ADDRESS` in `.env` to this computer's
network address (e.g. `192.168.1.20`) and use HTTPS for the app (see
*Transport security*: phones only allow the camera on HTTPS).

## Email (interview invitations)

When the interviewer confirms interviews in the Hiring Assistant, each
candidate is emailed a private link (moved interviews get a new one). The
text comes from the knowledge base's **Email templates** collection (RAG):
a template needs a `Subject:` line and may use `{candidate_name}`,
`{job_title}`, `{date}`, `{time}`, `{time_zone}`, `{duration}` and
`{interview_link}`; `- **Label:** value` lines become a details table and
the link a "Join your interview" button (see
`test-data/knowledge-base/email-templates/`). Each email has an HTML and a
plain-text part, and an **invite.ics** calendar invite, so the interview
appears in the candidate's calendar app; a moved interview updates the
same event. A cancelled interview sends a short fixed "Interview
cancelled" email whose invite removes the event (only to candidates who
were sent the invitation). Without a template, a short standard text is
used. The confirmation card shows a preview first.

```
backend --MCP (send_email)--> email-mcp --SMTP over TLS--> Gmail
```

Setup (once):

1. Use a Gmail account with **2-Step Verification** on
   (<https://myaccount.google.com/security>).
2. Create an **app password** at <https://myaccount.google.com/apppasswords>
   (name it "CandiVue"); Google shows 16 letters once.
3. In `.env`: `SMTP_USER` = that Gmail address, `SMTP_PASSWORD` = the app
   password (no spaces), and `EMAIL_TEST_RECIPIENT` = your own address.
4. `docker compose up -d --build`

Keep `EMAIL_TEST_RECIPIENT` set: every email then goes to you, with
"[Test for <candidate address>]" in the subject, so no real person is
mailed (N13). An email that fails never loses the interview: it shows
"Invitation failed" and can be sent again on the Interviews page. To
revoke access, delete the app password.

## Calendar (Google Calendar)

The interviewer's Google Calendar is used in two ways (§4B-8), through our
own small MCP server in `calendar-mcp/`:

```
backend --MCP (list_busy, create_event, move_event, delete_event)--> calendar-mcp --HTTPS--> Google Calendar API
```

- **Before:** free times (`find_free_slots`) and proposed times skip the
  interviewer's busy events as well as their CandiVue interviews. A clash
  is a problem the assistant must fix; all-day events and events marked
  "free" do not count. The confirmation card says "Free in your calendar".
- **After Confirm:** each interview is added to the calendar as an event
  (no guests, so Google never emails the candidate), moved when it is
  rescheduled and deleted when it is cancelled. Resend on the Interviews
  page adds it if it is still missing.

If the calendar is not set up or not reachable, nothing is blocked:
times are checked against CandiVue interviews only, with a warning, and
the results card says "Calendar not updated: <reason>".

**One-time setup** (reuses the Google Cloud project and OAuth client from
"Job board (Blogger)"):

1. In that project, enable **Google Calendar API** (*APIs & Services →
   Library*). If the calendar belongs to another Google account, add it as
   a test user on the OAuth consent screen.
2. Refresh token (on your computer, not in Docker):

   ```bash
   cd calendar-mcp
   python -m venv .venv
   .venv\Scripts\activate            # Windows (source .venv/bin/activate on macOS/Linux)
   pip install -r requirements-dev.txt
   python get_refresh_token.py <client ID> <client secret>
   ```

   Sign in with the interviewer's Google account and allow access. The
   script prints `CALENDAR_REFRESH_TOKEN=...`.
3. Put `CALENDAR_CLIENT_ID`, `CALENDAR_CLIENT_SECRET` (the same client as
   Blogger is fine) and `CALENDAR_REFRESH_TOKEN` in `.env`;
   `CALENDAR_ID=primary` is the account's main calendar. Then
   `docker compose up -d --build`.

The token only allows managing calendar events (scope
`calendar.events`). As with Blogger, a consent screen in *Testing* ends
the token after 7 days: run step 2 again before a demo. To revoke it,
remove CandiVue at <https://myaccount.google.com/permissions>.

## CV Collector (Google Drive)

Applicants apply through the Google Form linked in the job post (§4B-9):

```
Google Form ─► Drive (CV file) + response Sheet (name, email, job, CV link)
                     │  read-only service account
   cv-collector (every 5 min) ─► cv_intake volume: job-<id>/<candidate>.pdf|docx
                              └► candidates table: received / rejected + reason
```

- **Which job?** The job post opens the form with "Position applied for"
  already filled in, e.g. `JOB-12 · Python Developer`
  (`GOOGLE_FORM_POSITION_FIELD`). Answers without a job reference, without
  consent or without a CV are skipped; a CV already collected is never
  downloaded again.
- **Checks (N8):** PDF or Word (DOCX) only, decided by the file's content,
  and at most `MAX_CV_MB` (checked before downloading). A rejected file is
  not saved; the reason is recorded. One bad answer never stops the others.
- **Storage:** the files are in the `cv_intake` named volume (never in the
  project folder or git, N14); only the data about them is in PostgreSQL.
  Look at them in Docker Desktop → Volumes → `candivue_cv_intake`.
- The Jobs page shows **CVs received**. Clicking a job opens its page with
  the **applicants**: name, email, when the CV arrived, file name and status
  (received / rejected with the reason), **View CV** (PDF opens in the
  browser, Word downloads; never cached) and **Remove** (deletes the
  applicant and the CV file, N19). API (interviewers only):
  `GET /api/jobs/{id}/cvs`, `GET /api/jobs/{id}/cvs/{candidate}/file`,
  `DELETE /api/jobs/{id}/cvs/{candidate}`.
- **Add CV (by hand):** for a CV received another way, or to load a set of
  sample CVs, use **Add CV** on the job page (one or several PDF/DOCX files;
  same checks; sent one file per request; shown as "Added by hand"; the name
  is guessed from the file name until screening reads the CV).
  API: `POST /api/jobs/{id}/cvs` (multipart `files`, at most 30 per request).
  nginx accepts requests up to 25 MB (`client_max_body_size`).
- **Synthetic test CVs:** `test-data/synthetic-cvs/` holds 20 made-up CVs for
  the "PHP Laravel Developer" test job (strong, partial, excluded and edge
  cases: scanned, DOCX, two-column, missing sections) and an answer key in
  `EXPECTED.md`. Re-create them with `python test-data/synthetic-cvs/make_cvs.py`.
- Without the settings below, the collector waits and logs "not set up yet".

**One-time setup** (same Google Cloud project as the job board):

1. **APIs:** *APIs & Services → Library*: enable **Google Drive API** and
   **Google Sheets API**.
2. **Service account:** *IAM & Admin → Service accounts → Create service
   account*, name `cv-collector`, **no roles**. Open it → *Keys → Add key →
   Create new key → JSON*. Keep the downloaded file outside the project.
3. **Share, read-only:** with the account that owns the form, share the
   form's upload folder in Google Drive (`<form title> (File responses)`)
   and the response Sheet with the service account's email
   (`cv-collector@<project>.iam.gserviceaccount.com`) as **Viewer**.
4. **`.env`:**
   - `GOOGLE_SERVICE_ACCOUNT_KEY`: the key on one line, e.g. in Git Bash
     `base64 -w0 <key file>.json`. Then delete the downloaded key file.
   - `CV_RESPONSES_SHEET_ID`: from the Sheet's address `/spreadsheets/d/<ID>/edit`.
   - `GOOGLE_FORM_POSITION_FIELD`: in the form, *⋮ → Get pre-filled link*,
     type anything in "Position applied for", *Get link*; the link contains
     `entry.<number>=…`; use `entry.<number>`. Give that question the help
     text "Filled in automatically, please don't change".
5. `docker compose up -d`, then `docker compose logs -f cv-collector`.
   Post the job again so its link pre-fills the job.

Use only sample or synthetic CVs (N13, CN5).

## CV screening (LangGraph 2)

A fixed workflow (Figure 4), started with **Screen CVs** on the job page,
not by the chatbot, so scores stay repeatable. It screens all of the job's
CVs in one batch, one parallel branch per CV, in the background with
progress ("12 of 20 CVs"). It is checkpointed, so after a restart it
continues where it stopped (N26). **No Gemini is used**: everything runs
locally, so there is no quota and CV text stays on this machine. Mostly
rules and local embeddings; a small **local model** (Ollama,
`SCREENING_MODEL`, default `qwen3:4b-instruct`, about 2.5 GB) is asked only
in the two cases the rules cannot settle (see below).

```
load_cv_batch → Send (one branch per CV):
  extract_text ─ no text → ocr_extract (Tesseract) ─┐
       │ text ───────────────────────────────────────┴→ parse_cv
       └ error → log_and_skip                           │ error → log_and_skip
  check_hard_requirements ─ fail → record_exclusion
       └ pass → match_requirements → score_skills ║ score_experience ║
                score_qualifications ║ ats_match → combine_scores
→ collect_results → rank_candidates → save_results
```

- **Reading:** the file's text (PDF or Word); a PDF without text is read
  by OCR (local Tesseract). A CV that still cannot be read is listed as
  "could not be read"; the batch goes on.
- **Parsing (rules):** contact details, sections, jobs with dates, years
  of experience (overlapping jobs counted once), highest degree,
  certificates. Ligatures ("ﬁ") are normalised; two-column CVs are handled.
  Dates such as "Jan 2020 – Present", "Jan 2020 – Till Date", "Feb 2019 to
  date", "03/2022 – now", "01.2018 – 12.2019", "Jan, 2015 – Mar, 2016",
  "2017 through 2018", "March 2019 until today" and "since 2014".
  "Master" counts as a degree only as "Master of / Master's in" (not
  "Scrum Master").
- **Years without dates (local model):** when the rules find no job dates,
  the local model reads the years the CV shows ("7 years of experience",
  "over five years"). It must quote the CV lines it used; a rule checks the
  quotes are really in the CV and the number comes from them. If nothing is
  found, the years are **unknown**: the candidate is **not excluded** for
  years, the experience score is 0 and the screen shows a "please check"
  warning.
- **Matching:** each requirement is **met** when the CV names it or one of
  its "also counts" names; **partly met** through a "related" name; else
  the CV line closest in meaning (local embeddings, cosine similarity)
  decides: met ≥ 0.62, partly ≥ 0.58 (calibrated on the synthetic CVs).
  A line that says the opposite ("has not used Laravel", "no experience
  with Docker") or only a wish ("interested in learning Docker") never
  counts; "no manual steps using Docker" still counts. A version number
  does not hide a name ("PHP8" counts for PHP). Every result keeps the CV
  line as evidence.
- **Second look before excluding (local model):** when a mandatory
  requirement is still not found (and the years are not too few anyway),
  the local model reads the CV once more. It counts only with a quoted line
  that is really in the CV and does not deny the skill; the panel then says
  the local model found it. This protects against excluding a good
  candidate because the rules missed a wording.
- **Hard-requirement gate:** a candidate is **excluded** (not ranked, with
  the reason) when a mandatory requirement is not met, is only "partly met
  by meaning", or the years are below the minimum (unknown years never
  exclude).
- **Scores (0-100, rules, each with a written reason):** technical skills
  (requirements weighted mandatory 3 / required 2 / preferred 1), relevant
  experience (minimum + 3 years = full marks), qualifications (degree 60%,
  qualification requirements 40%), ATS CV-JD match (key job terms found
  60%, closeness of the whole CV to the JD 40%).
- **Weights (human control):** the interviewer's weights on the job page
  win; otherwise the Hiring Assistant's suggestion; otherwise defaults
  (skills 35, experience 30, qualifications 15, ATS 20). Each run records
  the weights it used; the page says when weights or CVs changed since.
- **Results** (interviewers only, N9): ranking (overall score first), a
  candidate panel with the score breakdown and each requirement's evidence,
  excluded candidates with reasons, unreadable CVs.
- API: `POST /api/jobs/{id}/screenings`, `GET /api/jobs/{id}/screenings/latest`,
  `PUT /api/jobs/{id}/weights`, `DELETE /api/jobs/{id}/weights`.

**Measured time (N1), 22 synthetic CVs, this laptop (CPU only):** about
**5 minutes** for the first run (reading, OCR, embedding every CV line, and
4 local-model questions: one CV without dates, three second looks; the
first question also loads the model, about 40 s) and about **7 seconds**
for a repeat run (parsed CVs, embeddings and the local model's answers are
reused, e.g. after changing the weights). One local-model question takes
about 6-16 s.

**Checked against** `test-data/synthetic-cvs/EXPECTED.md`: the 5 expected
candidates are excluded with the right reasons, the strong CVs rank on top,
"Laravel Sail" counts for Docker and "Podman" gives partly met, the CV
without dates gets its stated 7 years, and the "Till Date" CV is read
correctly. A fresh run and a repeat run give the same ranking.

**Known limitations (fairness and accuracy, N20):**
- Only job-related data is scored; no age, gender, nationality or other
  protected attribute is read or stored. Names and emails are shown but
  not scored.
- Years of experience count the whole career, not years per skill.
- "Present" means the screening date, so the same CV gains experience over
  time.
- The "also counts" / "related" lists come from the AI when the profile is
  saved; check them, since a missing name can make a skill look unmet.
- Similarity thresholds were calibrated on synthetic CVs; unusual CV
  layouts can lose lines. Scanned CVs are marked so they can be checked.
- The local model is small: its answers are only used with a quote that
  is checked against the CV, but it can still miss a wording (then the
  result is the same as the rules alone). Years it computes from unusual
  dates are checked for plausibility, not exactly.
- English CVs only (OCR and rules are set up for English).
- Scores support the interviewer's decision; nothing is rejected or hired
  automatically.

## Knowledge base (RAG)

Documents the Hiring Assistant can search: reference library, company
policies, previous job profiles, email templates and the interview
question bank.

- Upload PDF, DOCX, TXT or Markdown (up to `MAX_UPLOAD_MB`). The type is
  checked from the file's content, not its name.
- Only the extracted text is stored, cut into overlapping passages; the
  file itself is not kept.
- Each passage gets an embedding (1024 numbers, stored with pgvector),
  made by `qwen3-embedding:0.6b` running locally in the `ollama` container
  (CPU is enough). The model (about 640 MB) is downloaded automatically on
  the first start and kept in the `ollama_models` volume.
  Search compares the question's embedding with the passages (cosine
  similarity) and returns the closest ones with a match score.
- Indexing runs in the background with a visible status; a failed
  document can be indexed again.
- Never upload CVs, interview notes or other personal data here.

## Secure by design

Security is built into each part instead of added at the end:

- **Deny by default:** every API route requires the interviewer role
  unless it is on a short, explicit list; a test fails if a new route
  forgets the check (`tests/test_auth_routes.py`).
- **Validate all input:** request bodies have length limits (Pydantic);
  uploads are checked by size and real file type; file names are cleaned.
- **Least data:** uploaded files are not kept, only their text; no
  candidate data in the knowledge base.
- **AI output is checked:** the profile and JD the LLM writes must match
  fixed shapes before they are saved; the job id is set by the graph, not
  by the LLM.
- **Prompt-injection care:** document text and chat messages are passed
  to the LLM as data, and the instructions say never to follow
  instructions found inside them.
- **Human approval:** nothing is published before the interviewer
  approves it.
- **CV files:** only `cv-collector` holds the Google key (a service
  account that can only read the shared folder and Sheet). Files are
  checked by content and size before they are saved; logs never contain
  applicants' names or emails.
- **Least privilege for integrations:** only `jobboard-mcp` holds the
  Blogger credentials (one OAuth scope: Blogger) and only `email-mcp` the
  email login; the backend cannot use them directly. Emails are plain
  text to one checked address. The posted page escapes all JD text, and only Google
  Forms links (HTTPS) are accepted as the application link.
- **No secrets or personal data in logs or error messages**, pinned and
  audited dependencies, localhost-only ports (see the sections above).

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
| Interview audio and video (WebRTC through LiveKit) | Always encrypted (DTLS-SRTP) between each browser and the LiveKit container. Its ports are bound to `127.0.0.1` unless `LIVEKIT_BIND_ADDRESS` is set for another device. |

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

Job board MCP server tests (Blogger is replaced by a fake, no
credentials needed):

```bash
docker compose run --rm --build jobboard-tests
```

Email MCP server tests (a fake SMTP server, no email is sent):

```bash
docker compose run --rm --build email-tests
```

Calendar MCP server tests (a fake Google Calendar, no event is made):

```bash
docker compose run --rm --build calendar-tests
```

Frontend tests (no backend needed; requires Node.js 22.22 or later):

```bash
cd frontend
npm install
npm test
```
