# Handoff: CandiVue AI — Web UI

## Overview
Web UI for **CandiVue AI**, an AI-assisted recruitment and interview platform (BJIT final project, repo `candivue-ai-30225`). It screens CVs, runs live 1-on-1 video interviews with a live transcript, analyses Q&A, and drafts an evidence-backed assessment report. **It supports human decisions only — nothing is hired or rejected automatically.**

Two roles, strictly separated (enforce in the backend, not only in the UI — requirement N9):
- **Interviewer** — email + password login; sees every interviewer screen.
- **Candidate** — no account; joins only via a unique interview link. Must **never** see scores, rankings, reports, transcripts, the Hiring Assistant or the identity panel.

## About the Design Files
The `.dc.html` files in this bundle are **design references built in HTML** — prototypes showing intended look, copy and behaviour. They are **not production code**. Recreate them in the target stack:

- **React 19 + Vite**
- **Mantine v9**: `@mantine/core`, `@mantine/dates`, `@mantine/charts`, `@mantine/notifications`, `@mantine/form`, plus `@mantine/dropzone` (Knowledge Base upload)
- **Icons:** `@tabler/icons-react` (the prototypes use the Tabler webfont; names match, e.g. `ti ti-briefcase` → `IconBriefcase`)
- Fonts: **Public Sans** (UI) and **IBM Plex Mono** (timestamps, IDs, source chips) from Google Fonts

Each file opens directly in a browser (keep `support.js` and `theme.js` next to them). Files are laid out as a pan/zoom canvas: each numbered section (`1`, `2`…) groups frames; each frame has an id badge (`1a`, `2b`…). Frame `…a` in section 1 is usually the main, interactive screen; later frames are states.

## Fidelity
**High-fidelity.** Final colours, type, spacing, copy and interactions. Recreate pixel-accurately using Mantine components and a custom Mantine theme (tokens below). Desktop-first, 1280px+ wide.

---

## Design Tokens

### Mantine theme
```ts
const harbor = ['#EDF5F6','#D5E9EB','#A9D2D6','#7CBAC1','#4FA2AB','#2F8A94','#23717A','#1C5D65','#164A51','#103A40'];
createTheme({
  primaryColor: 'harbor', primaryShade: { light: 6, dark: 4 },
  colors: { harbor },
  fontFamily: "'Public Sans', system-ui, sans-serif",
  fontFamilyMonospace: "'IBM Plex Mono', monospace",
  defaultRadius: 'sm',            // 4px controls; cards use radius="md" (8px)
  headings: { fontWeight: '600' },
});
```
Alternative brand direction **Iris** (not used in screens): `#F0F0FA, #DFE0F4, #BFC1E8, —, #7E83CC, —, #4C52A6, #3F4490, —, #262A5C`.

### Neutrals (light)
| Token | Hex | Use |
|---|---|---|
| ink | `#1A2227` | headings, body (15.9:1) |
| text-secondary | `#48535B` | descriptions (7.9:1) |
| text-dimmed | `#66717A` | labels, meta — minimum for text (4.9:1) |
| disabled text | `#8A949A` | disabled buttons only |
| border-strong | `#C9D0D4` | inputs, default buttons |
| border | `#DEE3E6` | cards, table header rule |
| row divider | `#E9ECEE` / `#F0F2F4` | table rows / transcript rows |
| app background | `#F5F7F8` | AppShell main |
| surface | `#FFFFFF` | cards, navbar, header |
| hover row | `#F1F4F5` | table row hover |
| selected row | `#EDF5F6` | harbor.0 |
| skeleton | `#EDF0F2` / `#E3E7EA` | |

### Semantic (badge/alert: text on tint)
| | solid | tint bg | text |
|---|---|---|---|
| success | `#2D7A4E` | `#E7F3EC` | `#245F3E` |
| warning | `#C08A1E` | `#FBF0D9` | `#7A5000` (alert body `#5A3D00`) |
| danger | `#B03A2E` | `#FBE9E7` | `#932E24` (alert body `#5A2620`) |
| info / running | `#2B5FA8` | `#E7EEF9` | `#234E8B` (alert body `#1F3B66`) |
| neutral | `#66717A` | `#EEF1F3` | `#3E484F` |
| speaker: Interviewer | — | — | `#1C5D65` |
| speaker: Candidate | — | — | `#6B4A9E` |

