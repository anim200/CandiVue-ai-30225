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
- Screening runs and interview analyses show progress, e.g. 12 of 20 CVs,
  4 of 7 Q&A units.
- An AI failure shows its own plain message, e.g. which model reached its
  daily limit and what to do; "Try again" continues from the last finished
  step (finished CVs or Q&A units are not sent to the AI again).
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
| Charts | Mantine Charts (Recharts) | Same look and colours as the other Mantine parts, light and dark. |

How it runs:

- **Start page:** after sign-in the interviewer sees *Home*: counts (open
  jobs, applications this week, CVs to screen, interviews today, reports to
  review, selected this month), "Needs you" (live interviews, interviews
  today, reports to review, jobs with CVs to screen, jobs waiting in the
  chat), the next interviews and applications per day for the last 14 days,
  all from `GET /api/dashboard` (interviewer only). The job page shows the
  screening as a *Ranking* (with a score distribution chart) or as a
  read-only *Pipeline* (Screened → Shortlisted → Invited → Interviewed →
  Selected); the report and the comparison show the interview dimensions
  as a radar chart.
- **Light or dark:** *Appearance* in the user menu (and a sun/moon button
  on the login and candidate pages). The choice is remembered in the browser
  and all its tabs follow it; the default is light. All colours of our own
  CSS are tokens in `frontend/src/styles/tokens.css` (a light and a dark
  value each); emails and the printed report always stay light.
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
| `cv-collector` | built from `backend/Dockerfile` (target `runtime`), command `python -m app.collector` | Copies new CVs from the Google Form into the `cv_intake` volume every few minutes, and processes the face photos of newly invited applicants (F7, encrypted). The only service that holds the Google key (read-only). No ports. |
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
  - Hiring Assistant in the interview room: the interviewer's messages,
    the job's requirements, question-bank passages found by search, and,
    only when the interviewer asks for questions from the CV, a **reduced
    CV summary**: job titles with dates, years, skills, degree level,
    certificates and how each requirement was met in screening. No name,
    email, phone number, address or links (they are removed first).
  - CV screening: nothing (it runs locally, see "CV screening").
  - Interview analysis (F5, F8-F10): the job title and requirements, the
    interview transcript with **names, email addresses, phone numbers and
    links removed**, the knowledge-base passages found for each answer
    (Reference library, Company policies) and, for the CV claims check,
    the reduced CV facts (as above).
  - Identity check (F7): **nothing**. Faces are compared locally (see
    "Identity check").
  - Assessment report (F6): the same transcript lines, the reduced CV facts
    (as above), the CV screening scores and reasons, the Q&A evaluations,
    and the interviewer's comment when they request changes.

Other external services (N18):

| Service | What it receives |
|---|---|
| Deepgram, through the `transcriber` | The interview audio of both people while the interview is live (streamed, not stored by CandiVue; `mip_opt_out=true` asks Deepgram not to use it for training). It returns the text. |
| Blogger (Google), through `jobboard-mcp` | The approved job description (title, text, requirements) and the Google Form link. No candidate data. |
| Gmail (Google), through `email-mcp` | The candidate's one-time access code (their email address, the job title and the code). Interview invitations and cancellations: the candidate's name and email address, the job title, the interview date and time, and the private interview link (also in the attached calendar invite). While `EMAIL_TEST_RECIPIENT` is set, every email goes to that test address instead. |
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
requests; an interview's analysis and report need about 4 (see "AI usage").

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
backend --MCP (create_job_post, update_job_post, delete_job_post)--> jobboard-mcp --HTTPS--> Blogger API v3
```

Deleting a job in CandiVue also removes its post (`delete_job_post`; a
post that is already gone counts as removed). If the blog cannot be
reached, the job is still deleted and a message asks you to delete the
post on the blog yourself.

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
Interviewer (signed in): Interviews → "Join now" ──────────────┐
Candidate: private link → waiting room (preview, devices) ─────┤
           heartbeat "I'm waiting" ──► interviewer sees        │
           "… is waiting · Let in" ──► Let in ──► ticket ──────┤ (this room only)
                                                               ▼
                     browser ⇄ LiveKit (Docker) ⇄ browser   video, audio, screen
                                 │ signed webhooks
                                 ▼
             backend: Live + start time, who joined; End interview → Ended
```

