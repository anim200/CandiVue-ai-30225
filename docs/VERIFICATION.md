# CandiVue AI – Security, privacy, performance and feature verification

WBS module 9 (Day 19). What was checked, how, the results, what was fixed,
and what is still open. Verified on 18-10-2026 on the development laptop
(Windows 11, Docker Desktop, 16 CPUs, 7.6 GB for Docker), with synthetic
data only (N13).

## 9.1 Security review

| Check | How it was verified | Result |
|---|---|---|
| Every API route needs the interviewer role unless listed on purpose | `tests/test_auth_routes.py` walks every route of the real app | Pass (open: health, login, link code, me, LiveKit webhook) |
| Candidates never see scores, rankings, reports, transcripts, identity results | Route guards + tests in each feature (`test_*` "candidates cannot ...") | Pass |
| Request bodies are bounded | Code scan: every text/list field of every request model has a length limit or fixed values | Pass |
| Uploads: type by content, size limits | CVs (PDF/DOCX by content, `MAX_CV_MB`), knowledge base (`MAX_UPLOAD_MB`), identity pictures (3 images, 2 MB each, must decode), nginx 25 MB per request; tests in `test_collector`, `test_knowledge_*`, `test_identity` | Pass |
| Interview link | Only a SHA-256 hash stored; one-time emailed code (HMAC, 10 min, 5 tries) before the link opens (`test_auth_api.py`) | Pass |
| Secrets | Only in `.env` (git-ignored); `git grep` for API keys, private keys and tokens: none; no key files tracked; each service gets only its own secret | Pass |
| Pinned dependencies | All Python requirements `==`; npm exact versions + lock file; every Docker image pinned (e.g. `python:3.13.16-slim`, `livekit-server:v1.13.9`); face models pinned by commit and SHA-256 | Pass |
| No personal data in logs | All `logger` calls of the backend and the three MCP servers read: ids, counts and error types only | Pass |

**Provider failures: bounded retries, clear errors, no silent data loss.**

| Provider | Retries | Failure seen by the user | Data kept |
|---|---|---|---|
| Gemini (`invoke_llm`) | `LLM_MAX_RETRIES` (2) with growing pauses; a daily limit is not retried | Run "stopped" with a plain message (which model hit its limit); 503 in the chat | Checkpoint: "Try again" continues, finished steps are not repeated (`test_post_interview`) |
| Local embeddings (Ollama) | **New:** 3 tries, 1 s and 2 s pauses (`test_embeddings`) | "The AI service is unavailable" | Same (resumable runs) |
| Local screening model (Ollama) | **New:** one question at a time (no queue timeouts) | "The local screening model is unavailable" | Same |
| Email, calendar, job board (MCP) | 3 tries each | Card / page shows the reason; the invitation or post stays saved | Yes |
| Deepgram | Reconnect with back-off; refused key or no credit: one clear problem | "Speech-to-text problem" in the room | Unconfirmed audio is sent again after a reconnect (`test_transcriber`) |
| LiveKit (call) | Browser reconnects to the same session | "Reconnecting…" | Transcript continues |

## 9.2 Privacy and fairness

- **Deletion of a candidate and all associated data (N19):**
  `DELETE /api/jobs/{job}/cvs/{candidate}`. **Found and fixed:** the
  database rows and the CV file were deleted, but the saved workflow state
  (LangGraph checkpoints) kept copies of CV text, transcript lines and
  room-assistant chat, also for finished runs (~54 MB, hundreds of
  threads). Now a finished run deletes its own state, deleting a candidate
  deletes theirs at once, and an hourly clean-up removes state of deleted
  or finished runs (54 MB → 8.5 MB; `tests/test_privacy.py`).
- **Job-only scoring:** screening uses only the job's requirements; no
  protected attribute is stored (`test_models.py`); every AI prompt says not
  to use or infer them, nor accent, grammar or filler words; names and
  contacts are removed before transcripts and CV facts go to the LLM.