**Scores are never red/green.** Show score numbers in ink with a harbor.6 bar (`Progress` 4–10px, track `#EDF0F2`).

### Dark mode (Mantine `colorScheme="dark"`)
Body `#12181B`, surface `#1A2226`, border `#2B353A`, text `#E6ECEE`, dimmed `#A3AFB4`, primary `#5DB3BC`, primary tint `#1C3A3E`. Badge tints: success `#1E3A2B`/`#8FD3A9`, warning `#3D3115`/`#F0C66E`, danger `#41201C`/`#F2A096`, info `#1B2A42`/`#9DBDF0`. Full light→dark map: `theme.js` (`BG`, `TX`, `BD` objects) — use it as the source for a Mantine CSS-variables resolver. Canvas page background in dark: `#0E1416`.

### Typography
| Role | Size / weight / line-height |
|---|---|
| Title order 1 (page) | 26 / 600 / 1.3, letter-spacing −0.01em |
| Title order 2 | 20 / 600 / 1.35 |
| Title order 3 (card title) | 16 / 600 / 1.4 |
| Body (reports, justifications) | 15 / 400 / 1.6 |
| UI text (tables, inputs, buttons) | 14 / 400 / 1.55 |
| Meta / column headers | 12 / 500–600, colour `#66717A` |
| Mono (timestamps, source chips) | 12–13 / 500 IBM Plex Mono |
| Score numeral | 28 / 600 tabular-nums (large: 52 / 700) |

### Spacing, radius, shadow
- Spacing: 4 / 6 / 8 / 10 / 12 / 14 / 16 / 20 / 24 / 32 px. Page padding `24px 32px`. Card padding 16–20px. Gaps between cards 16–20px.
- Radius: controls 4px, cards/alerts 8px, chips 4px, badges 999px, logo mark 28% of size.
- Shadows: cards none (border only); drawer `-8px 0 24px rgba(26,34,39,.10)`; modal `0 12px 40px rgba(0,0,0,.2)`; menu `0 10px 30px rgba(26,34,39,.12)`.
- Controls: Button `size="sm"` height 36 (primary auth/join buttons 40–44). Table rows 44px (lists 52px). Badge height 22, 12px/600, sentence case (`tt="none"`), with leading icon.

### Badges (Mantine `Badge variant="light"` + `leftSection` icon)
Every badge = colour + icon + word (never colour alone).
- **Run status** (`RunStateMixin.status`): Pending (neutral, `IconClock`) · Running (info, small `Loader`) · Waiting for review (warning, `IconEye`) · Completed (success, `IconCheck`) · Failed (danger, `IconAlertTriangle`)
- **Report review** (`review_status`): Waiting for review · Changes requested (harbor light, `IconMessage2`) · Approved (success, `IconCircleCheck`)
- **Requirement match**: Met (success) · Partially met (warning, `IconCircleHalf2`) · Unmet (danger, `IconX`)
- **Identity**: Confident match (success, `IconUserCheck`) · Low confidence (warning, `IconUserQuestion`) · No match (neutral, `IconUserX`) · Not available (neutral, `IconBan`)
- **Candidate pipeline**: New · Invitation pending · Invited · Invitation failed
- **Session**: Scheduled · Live · Ended · Cancelled
- **CV claims (F8)**: Supported · Contradiction (`IconArrowsDiff`) · Unverified (`IconHelp`) · Never discussed (`IconMinus`)

### Logo
`LogoMark` = rounded square (radius 28%) with `linear-gradient(150deg,#2E8F9A 0%,#1B5E66 55%,#123F45 100%)`, a white ring (58% of size, stroke 8.5%), a pupil dot `#BDEDF1` (20%, offset +5%/−5% from centre) and an amber spark `#F2C46D` (13%, at 69%/13%, outlined in `#123F45`). `Wordmark` = "Candi" (ink) + "Vue" (harbor.6, or `#7FD0D8` on dark) 700, letter-spacing −0.025em, followed by an "AI" chip in IBM Plex Mono 600 (harbor.0 bg, `#CFE5E8` border). Header lockup: 30px mark + 17px word. Build the mark as an SVG component (circles + rounded rect). Only on the login screen does the pupil animate (`cvlook`, 6s). Sizes in `Style Guide.dc.html` §4.