- **Waiting room:** the candidate checks camera and microphone (preview,
  level meter, device choice), ticks a notice ("not recorded, a written
  transcript is kept") and joins the waiting room. They get a call ticket
  only after the interviewer clicks **Let in** (checked by the backend,
  not only on the page). Each open page sends a heartbeat every few
  seconds, so the candidate sees whether the interviewer is there, and the
  interviewer gets a banner, a soft chime and "● Waiting" in the tab title.
  Once let in, a dropped connection or a reload goes straight back in.
- The backend gives each person a **ticket** (a signed LiveKit token) for
  their interview's room only. Browsers cannot send data into the room;
  chat goes through the backend.
- **Join any time** once the invitation email was sent, until the
  interviewer clicks **End interview** (or the interview is cancelled).
  The email is the only way the candidate gets their link. Ending closes
  the call for everyone and the candidate's link stops working. Leaving
  the room page without ending keeps the interview live.
- **The call:** the stage fills its column (16:9 when there is room, wider
  on short screens); the other person's video stays whole and sharp, with
  a blurred copy of it filling the sides; the controls float over its
  bottom edge (under it on phones); full screen from the icon in its
  top-right corner; a ring shows who is speaking; mute, camera,
  **screen sharing** (both sides; desktop browsers) and End/Leave. A shared
  screen fills the stage and the cameras move to a strip.
- **Interviewer's room:** the candidate's CV on the left (rank, overall
  and four scores, each requirement with the CV line that showed it,
  roles, degree, certificates, skills, the PDF inside the page), the call
  with the live transcript under it, and on the right the Hiring Assistant
  (only the interviewer sees it) and the chat with the candidate.
- **Chat:** plain text, at most 1,000 characters, 20 messages a minute per
  side; saved (table `interview_messages`, deleted with the interview) and
  pushed to both pages by LiveKit, with a check every few seconds as a
  fallback. Links open in a new tab.
- **Hiring Assistant in the room (§4B-10):** LangGraph 1 with its own
  thread per interview (`assistant-interview-<id>`), so a job chat waiting
  for a confirmation never blocks it and it can be prepared before the
  call. Quick actions: from the CV, from the question bank, check gaps,
  warm-up. Questions from the CV are made once per interview and saved
  (asking again costs no AI request; "Make a new set" makes another).
  Without a question bank (knowledge base, Question bank collection) the
  assistant says so and suggests its own questions. The AI model can be
  switched under its chat.
- The candidate sees only the call, the chat and the interview details:
  never the transcript, scores, CV panel, identity check or assistant
  (N9, checked by the backend).
- **Edge cases handled:** opened in a second tab ("Use this tab"), camera or
  microphone blocked or busy, screen sharing cancelled or not supported
  (phones), interviewer leaves without ending, interview ended or
  cancelled while waiting, reconnecting, long interviews (timer h:mm:ss,
  "+2 h 05 min over" the planned length, and a hint to end an interview
  left live for over 3 hours).
- Video, audio and shared screens are not recorded or stored (N16).

Setup: `LIVEKIT_API_SECRET` in `.env` (32+ random characters, see
`.env.example`); it signs the tickets and LiveKit's webhooks.

**Try it on one computer:** sign in, open **Interviews → Join now**; open the
candidate's link from the invitation email (with `EMAIL_TEST_RECIPIENT` it
comes to you) in a second window of the **same browser** (a private window
works), so both tabs can use the camera. Join the waiting room as the
candidate, then click **Let in** in the interviewer's tab. Use a headset,
or mute the tab that is not speaking, to avoid echo.

**From a phone or a second computer on the same network:** set
`LIVEKIT_NODE_IP` and `LIVEKIT_BIND_ADDRESS` in `.env` to this computer's
network address (e.g. `192.168.1.20`) and use HTTPS for the app (see
*Transport security*: phones only allow the camera on HTTPS).

## Live transcript (speech-to-text, F4)

While an interview is live, the **transcriber** container listens to the
call and writes a speaker-attributed, timestamped transcript. Speech-to-text
is done by **Deepgram** (Nova-3, English), streamed over a WebSocket.