- **Raw media:** no recording (no LiveKit egress); audio is streamed to
  Deepgram from memory; identity pictures are compared in memory; enrolment
  pictures are not stored, only an encrypted embedding (deleted after 30
  days).
- **Logs:** no names, emails, CV or transcript text (see 9.1).
- **Privacy note:** README "Privacy note" (stored fields, retention,
  deletion, external providers, fairness limits) and "AI provider and data
  sent to it" (N18).

## 9.3 Performance

| Measure | Result |
|---|---|
| 20-CV batch (F1), first screening | ~3-5 min for 20-22 CVs on the CPU (08-10-2026); a repeat run ~7-8 s (parsed CVs and embeddings reused) |
| 29 CVs while a live interview runs | **18.8 min**, completed (after the fixes below; it failed before them) |
| Live transcript: words on screen | ~1 s (grey "speaking" line, 14-10-2026 matrix) |
| Live transcript: turn saved after speech ends | median **0.8 s**, 95% within **2.7 s**, max 5.9 s (218 turns, 45-minute test) |
| API responsiveness during a fresh 29-CV screening | median 62 ms, 95% within 130 ms, slowest 0.62 s (318 calls; before the fix: slowest over 20 s) |
| Analysis + report after a 45-minute interview | report ready **82 s** after "End" with **6** Gemini requests (60 Q&A units = 3 batches) |

### Stability test: 45 minutes alongside background CV processing (#647758)

Two Chromium browsers on this laptop (interviewer and candidate) in one
interview for 45 minutes: synthetic voices with faint room noise as
microphones, a public-domain painting as the candidate's camera (identity
check on), 27 question-and-answer rounds, a screening of 29 CVs started at
minute 5, the candidate's page reloaded at minute 20, then "End".

| Check | Result |
|---|---|
| Call connected at every check (27) | **Yes**; the reload rejoined at once |
| Transcript | 218 turns, in order; **95.8%** of the interviewer's and **97.4%** of the candidate's words saved (the rest: recognition differences, e.g. "pro filed") |
| Memory over 45 minutes | backend 445 → 465 MB, transcriber 279 → 313 MB, LiveKit 82 → 76 MB, database stable: no leak |
| CPU | transcriber median 16%; Ollama up to 16 cores while screening |
| Identity check | confirmed 18 of 27 checks; "no face" in 9, in two stretches of heavy load (see below) |
| Screening of 29 CVs | **Failed at 27 of 30** after 10.8 min: three local-model requests timed out in Ollama's queue → **fixed**, then re-tested (below) |
| Analysis and report | completed; 60 units (the maximum) evaluated in 3 batches; report waiting for review |

**Found and fixed during the test:**

1. Local screening model requests queued in Ollama (one at a time on a
   CPU) and timed out while CVs were screened in parallel; the backend
   now asks one question at a time, so the timeout covers the answer only.