---

## App Shell (interviewer screens)
Mantine `AppShell` — header 56px (white, bottom border `#DEE3E6`, padding 0 20px), navbar 240px (white, right border, padding 16px 12px), main `#F5F7F8`.
- Header left: Logo lockup. Right: `UserMenu` (Avatar 30px initials "IA" on harbor.1, name 14/600 + email 12px dimmed, chevron). Clicking opens a `Menu`: name/email, **Appearance Light/Dark** `SegmentedControl`, Help, divider, **Sign out** (red).
- Navbar `NavLink`s (height 40, radius 6, icon 19px): **Jobs** (`IconBriefcase`), **Interviews** (`IconVideo`), **Reports** (`IconFileText`), divider, **Hiring Assistant** (`IconSparkles`), **Knowledge base** (`IconBooks`). Active: bg harbor.0, text harbor.7, 600.
- Live Interview uses a collapsed 64px icon rail instead of the full navbar.

## Screens

Component names below are the names to use in code.

### 1. CV Screening Results — `CV Screening Results.dc.html` (`ScreeningResultsPage`)
- **JobHeader**: breadcrumb (Jobs › Screening results), title "Sample Job: Python Backend Developer", meta "20 CVs received · Last screened …" + run status badge; right **Screen CVs** (filled, `IconPlayerPlay`; while running: loading "Screening…", disabled).
- Info `Alert` (info): "Scores support your decision. CandiVue never rejects or hires anyone automatically."
- **RankingTable** (`Card` + `Table highlightOnHover`): columns Rank 52 · Candidate 1fr · Overall (0–100) 150 (number + 90px bar) · Technical skills 92 · Relevant experience 92 · Qualifications 92 · ATS CV–JD match 84 · Status 150 · chevron 24. Header subtitle shows the AI-set weights (technical 35%, experience 30%, ATS 20%, qualifications 15%). Scanned CVs (OCR fallback) show a small `IconScan` chip with tooltip.
- **ExcludedList**: collapsible card "Excluded: failed a mandatory requirement (4)" → table Candidate · Mandatory requirement · Reason (plain language).
- **UnreadableList**: "1 CV could not be read" with reason and next step; batch otherwise unaffected.
- Row click → **CandidateDrawer** (`Drawer position="right" size=500`, overlay `rgba(26,34,39,.28)`): rank, name, **View CV**; **ScoreBreakdownCard** (overall /100 + per-dimension horizontal `BarChart`-style rows with weight and 1–2 sentence justification); **RequirementList** (requirement, Mandatory/Required/Preferred tag, Met/Partial/Unmet badge, evidence text, `CV · <section>` source chip).
- States (§2): running "12 of 20 CVs" with striped animated `Progress` and "ranking appears when all are screened"; failed (danger alert "Screening stopped at 12 of 20 CVs… No CVs were lost… Try again", previous results kept); empty — no CVs; empty — ready, never screened; skeleton loading; page error; drawer loading / error.

### 2. Live Interview (interviewer) — `Live Interview.dc.html` (`LiveInterviewPage`)
Three IdentityPanel placements (1a fixed right column + assistant below; 1b right-column `Tabs` Identity/Hiring Assistant; 1c identity strip overlaid on candidate video). **Pick one before building** (product owner to confirm; 1a is the default).
- **SessionBar**: LIVE pill (pulsing dot), candidate, job, elapsed timer (mono), connection badge (Connected / Reconnecting… with spinner).
- **VideoTile ×2** (16:9, radius 8, name label bottom-left with mic state).
- **CallControls**: Mute/Unmute, Camera off/on (active state = danger tint), **End session** (filled red) → confirm `Modal` "End the interview?".
- **LiveTranscript**: ordered turns: `00:15` (mono) · speaker label (Interviewer / Candidate colours) · text. Auto-scrolls to newest; new turns fade up.
- **IdentityPanel**: badge + Face/Voice confidence bars; on confident match only: name, headline experience, key skills chips, pre-interview score + rank, areas to probe, "Checked at 00:04 against the reference given with consent on 7 Oct · Re-check". States (§2): Checking, Low confidence (profile hidden), No match, No reference (no consent), Failed. **Never assume identity.**
- **HiringAssistantChat**: "Only you see this"; user bubbles right (harbor.0); AI answers list suggested questions with copy icon and source (`Question bank · …`); quick chips; input + send; "Finding questions…" loader.
- States (§3): reconnecting tile overlay, waiting for candidate, transcript empty/paused, assistant empty/error, end-session modal, camera blocked.