```
browser ⇄ LiveKit ⇄ transcriber (hidden, listen-only participant)
                       │ one audio stream per person (16 kHz)
                       ▼
                   Deepgram ──► final pieces of speech ──► transcript_turns
                                                              │ every 1.5 s
                         interviewer's room: Live transcript ◄┘
```

- **Speaker attribution:** each person's microphone is its own stream, so
  the speaker is known from the track (interviewer or candidate); no
  guessing from mixed audio. Both talking at once gives two overlapping
  turns.
- **Turns:** what one person says until they pause (1.2 s or more between
  words, from Deepgram's word times, or Deepgram's "utterance end"). A turn
  is saved with its first words and grows while the person speaks, so a
  long answer appears live; times are milliseconds from the start of the
  interview. Very long answers are split every 45 s. A choppy connection
  does not chop a sentence into one-word lines.
- **Where to read it:** a compact card under the call, and a full-height
  **Transcript** tab beside it (larger text, the speaker and time once per
  run of their lines, Copy the whole transcript). The card's expand icon
  opens the tab; while the tab is open the card hides, so the video is
  larger.
- **Nothing is lost:** each turn is saved at once. If Deepgram or the
  network drops, the stream reconnects (a few seconds may be missing); a
  person who reconnects gets a new stream; a restarted transcriber joins
  the live interviews again. When the interview ends, the last words are
  fetched and saved before it leaves.
- **Status in the room:** Listening, Starting…, Not running (the
  transcriber is down), or the problem (e.g. "Deepgram refused the API
  key", "no credit left"), and "paused while the call reconnects".
- **Technical words:** the job's requirement names (e.g. Laravel, Docker)
  are sent to Deepgram as key terms (Nova-3 "keyterm prompting"), so they
  are recognised more reliably. Only job words, nothing about the candidate.
- The transcriber checks every 2 s for live calls and joins only while the
  interviewer or the candidate is in the call (the first 2-3 seconds of a
  call can be missed); it leaves a room nobody has been in for 2 minutes.
- **Measured** (two browsers, synthetic speech, this laptop): words appear
  about 1-2 s after they are spoken; speakers always right; a 15 s mute
  keeps the stream open; a reload continues with the new microphone; all
  turns kept after the end. Times are accurate to about a second.
- **Privacy:** audio is streamed to Deepgram and kept in memory only, never
  stored (N16); Deepgram is asked not to use it for training
  (`mip_opt_out=true`). The transcript is interviewer-only: candidates
  get 403 (N9).
- API: `GET /api/interviews/{id}/transcript?since=<time>` (turns new or
  changed since then, plus the status).

Setup: create an API key at deepgram.com and put it in `.env` as
`DEEPGRAM_API_KEY`; `docker compose up -d`. Only the `transcriber`
container receives it. It shares LiveKit's network (`network_mode`), because
LiveKit tells participants to send media to 127.0.0.1.

## Interview analysis and assessment report (LangGraphs 3 and 4)

When the interviewer ends an interview, two fixed workflows run in the
background, one after the other; the report is usually ready to review
within a minute. Nothing is shown to the candidate (N9: interviewer-only
routes, candidates get 403).

**Q&A analysis (F5, F8-F10, LangGraph 3, `backend/app/graphs/qa_analysis.py`).**

- Waits a few seconds for the transcriber's last words, then **one AI
  request** splits the transcript into question–answer units. Multi-part
  questions become `Q6a` / `Q6b`, follow-ups are linked to the question they
  follow. The LLM only points at numbered transcript lines; the code checks
  every number (it must exist and come from the right person).
- Greetings, small talk and unanswered questions are kept but not scored.
- **Accuracy is checked against documents (RAG, local, no AI request):** job
  answers against the knowledge base's *Reference library*, company answers
  against *Company policies* (user decision 17-10-2026, `docs/requirement.md`
  §4B-5). Passages scoring below 0.5 are ignored (measured: on-topic
  0.6-0.7, off-topic under 0.25). Without a matching passage the answer is
  marked "not checked against a reference document".
- **One AI request scores a batch of up to 20 answers** (a typical interview
  is one batch): relevance, accuracy, completeness and articulation, 0-100
  with a reason each and the transcript lines it rests on. An answer the AI
  skips is shown as not scored ("use Analyse again"), never invented.
- Requirement coverage (which units explored each job requirement) and the
  requirements never explored are computed in code.
- **One more AI request reviews the whole interview** (`app/analysis/review.py`):
  - **CV claims check (F8):** important CV claims, each *supported*,
    *contradiction*, *unverified* (came up, no concrete detail) or *never
    discussed*, with what the interview showed and a neutral follow-up
    question. A claim must point to a real CV item; every result except
    "never discussed" must cite the candidate's own lines, otherwise it is
    shown as never discussed. Flags are prompts for a person, never
    accusations, and change no score.
  - **Two judgement dimensions for F9:** problem-solving approach and
    experience depth, each with the candidate's lines as evidence (without
    evidence: "not enough evidence", left out of the average).
  - **For F10:** questions that gave little evidence (yes/no, leading, too
    broad, off-topic) and up to three suggestions for the interviewer.