2. The identity check asked LiveKit for a medium video layer; with a
   640×480 camera that is 320×240 and the face became too small ("no
   face"). It now asks for the full picture. When the browser itself lowers
   the video quality on a busy computer, the panel now says "Face unclear:
   ask the candidate to sit closer or improve the light" instead of "No
   face in view".
3. "Take the pictures" could run before the camera had a picture (empty
   pictures, a technical error); the button now waits for the video.
4. Local embeddings now retry (see 9.1).
5. **API stalls and a wrongly skipped CV:** screening ran about 20 CV
   branches at once; they used up the backend's 15 database connections
   ("QueuePool limit reached"), so API requests waited up to 30 s and one
   valid CV was marked "could not be parsed". Screening now runs at most 4
   CVs at a time (`MAX_PARALLEL_CVS`, also for talent rediscovery). The
   local models answer one request at a time anyway, so it is not slower:
   11 instead of 7 CVs screened in the first 3 minutes.

**Test artifacts (not app problems):** without room noise the synthetic
microphones send perfect digital silence between clips; the interviewer's
browser then rejoined the call every 20-40 s (7-8 times in 4 minutes).
With faint noise, like any real microphone, it never did (0). Screenings
left over from earlier test runs (whose test jobs had been deleted) were
still running at the start of the 45-minute test; in the app, jobs cannot
be deleted.

### Re-test after the fixes

**15-minute interview with a 29-CV screening** (fixes 1-4): call
connected at every check; 79 turns in order, saved a median 0.9 s (95%
within 1.8 s) after the speech; 91.7% / 97.2% of the interviewer's /
candidate's words; identity confirmed (0.99) in 7 of 10 checks, "face
unclear" in the others while the screening loaded the CPU; analysis and
report ready 87 s after "End" (43 units, 6 Gemini requests); the screening
**completed** (30 of 30, 18.8 min). API stalls were still seen → fix 5.

**API probe, fresh 29-CV screening, 3 minutes, 1 call/s to two routes**:

| | Before fix 5 | After fix 5 |
|---|---|---|
| Median / 95% | 65 / 196 ms | 62 / 130 ms |
| Slowest | over 20 s (timeout) | 0.62 s |
| Calls over 2 s | 2 | 0 |
| Pool errors / wrongly skipped CVs | yes | none |
| CVs screened in 3 minutes | 7 | 11 |

## 9.4 Required-feature verification

| Feature | Automated tests (real database, fake AI) | Live check with real services |
|---|---|---|
| F1 parsing / OCR / hard-requirement screening | `test_screening_flow` (rank, exclude with reasons, unreadable file skipped, years in words, second look before excluding), `test_screening_rules`, **new** `test_cv_text` (OCR of a scanned PDF, blank scan) | 20-22 synthetic CVs match `EXPECTED.md` (08-10-2026) |
| F2 stable scoring, weights | `test_screening_flow` (weights win, reset), **new** "same CVs, same scores" test | Same ranking on repeat runs |
| F3 interview, link, room | `test_interviews`, `test_interview_room`, `test_auth_api` | Two-browser calls; 45-minute test |
| F4 transcript | `test_transcriber` (whole stream, reconnect, no loss) | 14-10 matrix; 45-minute test |
| F5 Q&A analysis | `test_post_interview`, `test_qa_pairs` | Gemini, interview 102 and the 45-minute test |
| F6 assessment report, review | `test_post_interview`, `test_assessment` | Review loop, export |
| F7 identity | `test_identity` | Paintings as cameras: match 0.96-0.99, no match 0.17 |
| F11 talent rediscovery | `test_talent_rediscovery` | Two-job UI check |
| Access control (N9) | `test_auth_routes`, guards in every feature test | – |
| Workflow recovery (N26) | `test_runner` (resume at startup), `test_checkpointer`, "continues after a failure" tests | Screening failure → "Try again" continues |

**Totals:** 293 backend tests and 36 frontend tests pass; ruff clean;
frontend build passes.

### Release readiness

| Item | Status |
|---|---|
| F1-F6, F7, F11 working end to end with synthetic CVs | Ready |
| **The trainer's 20 sample CVs** (N13, CN5; WBS 9.4 "20 supplied CVs") | **Open:** not received yet. When they arrive: create the job in the chat, post it, add the 20 CVs (Add CV), Screen CVs, shortlist and invite, hold one interview, end it, review and approve the report, then compare with this table |
| Trainer approvals (job board, calendar MCP, F5 split, F7) | Open (requirement.md §14) |
| Redmine ids for modules 6-8 (`#TBD` refs) | Open (user) |
| Figures 2, 5, 6 updated for the latest design | Open (user) |
| Blogger refresh token (7-day Testing mode) | Renew before the demo |
| One short check with a real microphone and webcam on two tabs (timestamps, no rejoins) | Open (needs the user, ~5 min) |