### 3. Assessment Report — `Assessment Report.dc.html` (`AssessmentReportPage`)
- **ReportHeader**: breadcrumb, candidate, job, interview date/duration, review badge; buttons **Interview analysis** and **Export / print**.
- `Tabs`: **Report** | **Compare candidates**.
- **SuitabilityCard**: "Good fit, with gaps to verify" on a 4-step scale (Not yet suitable / Partial fit / Good fit / Strong fit) + "not a decision" note + identity line.
- **ComponentScoresCard**: CV screening + 4 interview dimensions (relevance, accuracy, completeness, articulation) + requirement coverage line.
- **FindingsList**: Strengths, Weaknesses, Evidence gaps, Areas to verify — each conclusion has **SourceChip**s (`Transcript 02:47` or `CV · Work history`). Clicking a chip shows it in **SourcePanel** (sticky right, 320px): highlighted segment with surrounding turns.
- **ReviewBar** (sticky bottom): status badge + hint; **Request changes** (light) → **RequestChangesModal** (required Textarea "What should change?") and **Approve report** (filled). After approve: success banner; after request: "being updated" banner.
- **CompareCandidatesTable**: columns per candidate (2–3, same job, chips to remove), rows per dimension (suitability, CV scores + 4 sub-dimensions, interview dimensions, requirements explored, main strength/gap, identity, review status).
- **ReportPrintView** (§3, A4 794×1123): always light; sources become numbered references; footer "AI-assisted draft, reviewed and approved by a person". Drafts print "Not yet approved".
- States: approved, changes requested v2, generating (`Stepper`: Interview ended → Q&A analysis → Final assessment), failed, no report yet, compare needs ≥2, loading, source load error.

### 4. Interview Analysis — `Interview Analysis.dc.html` (`InterviewAnalysisPage`)
Tabs: **Q&A analysis** (F5) · **Transcript** (F4) · **CV claims check** (F8) · **Interview score** (F9) · **Interview quality** (F10) · **Session details** (F3).
- **RequirementCoverageCard**: each requirement with the Q ids that explored it; never-explored ones highlighted (warning tint).
- **QAPairCard** (expandable): Q id, question, time range, mapped requirement, tags (with follow-up / multi-part split), 4 mini bars; expanded: the turns + "Why these scores" + transcript chip. Only job-related Q&A is scored.
- **TranscriptViewer**: search, speaker `SegmentedControl`, download; Q id margin; highlighted target turn; "overlapping speech" tag; reconnection gap row.
- **SessionDetailsCard** + timeline (opened, joined, identity, reconnect, ended, raw media discarded, analysis done, report ready) + note that raw A/V is discarded after transcription.
- **ClaimsCheckList** (F8): Result · CV says · Interview says · Suggested follow-up; banner "prompts for your own follow-up… nothing here changes a score or a decision".
- **InterviewScoreCard** (F9): separate from CV score; 6 dimensions with evidence.
- **InterviewQualityPanel** (F10): verdict, speaking-time split, coverage, consistency across candidates, suggestions; low-quality state offers **Reschedule with Hiring Assistant**.
- States: analysis running (4 of 7), failed, not held yet, no job-related questions, loading, page error.

### 5. Hiring Assistant — `Hiring Assistant.dc.html` (`HiringAssistantPage`)
Own nav item; **one thread per job**. Columns: navbar 240 · **ThreadList** 260 (job + status line) · chat.
- **JobProgressBar**: Profile → JD approved → Posted → CVs screened → Invitations; "Nothing is posted or sent until you confirm".
- Chat cards: **JobProfileCard** (Mandatory / Required / Preferred), **JdApprovalCard** (version, status, RAG source chips, rejected-version note; pending state: Reject with feedback / Edit / Approve and post), **PostingResultCard**, **ScreeningNotice** (link to results; the chatbot does not run screening), **InvitationConfirmCard** (rank, candidate, slot, calendar status, collapsible email preview, Cancel / Change / **Confirm and send N invitations** → sending → sent).
- **ChatComposer** with suggestion chips.
- **JdEditModal** (§3): title, about, responsibilities; requirements locked to the job profile; saves as a new version (still needs approval). Reject-with-feedback modal.
- States: JD waiting approval, new thread empty, working (tool steps), assistant error, posting failed, invitations partly sent (bounced email), slot taken, loading.