- **Interview score (F9, `app/analysis/interview_score.py`, plain code):**
  six dimensions with evidence, separate from the CV score. Technical
  competency (accuracy of the job answers), communication (articulation),
  response relevance, job alignment (best answer per explored
  requirement), plus the two judged ones. The overall interview score is
  their average.
- **Interview quality (F10, `app/analysis/interview_quality.py`, plain code):**
  the interview as evidence, not the candidate. *Poor* when fewer than 3 job
  questions were answered, less than half of the mandatory requirements
  were explored, or the interviewer did more than 75% of the talking;
  *needs attention* when a mandatory requirement was not explored, the
  interviewer talked more than 60%, or two questions gave little evidence;
  otherwise *good*. The page also compares the interview with the job's
  other analysed interviews (answered questions, requirements explored,
  requirements usually explored but not here). A poor interview offers
  **Reschedule with Hiring Assistant**: the job's chat opens with the
  request filled in; the interviewer checks and sends it, and the
  assistant invites the candidate again (`invite_again`) after the usual
  confirmation (trainer clarification: a poor interview is not enough
  evidence).

**Assessment report (F6, LangGraph 4, `backend/app/graphs/final_assessment.py`).**

- Component scores are computed in code: the CV screening score and its
  dimensions (F2), the interview score with its six dimensions (F9), and
  the requirement coverage. The overall position is the average of the CV
  and interview scores on a 4-step scale (Not yet suitable < 50 ≤ Partial
  fit < 65 ≤ Good fit < 80 ≤ Strong fit). Without scored answers the
  headline says it rests on the CV alone. It is a summary for a person,
  never a decision.
- **One AI request** writes the four lists: strengths, weaknesses, evidence
  gaps and areas to verify. Every conclusion must cite evidence ids: CV
  items (`CV3`), transcript lines (`T12`) or a requirement's coverage record
  (`R2`, for what was never discussed). Ids are checked; a conclusion
  without valid evidence is sent back for repair (at most twice, rarely
  needed) and then shown as unsupported.
- The report also shows the CV claims to follow up (F8, with their
  transcript sources), the interview quality (F10) and the identity check
  (F7), copied from the analysis and the interview: no extra AI request.
- **Review (HITL):** the report waits for the interviewer. *Approve* makes
  it final; *Request changes* with a comment writes the next version with
  that comment in one request, which also says what changed, and waits
  again.
- **Export:** "Export / print" downloads one self-contained HTML file or
  prints it (the print dialog also saves it as PDF). Drafts are marked "Not
  yet approved" on every page; sources become numbered references.
- **Compare candidates:** up to three assessed candidates of the same job
  side by side (CV and interview scores, claims to follow up, interview
  quality, identity).

| Page | Address |
|---|---|
| Interview analysis (Q&A analysis, transcript, CV claims check, interview score, interview quality, session details) | `/interviews/<id>/analysis` |
| Assessment report (report, compare candidates) | `/interviews/<id>/report` |
| Reports of a job | `/reports` |

API (interviewers only): `GET/POST /api/interviews/{id}/analysis`,
`GET/POST /api/interviews/{id}/report`, `POST /api/interviews/{id}/report/review`,
`GET /api/interviews/{id}/report/export`, `GET /api/jobs/{id}/reports`.
`POST` starts a run, continues a failed one, or with `{"again": true}`
replaces it (analysing again also replaces the report). Analyses made
before F8-F10 show "Analyse again" on those tabs.