### 6. Knowledge Base — `Knowledge Base.dc.html` (`KnowledgeBasePage`)
Upload documents for RAG (vector store).
- Warning banner: never upload CVs/interview notes/personal data.
- **CollectionNav** (230px): All · Reference library · Company policies · Previous job profiles · Email templates · Interview question bank (count + what each is used for).
- **UploadDropzone** (`@mantine/dropzone`): PDF/DOCX/TXT/MD, ≤20 MB, target collection select.
- **DocumentsTable**: Document (type tile, name, size · added date) · Collection · Status (Uploading / Indexing with striped progress, Ready, Failed, Personal data) · Passages · actions (preview, remove). Inline message rows for failures.
- **RetrievalTestCard**: query → top passages with source + match bar.
- States: drag-over, rejected files, personal data found (blocked), remove confirm, index unavailable, loading, no search results.
- Note: the personal-data scan before indexing is a design proposal — needs a backend step.

### 7. Lists — `Jobs.dc.html`, `Interviews.dc.html`, `Reports.dc.html`
- **JobsTable**: Job · CVs received · Screening status · Interviews · Updated. Primary action "Create job with Hiring Assistant".
- **InterviewsTable** with Upcoming/Past `SegmentedControl`: Candidate · Job · Date and time · Session badge · Invitation badge · action (Join now / Open / Review / Resend / Report).
- **ReportsTable** with job `Select`: Candidate · Interview · Suitability position · Status.
- Each: empty, loading, error. Jobs §2d shows the open UserMenu.

### 8. Login — `Login.dc.html` (`LoginPage`)
Split 1.15fr / 1fr. **BrandPanel** (dark radial gradient `#1E6670 → #123F45 → #0B2A2F`, breathing concentric rings, floating evidence chips, headline "Hiring decisions, backed by evidence.", three principles). **LoginForm**: "Welcome back", Email + Password (`PasswordInput`), "Forgot password?", Keep me signed in, Sign in (loading → success), candidate note "join using the private link". Validation: email must contain “@” (inline error); wrong credentials → danger alert with shake. States: wrong password, signing in, session expired, service unavailable.

### 9. Candidate (no account) — `Candidate Join.dc.html`
No AppShell; simple header (logo, help email, theme toggle). Content column 620px.
- **Enrolment** (when confirming the invitation, before interview day — F7 reference capture): `Stepper` Consent → Face and voice → Done. **InvitationSummary** (role, date/time). **BiometricConsentCard**: what we capture (one photo + 10-second voice), how long (deleted 30 days after the interview — confirm real policy), who sees what (interviewer sees only match result), not used for scoring; consent `Checkbox` required to Continue; "Continue without identification" (no penalty). **ReferenceCapture** (photo with oval guide, read-aloud sentence + recorder). **EnrolmentDone**.
- **Join day**: **JoinWelcome** (welcome, role, date/time only; "The call is not recorded; only a written transcript is kept"), **ConsentReconfirm** (checkbox required), **DeviceCheck** (camera/mic/speaker selects, mic level meter, Join interview), **WaitingRoom**.
- **In call** (§4): **CandidateCallPage** — interviewer video, self PiP, Mute / Camera / Leave, connection badge, "Not recorded · a written transcript is kept". **No transcript, scores, identity or assistant.** Reconnecting overlay; leave confirm.
- States: checking link, link not open yet (opens 15 min before), expired, already connected elsewhere (one connection only), session ended, camera/mic blocked, no mic sound, photo not usable, link not recognised, generic connection error.

---