## AI usage (Gemini free tier)

Every Gemini request counts against a small free daily quota, so the AI
work is batched and everything that can be worked out in code is (counts
come from the request log in the tests, `tests/test_post_interview.py`,
and a live run on 17-10-2026).

| Step | Before | Now | How |
|---|---|---|---|
| Split the transcript into Q&A units | 1 | 1 | unchanged |
| Score the answers (F5) | 1 per answer | 1 per 20 answers | all answers in one structured request |
| CV claims (F8), 2 judged dimensions (F9), interview advice (F10) | (+3 if built separately) | 1 | one review request for the whole interview |
| Interview score (F9), interview quality (F10), coverage | – | 0 | plain code from the evaluations and the transcript |
| Report: strengths, weaknesses, gaps, verify (F6) | 4 | 1 | one request returns the four lists |
| "What changed" on a revision | 1 | 0 | returned by the revision request itself |
| Hiring Assistant after "Post" / "Don't post" / confirming invitations | 1 each | 0 | the chat card already shows the result |

**Per interview** (a 45-minute interview has about 12 answers):
before `1 + 12 + 4 = 17` requests (`20` with F8-F10 as separate requests),
now `1 + 1 + 1 + 1 = 4` (a repair adds 1, rarely). Each report revision:
before `4 + 1 = 5`, now `1`. Measured live: interview 102 (5 answers) took
exactly 4 requests for analysis and report (35 s).

**What fits in a day:** with a daily quota of `Q` requests, interviews per
day = `Q / 4` instead of `Q / 17`, about 4× as many. On the 20-request quota
measured for `gemini-3.5-flash`: 5 interviews instead of 1. Per-minute
limits are no longer a problem either: one analysis sends its requests one
after another instead of 4 at a time.

## Identity check (F7) and the candidate access code

**Access code.** Opening the interview link emails a one-time 6-digit code
to the address the candidate applied with; the link and the code together
open the interview (a forwarded link alone is not enough). The code works
once, for 10 minutes, with at most 5 wrong tries; a new one can be sent
after 60 seconds. Only an HMAC of it (keyed with `JWT_SECRET`) is stored. A
reload in the same tab keeps the candidate signed in. API:
`POST /api/auth/candidate` (sends the code), `POST /api/auth/candidate/verify`.

**Identity check (face only, §4B-15).** The reference is the photo the
applicant sends with the application, and the candidate checks in with
their camera before the interview (`app/identity/`):

1. **Application photo.** The Google Form has two optional questions: a
   photo of the applicant's face (file upload) and a separate tick box
   allowing its use at the interview (see "CV Collector"). The CV Collector
   records both but downloads the photo **only once the applicant is
   invited** (most applicants are never interviewed). It checks the file by
   content (JPEG, PNG, WebP, HEIC from iPhones; at most 10 MB), turns phone
   photos upright (EXIF) and looks for exactly one clear face. It keeps the
   face embedding (128 numbers) and a small copy of the photo (320 px,
   cropped around the face), both **encrypted** (Fernet,
   `FACE_REFERENCE_KEY`); never the original file. An unusable photo keeps
   only the reason (no face, more than one person, face too small,
   unreadable, too large); a failed download is tried again in later
   rounds. The Interviews page shows the photo state under each upcoming
   interview.
2. **Check-in.** After the emailed code the candidate agrees (or skips: no
   effect on the interview) and takes three camera pictures. Each must show
   exactly one face, large and light enough; otherwise they are told what
   to change ("only you in view", "move closer", "turn on a light") and try
   again, up to 10 times; then the check-in is recorded as failed and they
   continue. The pictures are compared with the application photo in
   memory and never stored. The candidate only sees "You're checked in".
3. **What the interviewer sees.** In the waiting-room banner (before "Let
   in") and at the top of the room's CV column: the **application photo**
   to compare with the video, and the check-in result with a **match
   score**:

   | State | When |
   |---|---|
   | Matches the application photo | the three pictures match (similarity ≥ `FACE_MATCH_FROM`, 0.363 = SFace's own same-person line, shown as 60 %) and none is clearly lower |
   | Not confirmed | in between: compare the photo with the video |
   | Different person | below `FACE_UNSURE_FROM` (0.28, shown as 40 %), or clearly closer to another invited applicant of the job (named) |
   | Check-in failed / skipped / not checked in / no comparison | with the reason (e.g. no photo sent, photo shows two people) |

   The match score is a fixed scale on the face similarity (0 → 0 %, 0.28 →
   40 %, 0.363 → 60 %, 0.70 and above → 100 %), so it reads at a glance; it
   is **not a probability**. The profile (name, headline experience, key
   skills, CV score and rank, areas to probe) shows only on a match. The
   report and the final ranking show the result too. There is no automatic
   check during the call (removed in §4B-15): the interviewer compares the
   photo with the video. Nothing is ever decided automatically.

- **Models:** OpenCV Model Zoo, run locally on the CPU (nothing leaves the
  machine): YuNet finds faces (MIT), SFace makes the embedding (Apache 2.0).
  Pinned by commit and SHA-256 in the backend Dockerfile.
- **Retention and deletion (N17, N19):** the embedding and the small copy
  are deleted 30 days after the applicant's last interview
  (`FACE_RETENTION_DAYS`; checked every hour), at once when all their
  interviews are cancelled or the candidate withdraws, and with the
  candidate or job. The **original photo stays in the form owner's Google
  Drive** (CandiVue's access is read-only): delete it there after the job.
- **Setup:** put a key in `.env` (see `.env.example`), add the two
  questions to the form, then `docker compose up -d --build backend
  cv-collector`. Without the key the check is off and candidates are not
  asked.
- **Limits:** the applicant chooses the photo, so the check shows that the
  person at the interview matches the photo sent with the application; it
  is not an ID-document check, and a real-time face-swap ("deepfake") is
  not detected. Tested with public-domain paintings as faces: the same
  painting matches (similarity 0.92, 100 %), another painting is named as
  the other applicant; never with real candidates' faces (N13).

API: candidates `POST/DELETE /api/candidate/identity` (check in / skip or
withdraw; they never see results); interviewers
`GET /api/interviews/{id}/identity` and `GET /api/interviews/{id}/identity/photo`.

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

**Selection email (§4B-14).** On an **approved** assessment report,
"Send selection email" opens the email to check: the text comes from an
Email templates document **without** `{interview_link}` (e.g.
`selection-congratulations.md`, placeholders `{candidate_name}` and
`{job_title}`), or a professional standard text. Subject and text can be
edited, **Preview** shows the email exactly as the candidate will see it,
and a confirmation step comes before sending; a warning shows when the
identity check did not confirm the candidate. It is sent through the same
email MCP (no button, no calendar invite, no offer details: HR sends the
offer outside CandiVue). The candidate is then shown as **Selected** in
the ranking and on the report, and cannot be emailed twice. It is never
sent automatically, and the route refuses it before the report is
approved (needs trainer approval: `docs/requirement.md` §14).

**Final ranking (§4B-15 f).** The Reports page starts with the job's
candidates whose report is **approved**, ranked by the overall score (the
average of the CV and interview scores, as in the report; on the same
overall score the higher interview score first; candidates equal on both
share a rank). Each row shows the CV and interview scores, the identity
check result and whether the candidate was selected. Tick two or three
candidates and **Compare** shows them side by side; **Send selection
email** opens the dialog above for the candidate you choose. Interviews
not ranked yet are listed with the reason (report being prepared, waiting
for your review, changes requested, earlier interview of the same
candidate). API: `GET /api/jobs/{job}/reports` (`rank`, `not_ranked`).

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
  downloaded again. The optional talent-pool question is recorded too
  (see "Innovation Feature (F11)").
- **Face photo (F7, optional):** two questions: a file upload titled
  **"Photo of your face"** (images only, 1 file, up to 10 MB) and a tick
  box titled **"Photo consent"** (e.g. "Photo consent: you may use my photo
  to confirm my identity at the interview"). The collector finds them by
  these words. It records the photo's Drive link and the consent (only
  together with a photo); the photo is downloaded only once the applicant
  is invited (see "Identity check (F7)").
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
- **Synthetic test CVs:** `test-data/synthetic-cvs/` holds 29 made-up CVs for
  the "PHP Laravel Developer" test job (strong, partial, excluded and edge
  cases: scanned, DOCX, two-column, missing sections; CV 29 for the
  talent-pool demo) and an answer key in `EXPECTED.md`. Re-create them with `python test-data/synthetic-cvs/make_cvs.py`.
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
CVs in one batch, one parallel branch per CV (at most 4 at a time: the
local models answer one request at a time, and more branches used up the
database connections; see docs/VERIFICATION.md), in the background with
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

## Innovation Feature (F11): Talent rediscovery

Good applicants who were not chosen for one job are usually never looked
at again, even when a later job fits them better. CandiVue keeps a
**talent pool** of applicants who agreed to be considered for other
vacancies, and suggests them when another job is screened.

```
Google Form: "Consider me for other vacancies" (optional, unticked)
   └► candidates.open_to_other_roles
"Screen CVs" on job B finishes ─► talent rediscovery run for job B
   load_pool ─ Send: screen_cv (LangGraph 2's own per-CV subgraph) per past application
            ─► collect_results ─► save_matches (passed the gate and overall ≥ 50)
Job B page: "Past applicants who may fit" ─► interviewer clicks "Add to this job"
   └► a copy of the application in job B (CV file, parsed CV, passages)
      ─► screen again, shortlist, invite as usual
```

- **Consent first:** only applicants who ticked the optional form question
  are in the pool (`open_to_other_roles`, default false). For CVs added by
  hand, the **Add CV** dialog asks whether the applicants agreed (unticked
  by default). The applicant row shows a **Talent pool** chip and a button
  to put someone in or take them out (e.g. when they ask to be left out).
- **Who is in the pool for a job** (`app/rediscovery/pool.py`):
  applications to *other* jobs whose CV was read, from the last
  `REDISCOVERY_MAX_AGE_DAYS` days (default 365, data minimisation), and not
  in the middle of their own process (no scheduled or live interview, not
  shortlisted while waiting for one). People who already applied to this
  job (same email) or were added from the pool are left out. A person with
  several applications is checked once, with the latest one.
- **Same screening, no new AI:** each past CV is screened against job B's
  requirements, weights and job description with the **same subgraph as
  LangGraph 2** (`app/graphs/talent_rediscovery.py`): mandatory gate,
  requirement evidence, four dimension scores. Parsed CVs and embeddings
  are reused, everything runs locally, nothing is sent to an AI provider.
  Results are stored in `rediscovery_runs` / `rediscovery_matches`, apart
  from job B's own ranking, so they never mix into it.
- **When it runs:** after every finished screening of the job, and on
  **Check again** (e.g. more people agreed since). Checkpointed and
  resumed after a restart like the other runs.
- **On screen** (job page, under the ranking): name, the job they applied
  for, when, how they did there ("Ranked 3 of 12", "Interviewed",
  "Not ranked: …"), the overall score for this job and the requirements
  met; clicking a name opens the same drawer as the ranking (score
  breakdown, requirement evidence, View CV). **Add to this job** copies the
  application (the original stays in its job) and marks it
  "From talent pool". A suggestion is never added automatically.
- **Hidden again** when it no longer qualifies (left the pool, now in an
  interview, already applied); added ones stay, marked "Added".
- **API (interviewers only):** `GET /api/jobs/{id}/rediscovery`,
  `POST /api/jobs/{id}/rediscovery` (check again; 409 while one runs),
  `POST /api/jobs/{id}/rediscovery/{candidate}/add`,
  `PUT /api/jobs/{id}/cvs/{candidate}/talent-pool`. Candidates get 403.
- **Google Form:** add an optional checkbox question whose title contains
  "talent pool", e.g. "Talent pool: other vacancies (optional)" with the
  option "Yes, consider me for other vacancies". Forms without it still
  work (nobody joins the pool).

**Demo:** synthetic CV 29 (`29-imran-crossway.pdf`, Python and PHP)
applies for the PHP Laravel job with the talent-pool box ticked. Create a
"Python Backend Developer" job in the chat (mandatory Python, Docker),
then on its page click **Check again**: Imran is suggested with his
evidence; **Add to this job**, then **Screen CVs**.

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

## Privacy note

What CandiVue keeps about a candidate, where, for how long, who receives
it, and the limits of its fairness. Only synthetic or sample data is used
in development and the demo (N13).

**Stored (PostgreSQL and the `cv_intake` volume, on this machine):**

| Data | Kept until |
|---|---|
| Application: name, email, the CV file, the text read from it (parsed CV, passages and their embeddings), screening scores and reasons | The applicant or the job is deleted (`DELETE /api/jobs/{job}/cvs/{candidate}`, `DELETE /api/jobs/{job}`) |
| Interview: time, link (hash only), chat messages, the **written transcript**, Q&A analysis, CV claims check, interview score and quality, assessment report | The interview or the applicant is deleted |
| Application photo (F7, §4B-15), only for invited applicants: one encrypted face embedding and an encrypted small copy (320 px), never the original file; the check-in result and consent time | 30 days after the applicant's last interview (`FACE_RETENTION_DAYS`), when all their interviews are cancelled, on withdrawal, or when the applicant or job is deleted. The original photo stays in the form owner's Google Drive: delete it there after the job |
| Saved workflow state (LangGraph checkpoints) | Deleted when the run finishes; kept only to continue a failed run or a report waiting for review; the rest is cleaned up every hour |
| Talent pool consent (F11) | Applications older than `REDISCOVERY_MAX_AGE_DAYS` (365) are no longer matched |

**Not stored:** audio and video. The call is never recorded; speech is
streamed to Deepgram and only the text is kept; the check-in camera
pictures are compared in memory and dropped (N16). Uploaded
knowledge-base files keep only their text. Logs contain ids, never names,
email addresses, CV or transcript text (checked in all services).

**Deleting a candidate** (N19) removes, in one request: the application,
its scores and passages, its interviews with transcripts, chat, analyses,
reports and application photo (database cascades), the CV file, and the
saved workflow state that held copies of their data
(`tests/test_privacy.py`). An application added from the talent pool to
another job is that person's separate application and is deleted on its
own. Data already sent to an external provider (below) cannot be recalled
by CandiVue.

**Deleting a job** ("Delete job" on the job page, after a confirmation
that lists what goes) does the same for every applicant of the job, and
also removes the job profile, JDs, screening and rediscovery runs, the
job's chat, the CV folder and the job-board post. Scheduled interviews are
cancelled first (cancellation email, calendar event removed). It is
refused while a screening, talent rediscovery, analysis or report of the
job is running, or an interview is live (`tests/test_job_deletion.py`).

**External providers:** see "AI provider and data sent to it" for exactly
what each one receives: Gemini (job data, transcripts and reduced CV facts
with names and contacts removed), Deepgram (interview audio, streamed),
Google Forms / Drive / Sheets (what applicants submit), Gmail (invitations,
access codes and selection emails), Google Calendar (the interviewer's events), Blogger (job
posts, no candidate data). Face recognition, CV screening and embeddings
run locally.

**Fairness and its limits:**

- Scores use job requirements only. Protected attributes (age, gender,
  ethnicity, nationality, religion, marital status) are never stored
  (`tests/test_models.py`), and every AI prompt says not to consider or
  infer them, nor accent, grammar or filler words (N20).
- Nothing is decided automatically: rankings, scores, claim flags, the
  identity result and the report are prompts for a person, who reviews
  and approves.
- Limits a reviewer should know: screening thresholds were calibrated on
  synthetic CVs; speech recognition can mishear some accents (the prompts
  tell the AI that an odd word is probably a recognition error); face
  recognition models can be less accurate for some groups and in poor
  light, which is why a face result is never used for scoring, never
  assumed, and "not confirmed" asks the interviewer to check; the
  application photo is chosen by the applicant, so a match is not an ID
  check; the AI can
  be wrong, so every conclusion shows its evidence.

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
  may load; no other site may frame the app. Frames may only show
  CandiVue's own pages and files it loaded itself (`blob:`, the CV preview
  in the interview room).
- `Referrer-Policy: no-referrer`: addresses such as interview links are
  never sent to other sites.
- `X-Content-Type-Options`, `X-Frame-Options`, and a `Permissions-Policy`
  that allows camera, microphone and screen sharing (`display-capture`)
  only for CandiVue itself.
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