## Interactions & Behaviour
- Errors are always plain language: what happened · what is safe · what to do. Never show stack traces, codes, paths or prompts (N12).
- Long AI work is async with status from `RunStateMixin` (pending → running → completed / failed / waiting_for_review); screening shows `processed of total`. Failed runs resume from the last step ("Try again… continues where it stopped").
- Use `@mantine/notifications` for completion events (e.g. "Report approved", "Screening finished").
- **Animations** (subtle, 150–350ms, `cubic-bezier(.2,.8,.2,1)` or ease-out): drawer slide-in from right 28px (280ms) + overlay fade; modal pop (scale .97 → 1, 250ms); new transcript turns / chat messages fade-up 6px (300–350ms); score bars grow from left (600ms); running progress uses moving diagonal stripes (1s linear loop); row hover background transition 150ms; login: staggered fade-up of brand copy, breathing rings (9s), floating chips (7–8s), logo pupil glance (6s); error alert shake (400ms). Respect `prefers-reduced-motion`.
- **Light/Dark**: switch lives in the UserMenu (and a toggle icon on candidate/login pages); persist to `localStorage` key `candivue-theme`, sync across tabs. In React use Mantine `useMantineColorScheme()` + `localStorageColorSchemeManager({ key: 'candivue-theme' })`. The print view always renders light. (`theme.js` is a prototype-only runtime colour remapper — do not port it; use Mantine's colour scheme instead.)
- Two-tab demo: keep auth tokens per tab (`sessionStorage`) so interviewer and candidate tabs don't overwrite each other.

## State Management (per screen, indicative)
- Screening: `run {status, processed, total, error}`, `rankedCandidates[]`, `excluded[]`, `unreadable[]`, `selectedCandidateId`, `excludedOpen`.
- Live interview: `connection: connected|reconnecting`, `muted`, `cameraOff`, `transcriptTurns[]` (stream), `identity {state, faceConf, voiceConf, profile?}`, `assistantMessages[]`, `assistantPending`.
- Report: `report {status, review_status, content, version}`, `selectedSourceId`, `activeTab`, `requestChangesOpen`, `comment`, `compareCandidateIds[]`.
- Interview analysis: `qaPairs[]`, `coverage[]`, `expanded{}`, `transcriptQuery`, `speakerFilter`, optional `claims[]`, `interviewScore`, `quality`.
- Hiring Assistant: `threads[]`, `activeJobId`, `messages[]` (typed cards: profile, jd, posting, screening, invitations), `pendingInterrupt` (HITL: jd_approval | invitation_confirm).
- Knowledge base: `collections[]`, `activeCollection`, `documents[] {status, progress, chunks, error}`, `searchQuery`, `hits[]`.
- Candidate: `linkState` (checking | early | open | expired | in_use | ended | invalid), `consent`, `devices`, `callState`.

## Data
All data is synthetic ("Candidate A–T", "Sample Job: Python Backend Developer", "Interviewer A", `example.com`). Never ship real names, photos or CVs (N13–N15).

## Assets
- Icons: Tabler Icons (`@tabler/icons-react`).
- Fonts: Public Sans, IBM Plex Mono (Google Fonts).
- Video tiles/camera previews are striped placeholders (`repeating-linear-gradient(135deg,#1E272C 0 10px,#222C31 10px 20px)` with a mono caption) — replace with real `<video>` elements.
- Logo: built from shapes; no image files.

## Files
| File | Contents |
|---|---|
| `Style Guide.dc.html` | Brand directions (Harbor / Iris), logo & icon, colour tokens, type, buttons, badges, card/table, inputs, feedback, dark mode |
| `Login.dc.html` | Interviewer login + states |
| `Jobs.dc.html` · `Interviews.dc.html` · `Reports.dc.html` | List pages + states, user menu |
| `CV Screening Results.dc.html` | Screening results, drawer, run states |
| `Live Interview.dc.html` | 3 layout options, identity states, session states |
| `Assessment Report.dc.html` | Report, compare, review, print layout, states |
| `Interview Analysis.dc.html` | Q&A, transcript, session, F8/F9/F10, states |
| `Hiring Assistant.dc.html` | Chat threads, HITL cards, JD edit, states |
| `Knowledge Base.dc.html` | RAG document upload, retrieval test, states |
| `Candidate Join.dc.html` | Enrolment, join, in-call, link/device states |
| `support.js` | Prototype runtime (needed to open the files; not for production) |
| `theme.js` | Prototype light/dark remapper (reference for dark colour values only) |

## Open decisions
- Choose the Live Interview identity layout (1a / 1b / 1c).
- Confirm biometric retention period and consent wording.
- F11 innovation feature is the trainee's own design and is intentionally not included.
