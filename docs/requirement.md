# AI-Powered Recruitment & Interview Intelligence Platform — Complete Requirements Reference

> **Purpose:** A portable, source-grounded reference for continuing the final project in a new chat or after context loss. This is a restatement and indexing of the issued Business Information Document (BID), **not** a completed Software Requirements Specification (SRS), Work Breakdown Structure (WBS), workflow diagram, architecture proposal, or implementation plan. The WBS and SRS must be prepared independently by the trainee, without AI support; the trainee reports permission to use AI for the architecture and workflow diagrams (§13).
>
> **Source of truth:** The issued 34-page BID (`Final_Project_doc_Business_Info_Document_AI_Recruitment_Platform_v2(3).pdf`) **plus the written trainer Q&A clarification sheet provided on 28 September 2026**. Where a trainer answer changes or tightens the BID, that clarification is recorded below. Project-specific decisions explicitly confirmed by the trainee are also marked as such. The original BID and trainer clarifications take precedence over this reference if there is a discrepancy.
>
> **Status markers:** **MUST / Core** = mandatory; **Stretch / Bonus** = optional credit; **Recommended** = optional implementation suggestion; **Clarify** = unresolved source ambiguity. Examples in this reference illustrate requirements and are **not** mandated technology selections, scoring formulas, file sizes, or architecture decisions.

## 0. Fast-start context for a future chat

- **Assignment:** Solo final evaluation project in the AI Trainee Developer Programme. The trainee proposes the product name and identity; the BID's descriptive title is not an assigned product name.
- **Product intent:** A web-based, AI-assisted recruitment and interview intelligence platform covering **pre-interview CV screening**, **live interviewer–candidate video interviews with transcript capture**, and **post-interview analysis plus an evidence-backed consolidated assessment**. The product augments human hiring decisions, not replaces them.
- **Mandatory functionality:** F1, F2, F3, F4, F5, F6 and one original, integrated trainee-conceived innovation F11. **Project-specific override:** F7 Candidate Identification & Real-Time Profile Overview, including the face/voice-recognition capability, is also required and must not be omitted, even though the original BID classified F7 as Stretch/Bonus.
- **Project-specific decision (JD generation):** the LLM-generated job description will use **RAG (retrieval-augmented generation)**. This is the trainee's own design decision, not a trainer or BID requirement.
- **Project-specific decisions of 30 Sep 2026 (see §4B):** (1) the approved job description will be **posted to an external job board (e.g. LinkedIn) through MCP**; (2) **updated 2 Oct 2026 (§4B-9):** the job post links to a **Google Form**; applicants' CVs are saved to **Google Drive**; a backend **CV Collector service** fetches them from Drive into the CV intake directory, and the CV Screening LangGraph reads them from there; (3) the unique interview link is **emailed to the candidate through MCP**; (4) in F5, **job-related answers are evaluated by the LLM** and **company-related answers are evaluated through RAG**; (5) the LangGraph workflows include **human-in-the-loop (HITL)** review points where the interviewer approves the job description, the interview invitations and the final assessment.
- **Project-specific decision of 1 Oct 2026 (see §4B-8):** the interviewer works through a **Hiring Assistant chatbot** (LangGraph agent). It builds the job profile, writes the JD (deciding itself when to use RAG), posts the approved JD via MCP, and later schedules interviews through **calendar and email MCP** (email format retrieved by RAG), using the ranked candidates saved in the database. The chatbot does **not** run or control the other three LangGraphs (CV Screening & Scoring, Interview Q&A Analysis, Final Assessment); they are separate workflows started by the application. The job-board posting, external calendar integration and the F5 split conflict with the BID or trainer Q&A and need written trainer confirmation (§14).
- **Project-specific decisions of 2 Oct 2026 (see §4B-9, §4B-10):** CVs are collected through a **Google Form** linked in the job post, saved to **Google Drive**, and fetched by a backend **CV Collector service** into the CV intake directory; during the live interview the interviewer can use the **Hiring Assistant** to get **RAG-suggested questions** from a question bank (previous years' and suitable questions).
- **Optional stretch functionality:** F8, F9 and F10 remain optional unless the trainer later changes their status. The original BID still awards F7–F10 as stretch bonus items, but this project has separately committed to implementing F7.
- **Required engineering:** Python backend/AI, meaningful multi-step stateful LangGraph, FastAPI + Pydantic/OpenAPI, complete local Docker containerisation (Compose for multiple services), GitHub with real incremental commit history, trainee-chosen justified frontend, persistent data, security/privacy and clean-machine reproducibility.
- **Sample inputs:** 20 trainer-provided sample CVs for development, testing and final demo; additional clearly labelled synthetic edge-case CVs allowed. Do not commit provided CVs publicly or personal candidate data to the repository.
- **Confirmed timeline:** Use a **20-working-day project timeline**. The trainee confirmed the project **started on 28 September 2026 (Day 1)**, and the trainer clarification states that **all documents and code must be submitted by 27 October 2026**. The earlier 17-day cover-page wording is no longer the planning basis for this project.
- **AI restriction:** AI assistance allowed for coding, UI design, paid/local LLMs, speech-to-text and video-feed collection. **WBS and SRS must be done without any AI support.** The BID also lists the workflow diagram as no-AI, but the trainee reports having received **permission to use AI for the architecture and workflow diagrams** (§13). All submitted work must be personally understood/explainable.
- **Suggested message when resuming elsewhere:** “Use the attached requirement.md as the current requirements reference, including trainer Q&A clarifications and project-specific decisions. Do not invent further trainer clarifications or generate the WBS or SRS. Preserve requirement IDs, the confirmed 20-working-day timeline, the project-specific decisions in §4B, and the F7 status recorded in §5.3.”

---

## 1. Document Purpose & Audience — BID §1, p. 4

**Three roles of the BID:**
1. **Business brief:** Describes business need, intent and rationale; implementation choice (‘how’) belongs to trainee.
2. **Assignment contract:** Mandatory deliverables, phase gates, submission standards and weighted grading.
3. **Instructional guide:** Guidance for requirements analysis, decomposition, prioritisation and delivery.

**Audience and use:**
- **AI trainee developers:** Read in full, treat as authoritative scope/acceptance, raise ambiguities in Phase 1 rather than assuming.
- **Trainers and technical mentors:** Clarifications and checkpoint/progress reviews.
- **Evaluation panel:** Scoring, especially BID §11.
- **Programme coordinators:** Schedule, milestones, sample CVs and submission logistics.

**Document navigation:** §§2–4 business/boundaries; §§5–6 functional and innovation requirements; §§7–8 quality/technology; §§9–12 planning/delivery/evaluation/constraints; §13 permitted/restricted AI use.

## 2. Project Overview & Background — BID §§2.1–2.3, pp. 5–6

### 2.1 Business problem

Large application volumes overwhelm human screening; keyword-only review misses qualified candidates; inconsistent interviewer criteria prevent fair comparison; unstructured notes lose interview content; opaque hiring decisions lack traceable evidence; long hiring cycles risk candidate withdrawal.

### 2.2 Intended solution and stages

| Stage | Business intent | Target result |
|---|---|---|
| Pre-Interview | Ingest/understand CVs; compare against defined jobs | Ranked and scored candidate shortlist |
| During-Interview | Conduct integrated live video/audio; capture conversation | Structured, timestamped, speaker-attributed transcript |
| Post-Interview | Analyse questions/answers; merge CV and interview evidence | Consolidated assessment for human hiring manager |

**Cross-cutting principle:** Every AI score, rank and flag must be explainable and traceable to CV content or transcript evidence. Human decision support, **not automated hiring/rejection**.

### 2.3 Product naming deliverable

- Trainee must propose a **product name**.
- Provide a **one-line positioning statement** describing what it does and for whom.
- Provide **2–4 sentences of rationale** for the name.
- Use same identity across GitHub repository, README, application UI and final presentation.
- Name/product thinking is graded separately (E6).

## 3. Objectives & Definition of Success — BID §3, pp. 7–8

### 3.1 Business objectives

| ID | Objective | Success indicator |
|---|---|---|
| B1 | Reduce manual CV screening | Batch screened/ranked against job requirements without hand-reviewing each CV. |
| B2 | Improve evaluation consistency | Same CV + job profile → stable/reproducible score and visible breakdown. |
| B3 | Capture interview as structured data | Every interview generates speaker-attributed transcript, not free-form notes. |
| B4 | Evidence-based decisions | Assessments cite underlying CV and transcript segments. |
| B5 | Shorten decision time | Consolidated assessment available immediately after interview concludes (long AI operations still require responsive status/error handling). |

### 3.2 Learning/evaluation objectives

| ID | Competency | Demonstrated through |
|---|---|---|
| L1 | Requirement analysis | Quality/depth of Phase 1 clarifications and documented assumptions. |
| L2 | Planning and estimation | Realistic granular traceable WBS. |
| L3 | Agentic AI engineering | Appropriate multi-step stateful LangGraph, not monolithic prompts. |
| L4 | Backend/API design | Clean documented FastAPI boundaries and data contracts. |
| L5 | System integration | Video + audio + transcription + LLM reasoning + persistence in one app. |
| L6 | Delivery discipline | Docker reproducibility, repository cleanliness, meaningful commits. |
| L7 | Creativity/initiative | Original innovation and meaningful product name. |
| L8 | Communication | Documentation, presentation and demo. |

### 3.3 Conditions defining a successful submission

- All **six Core features (F1–F6)** implemented and demonstrated end-to-end.
- **Project-specific requirement: F7 face/voice candidate recognition is implemented and demonstrated as part of the final product.**
- One original **F11 innovation** implemented with written rationale.
- Application runs on a **clean machine** via documented Docker commands; no undocumented manual steps.
- GitHub has full README, clear setup and incremental commits.
- Product name/positioning proposed and applied consistently.
- Trainee can explain and defend architecture during presentation.

## 4. Scope Boundaries — BID §4, pp. 9–10

### 4.1 In scope

| Area | Requirement |
|---|---|
| Job requirement definition | Configure required skills, preferred skills where applicable, qualifications, minimum experience, selection criteria. **Trainer clarification requires support for multiple job profiles**, each with its own requirements/evaluation criteria; trainer also states the **LLM will generate the job description**. **Project-specific decision:** job-description generation will use **RAG** (trainee's design choice; not required by the BID or trainer Q&A). |
| Job post reference | BID contains example generic job-post wording directing interested applicants to send a CV to a contact email; **it does not mandate publishing to a job board**. **Project-specific decision (§4B-2):** the approved job description will be published to an external job board through MCP. |
| CV ingestion/parsing | Upload CVs; **PDF minimum**, DOCX encouraged; extract structured attributes. **Project-specific decision (§4B-3, updated by §4B-9):** CVs submitted through a Google Form are saved to Google Drive; a backend CV Collector service fetches them into the CV intake directory, and the system ingests them from there. |
| Screening/ranking | Automated semantic matching and ordered candidates. |
| Candidate scoring | Criteria-weighted overall and per-criterion scores. |
| Video interview | Integrated real-time interviewer/candidate video/audio with audio capture. |
| Speech recognition | Both speakers, timestamped/structured attributable transcript. |
| Q&A analysis | Relevance, accuracy, completeness, articulation quality. |
| Consolidated assessment | Merge screening, scoring, interview analysis. |
| Innovation | Exactly one original F11 and written rationale. |
| Packaging/delivery | Docker, GitHub, README, setup docs, presentation. |

### 4.2 Explicitly out of scope — **do not spend effort unless explicitly approved or F11 exception applies**

- Production/cloud hosting, CI/CD, load balancing, infrastructure-as-code; **local Docker sufficient**.
- Enterprise authentication: SSO, LDAP and enterprise identity management remain out of scope. **Lightweight authentication/access separation is required.** Trainer clarification accepts JWT/session-based auth and explicitly permits **Firebase Authentication**. The required roles are **Interviewer** and **Candidate** only; no separate recruiter/admin role is required.
- Integration with commercial ATS/HRIS.
- Payroll, offer management, employee onboarding; workflow ends at consolidated assessment.
- Job-board publishing, candidate sourcing, full application portal. **Project-specific decision (§4B-2):** the trainee has decided to publish the job description to a job board through MCP. Because the BID lists this as out of scope (and CN8 says out-of-scope work is not credited and may be penalised), **written trainer approval is required** before building it, and it must not delay Core features.
- **External calendar integration and broader automated calendaring workflows** remain out of scope unless deliberately chosen as F11. However, trainer clarification makes **internal future interview scheduling by date/time mandatory under F3**, together with a candidate-specific interview link. **Project-specific decision (§4B-8):** the Hiring Assistant books interviews through a **calendar MCP**. This is external calendar integration, so it needs **written trainer approval** or must be presented as the F11 innovation feature.
- Multi-tenancy, subscription/billing/licensing.
- Native mobile apps; web only.
- Training/fine-tuning foundation models from scratch; use existing models/APIs.
- Formal WCAG accessibility certification (reasonable accessibility practice welcomed).

### 4.3 Scope-management instruction

Build a **thin end-to-end slice** (CV in → interview conducted → assessment out), then deepen modules. The BID warns against over-engineering one module while leaving the interview pipeline incomplete. The project now follows a **confirmed 20-working-day timeline**, but the same scope-discipline guidance still applies. This is source guidance, **not** permission to omit mandatory acceptance criteria at final submission.

---

## 4A. Written Trainer Q&A Clarifications — 28 Sep 2026

These clarifications supplement the BID and should be treated as current project requirements unless a later trainer instruction supersedes them.

- **Technology:** the BID-mandated Python/FastAPI/LangGraph/Docker constraints still apply. For live A/V, third-party CPaaS/WebRTC libraries or raw WebRTC are both acceptable. Paid AI/STT APIs and local LLMs are permitted; the Q&A does **not** establish extra marks merely for choosing a local LLM.
- **GitHub:** personal GitHub accounts may be added as collaborators for development/remote access, but all project code and commits must remain in the designated **BJIT GitHub repository/account**.
- **Authentication/roles:** lightweight access control is required; JWT/session-based approaches are valid and Firebase Authentication is permitted. Only **Interviewer** and **Candidate** roles are required.
- **Job profiles:** the system must support **multiple job requirement profiles**, each with its own requirements/evaluation criteria. Trainer clarification says the **LLM will generate the job description**; **project decision (§4B-8):** the interviewer creates the profile and JD through the Hiring Assistant chatbot; the job-description/chatbot functionality is interviewer-side rather than candidate-facing. **Project-specific decision:** the trainee has decided that job-description generation will use **RAG**; the trainer Q&A only states that the LLM generates it. The Q&A wording about chatbot/video visibility is unclear and must not be read as removing the F3 two-party video requirement.
- **CV ingestion:** manual UI upload is sufficient; email inbox ingestion may also be supported but is not mandatory. **Project-specific decision (§4B-3, updated by §4B-9):** CVs come from a Google Form, are saved to Google Drive, and are fetched by a backend CV Collector service into the CV intake directory; the system ingests them from there. CVs only need to support **English**. OCR fallback is expected when text is not extractable.
- **Screening:** candidates who fail a mandatory hard requirement are excluded from screening/next stage. AI-generated explanation is sufficient for displayed F1 requirement evidence.
- **F2 scoring:** use **0–100**; include the defined dimensions plus an ATS-style CV–job-description match; trainer says AI determines weights based on the prompt.
- **Video interview:** 1-on-1 only; same-computer two-tab demo is acceptable; future scheduling is required; selected candidates receive unique session links; reconnection should be automatic.
- **Transcription:** participant/channel metadata is sufficient for speaker attribution; English only; elapsed or clock timestamps both accepted; near-real-time streaming may use Google STT/gRPC and does not require WebSocket; overlapping speech may be kept as separate overlapping speaker turns.
- **Raw media:** audio/video may be processed temporarily but should be discarded after transcript generation; permanent raw recording is not required.
- **F5 evaluation:** transcribe the whole conversation but score only job-related Q&A. Multi-part interviewer questions may be split into separate Q&A units. One clarification explicitly requires approved/authoritative external documentation via **RAG** for technical verification.
- **Fairness:** evaluation is to be based on defined job-related criteria and qualifications. The BID's stronger N20 rule still applies: protected/personal attributes must not be used, inferred or stored as scoring inputs.
- **Data deletion:** backend API is sufficient; no UI delete button required.
- **LangGraph persistence:** long-running workflow state must be persisted and must resume after restart from the last completed point.
- **SRS:** a separate SRS is required, but Section 13 still prohibits AI support for preparing it.
- **Deadline:** all documents and code are due **27 October 2026**. The project is now being treated as **20 working days**, starting **28 September 2026**.
- **F7 project override:** trainer Q&A said biometrics were not required in that phase, but the trainee has now confirmed that **F7 face/voice recognition must be implemented for this project**. This later project-specific instruction supersedes the earlier decision to leave biometrics for a future phase.
- **F10:** if the optional interview-quality assessment concludes the interview quality is bad, the Q&A supports **rescheduling the interview** rather than treating the poor-quality session as sufficient evidence.

---

## 4B. Project-Specific Decisions — trainee-confirmed

These are the trainee's own design decisions. They are **not** BID or trainer requirements. Where a decision conflicts with the BID or trainer Q&A, the conflict is stated and the item is listed in §14 for written trainer confirmation.

| # | Date | Decision | Affects | Conflicts / conditions |
|---|---|---|---|---|
| 1 | 28–29 Sep 2026 | **Job-description generation uses RAG** in addition to the LLM. **Updated 1 Oct 2026 (§4B-8):** RAG is a tool of the Hiring Assistant chatbot, which decides itself when to use it; sources are the trusted reference library, company policies and previous job profiles. | Job profiles, JD LangGraph workflow | None; trainer Q&A only says the LLM generates the JD. |
| 2 | 30 Sep 2026 | **Publish the approved job description to an external job board** (e.g. LinkedIn or another site) **through MCP**. Flow: create job profile → generate JD → interviewer approves (human-in-the-loop) → the Hiring Assistant (LangGraph 1) posts the JD via MCP using its `post_to_job_board` tool (the post includes the Google Form link) → applicants submit CVs through the Google Form, saved to Google Drive → the CV Collector service fetches them into the CV intake directory (§4B-9) → screening and later steps. If posting still fails after retries, the error is recorded and the approved JD remains saved. | Pre-interview flow, external services | BID §4.2 lists job-board publishing as **out of scope**; CN8 says out-of-scope work is not credited and may be penalised; CN4 is local-only. Real applicants' CVs would breach **N13/CN5** (only the 20 sample CVs or synthetic data may be used), so any live posting must be a demo/test posting and the final demo must still use the provided CVs. Major boards restrict posting APIs to approved partners, so availability of a free MCP route must be verified. **Needs written trainer approval; must not delay Core.** |
| 3 | 30 Sep 2026 | **Superseded on 2 Oct 2026 by §4B-9 (Google Form → Google Drive → CV Collector service).** Original decision: **the developer places the CVs in a designated CV intake directory** in the project; the system reads and screens the CVs from that directory. The system does **not** collect CVs from the job board or applicants itself. | F1 ingestion | Consistent with the Q&A (manual upload is sufficient; other intake routes allowed). The directory must be **git-ignored** and mounted as a **Docker named volume** (N14, D5); files still get type/size validation (N8) and per-file failure isolation (F1). For development and the final demo, the CVs placed there are the provided 20 sample CVs and any synthetic test CVs (N13/CN5). |
| 4 | 30 Sep 2026 | **Email the unique interview link to the candidate through MCP.** **Updated 1 Oct 2026 (§4B-8):** the Hiring Assistant chatbot sends the email (format retrieved by RAG) and books the interview through a calendar MCP. | F3 link delivery | Resolves the unspecified delivery mechanism in the Q&A. Email credentials via environment variables only (N7); list the email service and what is sent in the README (N18). |
| 5 | 30 Sep 2026 | **F5 evaluation split:** **job-related** answers are evaluated by the **LLM**; **company-related** answers are evaluated through **RAG** over company reference documents. **Updated 17 Oct 2026:** **both** are checked through RAG: job-related (technical) answers by the LLM against the **authoritative reference library**, company-related answers against the **company documents**; without a relevant passage the LLM judges alone and the answer is marked "not checked against a reference document". | F5 Q&A analysis workflow | The update follows the trainer answer that requires **RAG with authoritative external documentation for technical verification**. The Q&A says only job-related Q&A is scored, so scoring company-related answers remains an extension. **Needs trainer confirmation (company-related scoring only).** |
| 6 | 30 Sep 2026 | **MCP** (Model Context Protocol) is used to connect to the job board and the email service (and, from 1 Oct 2026, the calendar service — §4B-8). | Integrations | Additive to the mandated stack (Python, FastAPI, LangGraph, Docker remain unchanged). MCP servers must start via Docker Compose or be documented external services; secrets via environment variables; provider disclosure in README (N18); clear error states if a provider fails (N6). |
| 7 | 30 Sep 2026 | **Human-in-the-loop (HITL) in LangGraph.** The graph pauses (LangGraph `interrupt`) and waits for the interviewer at three points: (a) **JD approval in the Hiring Assistant** — the interviewer approves, edits, or rejects the draft with feedback (rejected drafts are regenerated); only an approved JD is saved and posted to the job board; (b) **Invitation confirmation in the Hiring Assistant** (added 1 Oct 2026) — before any calendar booking or email is sent, the interviewer confirms the chosen candidates, dates, times and email preview; (c) **Final Assessment** — the interviewer reviews the report and approves it or requests changes (changes trigger regeneration) before the report is finalised. | Hiring Assistant, F3 invitations, F6, job-board posting | Supports the BID principle that the platform **augments rather than replaces** human decisions (§2.2). The paused state is saved by the checkpointer, so the run resumes from the same point after the interviewer responds or after a restart (N26). Only the Interviewer role can respond to a review (N9). No conflict with the BID or trainer Q&A. |
| 8 | 1 Oct 2026 | **Hiring Assistant chatbot + three background workflows.** (a) **LangGraph 1 — Hiring Assistant (agent):** an interviewer-only chatbot where the LLM decides which tools to call. Flow: the interviewer creates the job profile (skills, experience, must-haves) by chat → the chatbot writes the JD, calling **RAG when it judges it useful** (trusted reference library, company policies, previous job profiles) → HITL approval → JD posted to the job board via **MCP** → (CV screening runs separately in the application — see (b)) → the interviewer asks the chatbot to **choose candidates from the ranked list** (the chatbot reads the saved ranking from the database) and **schedule future interviews** (date and time) → HITL confirmation → the chatbot creates the session and unique link (backend function), books it through a **calendar MCP**, and sends the invitation through the **email MCP** using an email template retrieved by **RAG** → the candidate receives the email. One chat thread per job opening; conversation state is checkpointed. The chatbot does **not** start, run or control LangGraphs 2–4. (b) **LangGraph 2 — CV Screening & Scoring (workflow):** started from the application (e.g. a "Screen CVs" action on the job page); reads CVs from the intake directory (OCR for scanned CVs), applies the hard-requirement gate, scores each dimension in parallel, combines to 0–100, ranks with reasons. (c) **LangGraph 3 — Interview Q&A Analysis (workflow):** starts automatically when an interview ends. (d) **LangGraph 4 — Final Assessment (workflow):** starts after LangGraph 3; HITL review in the Reports screen. **Storage:** relational database for job profiles, JDs, candidates, parsed CV data, dimension scores, weights, final score, rank and reasons, sessions, transcripts, analyses, reports and LangGraph checkpoints; vector store for CV embeddings and the RAG sources (reference library, company policies, previous job profiles, email templates and, from 2 Oct 2026, the interview question bank — §4B-10). | Job profiles, F1, F2, F3 invitations, MCP integrations, RAG, LangGraph design | Matches the trainer answer that the JD/chatbot functionality is interviewer-side. **Calendar MCP** is external calendar integration, which the BID lists as out of scope unless chosen as F11: **needs written trainer approval, or present the Hiring Assistant with calendar scheduling as the F11 innovation feature.** Job-board posting still needs approval (§4B-2). Calendar and email providers must be listed in the README with the candidate data they receive (N18). Scores stay reproducible because LangGraph 2–4 are fixed workflows, not free agents (F2). |
| 9 | 2 Oct 2026 | **CV collection through Google Forms and Google Drive** (replaces the developer placing CVs by hand, §4B-3). The posted job includes a **Google Form** link; applicants submit their CV through the form; the uploaded CVs are saved to **Google Drive**; a backend **CV Collector service** fetches new CVs from Drive (Google Drive API) into the **CV intake directory**; the **CV Screening LangGraph** reads them from that directory when screening is started from the application. | F1 ingestion, external services, privacy | Real applicants' CVs would breach **N13/CN5**, so during development and the demo only the provided sample CVs or synthetic CVs are submitted through the form. Google Forms and Google Drive receive candidate data and must be listed in the README (N18). Drive credentials via environment variables only (N7). The intake directory stays git-ignored and on a Docker named volume (N14, D5); files still get type/size checks (N8). Google Forms file upload requires respondents to sign in with a Google account. |
| 10 | 2 Oct 2026 | **Hiring Assistant during the live interview.** The interview page includes the Hiring Assistant chat (LangGraph 1, same job thread). The interviewer can ask it for interview questions; it retrieves them by **RAG** from a **question bank** in the vector store (previous years' questions and other suitable questions for the role) and suggests them. The interviewer then asks the chosen questions to the candidate in the live call. | F3 interview page, LangGraph 1, RAG | Interviewer-only (N9): the candidate never sees the chat. Suggested questions do not change F5: the Q&A analysis still evaluates the questions actually asked in the transcript. The question bank must not contain candidate personal data. |

---

## 5. Functional Requirements — BID §5, pp. 11–15

### 5.1 Feature register

| ID | Name | Stage | Status |
|---|---|---|---|
| F1 | CV Screening & Requirement-Based Candidate Ranking | Pre | **Core / Must Have** |
| F2 | AI-Based Candidate Scoring | Pre | **Core / Must Have** |
| F3 | AI-Powered Video Interview | During | **Core / Must Have** |
| F4 | Real-Time Speech Recognition & Transcription | During | **Core / Must Have** |
| F5 | AI-Based Interview Question & Answer Analysis | Post | **Core / Must Have** |
| F6 | Consolidated Candidate Assessment | Post | **Core / Must Have** |
| F7 | Candidate Identification & Real-Time Profile Overview | During | **Stretch in BID; REQUIRED for this project by latest trainee instruction** |
| F8 | CV Claim Verification Through Interview Analysis | Post | **Stretch / Could Have** |
| F9 | Comprehensive Candidate Interview Scoring | Post | **Stretch / Could Have** |
| F10 | Interview Quality Assessment | Post | **Stretch / Could Have** |
| F11 | Trainee-Proposed Innovation Feature | Any | **Creative / Must Have** |

### 5.2 Pre-Interview

#### F1 — CV Screening & Requirement-Based Candidate Ranking [CORE]

**Purpose:** Automatically screen multiple candidates against a defined job requirement profile and return an explainable suitability ranking.

**All expected behaviours:**
- Accept job profile containing **required and preferred skills**, qualifications, minimum years of experience and additional selection criteria.
- Ingest **multiple CVs in one batch**; extract **contact details, education, work history, skills, certifications, project experience**. **Project-specific decision (§4B-3, updated by §4B-9):** the CV Collector service fetches CVs from Google Drive into the designated CV intake directory (git-ignored, Docker named volume), and the batch is read from there.
- Use **semantic understanding**, not literal keywords alone; e.g. “built REST services in Django” can evidence “Python web development.” Avoid inventing unsupported skills.
- Produce ordered ranking of candidates who remain after screening/hard-requirement gating, with relative suitability visible.
- For each candidate, state requirements **met / partially met / unmet**, with supporting CV evidence.
- Handle non-standard/multi-column layouts, missing sections and image-heavy/scanned documents safely; a bad CV must not crash the batch. **Trainer clarification now expects an OCR fallback when extractable text is unavailable:** `CV → Is text available? → Yes: text extraction / No: OCR → CV parsing → requirement match → screening results`. OCR still does not need to be perfect; failures must remain graceful and isolated to the affected CV.
- **Mandatory/hard requirement gate:** if a candidate fails any mandatory hard requirement, trainer clarification says that candidate should be **excluded from screening results and should not proceed to the next stage**. This overrides the earlier assumption that every candidate remains ranked with only a warning.
- For displayed requirement evidence, trainer clarification says an **AI-generated explanation is sufficient**; showing the exact original CV snippet is not mandatory. However, the underlying decision should still remain traceable to the candidate data because the BID requires explainability.

**Evidence to demonstrate:** Job profile + 20-sample batch + ranking + per-candidate requirement status and evidence + failure handling.

#### F2 — AI-Based Candidate Scoring [CORE]

**Purpose:** Produce an explainable, reproducible suitability score against the defined job profile.

**All expected behaviours:**
- Score **at least three distinct dimensions:** technical skills; relevant experience; academic/professional qualifications. Extra dimensions allowed.
- The BID requires **configurable per-dimension weights** so scoring can adapt by role. Trainer clarification additionally says the **AI should determine the weights based on the prompt**. Safest reading: weights may vary by job/prompt, but the chosen weights must be explicit, recorded and reproducible; manual recruiter editing is not separately confirmed as mandatory.
- Show **overall aggregate** and **individual dimension breakdown**.
- Use a **0–100 score scale** for candidate evaluation; this was explicitly confirmed by the trainer.
- In addition to the minimum dimensions (technical skills, relevant experience, qualifications), trainer clarification says the suitability score should also consider an **ATS-style CV–job-description matching score**.
- Provide short natural-language **justification for every dimension score**.
- Ensure **stable/reproducible** scores: identical CV + job profile must not materially change across repeated runs.
- **Persist** scores for future retrieval/merge into F6.

**Still not prescribed:** exact weight values, exact aggregate formula, exact ATS-score formula, or specific LLM/embedding model. The original BID required configurable weights; trainer clarification narrows this by saying the AI determines weights from the prompt.

**Pre-interview stretch:** None separately listed; original pre-interview extensions would belong to F11 and must meet its originality rule.

### 5.3 During-Interview

#### F3 — AI-Powered Video Interview [CORE]

**Purpose:** Integrated real-time **interviewer–candidate** browser video/audio call that captures conversation for AI analysis.

**All expected behaviours:**
- Browser-based live video and audio between interviewer and candidate.
- Session lifecycle: **create, schedule for a future date/time, join, conduct, end**. Trainer clarification confirms that future scheduling is required, while full external calendar integration remains optional/out of scope.
- After candidate selection, trainer clarification says the system should create and send a **unique interview link** tied to that candidate/session. The required delivery mechanism (email, in-app, etc.) is not specified in the Q&A. **Project-specific decision (§4B-4, updated by §4B-8):** the Hiring Assistant chatbot schedules the interview, books it through a **calendar MCP**, and sends the link by **email through MCP**, using an email template retrieved by RAG, after the interviewer confirms (HITL).
- The required interview topology for this phase is **1 interviewer + 1 candidate only**; panel interviews are not required.
- For demonstration, **two browser tabs on one computer/localhost are acceptable**; two physical machines are not required.
- If connectivity drops, trainer clarification requires the participant to **reconnect automatically to the same session** while preserving transcript already captured.
- Capture audio **continuously** throughout call and route into analysis/transcription pipeline.
- Link each session to **specific candidate** and **specific job requirement profile**.
- In-call controls: **mute, camera toggle, end session**.
- Gracefully handle network interruption; dropped frame must not terminate recording or lose transcript already captured.
- Persist session record with **start/end times and participants**.

**Interpretation guard:** “AI-Powered” does **not** expressly require an AI avatar or autonomous AI interviewer; source specifies human interviewer–candidate communication enhanced by AI capture/analysis.

#### F4 — Real-Time Speech Recognition & Transcription [CORE]

**Purpose:** Convert both parties' speech to a usable structured transcript during the interview.

**All expected behaviours:**
- Transcribe **during live session** with minimal perceptible lag.
- Attribute utterances to the correct speaker via **participant-specific metadata/channel separation** (e.g., Participant ID, User ID, Role = Interviewer/Candidate); trainer clarification confirms this satisfies speaker attribution without requiring mixed-audio AI diarisation.
- **Timestamp each utterance** for later evidentiary reference. Either elapsed timestamps (e.g., `00:15`) or actual clock time are acceptable.
- Structured **ordered sequence of speaker-attributed timestamped turns**, not one block of text. For overlapping speech, separate speaker-attributed entries with overlapping timestamps are acceptable.
- Persist and retrieve transcript after session.
- **English-only transcription is sufficient** for this project.
- Continuous/near-real-time streaming is required, but **WebSocket specifically is not mandatory**. Trainer clarification explicitly accepts Google Cloud Speech-to-Text Streaming API using gRPC.
- Remain stable with accented/overlapping speech and silence; imperfect accuracy acceptable if robust. Transcript correction/editing after STT remains unresolved because the trainer response did not answer that part directly.

#### F7 — Candidate Identification & Real-Time Profile Overview [REQUIRED FOR THIS PROJECT; STRETCH IN ORIGINAL BID]

- **This project must implement F7, including its face/voice-recognition capability, and must not exclude it.** The original BID allows face and/or voice recognition; the latest project instruction makes the F7 biometric-identification functionality mandatory for this submission even though the trainer Q&A had earlier deferred it.
- Identify interviewee with **face and/or voice recognition** matched against candidate records.
- On **confident match**, show compact interviewer profile: **name, headline experience, key skills, pre-interview score, areas flagged to probe**.
- Explicitly handle no-match/low-confidence; **never silently assume identity**.
- **Visible biometric consent**; protect storage/retention per N17.
- A reference biometric must exist before verification. The BID does not specify the enrolment mechanism, so the project must define a consent-based way to obtain/store reference face or voice data, or use trainer-provided reference data if later supplied. Session-ID lookup alone is **not biometric verification**.
- Trainer Q&A note: the written trainer answer said face/voice recognition was not required for that phase; however, the trainee has now explicitly confirmed that **F7 face/voice recognition is required for this project**, so this reference keeps it in scope.

### 5.4 Post-Interview

#### F5 — AI-Based Interview Question & Answer Analysis [CORE]

**Trainer clarification:** Transcribe the full interview, including greetings/small talk, but evaluate/score only **job-related questions and answers**. For technical/factual verification, one trainer answer explicitly requires **authoritative external documentation through RAG** rather than relying solely on the LLM's parametric knowledge. A later trainer answer is less specific, so this remains a clarification conflict; until resolved, treat the explicit RAG requirement as the safer requirement.

**Project-specific decision (§4B-5, updated 17 Oct 2026):** job-related answers are evaluated by the **LLM against the authoritative reference library (RAG)**, and company-related answers through **RAG** over company reference documents. This follows the trainer answer that requires RAG for technical verification; scoring company-related answers still goes beyond "score only job-related Q&A". **Confirm the company-related scoring with the trainer.**


**Purpose:** Determine how effectively candidate answered questions relevant to the job.

**All expected behaviours:**
- Segment transcript into **question–answer pairs** with each answer correctly associated to prompting question.
- Evaluate **at least**: (1) question relevance, (2) factual/technical accuracy, (3) completeness, (4) overall articulation quality.
- Map questions and answers to **specific job requirements**, making coverage gaps visible.
- Provide short **written justification per evaluation**, citing supporting transcript segment.
- Handle **follow-ups, clarifications and multi-part answers** sensibly.
- Identify job requirements **never explored** in interview.

**Distinction:** F5 requires per-answer analysis; a standalone numerical overall interview scoring framework is optional F9.

#### F6 — Consolidated Candidate Assessment [CORE]

**Purpose:** Combine pre-interview and post-interview findings into one explainable hiring-manager report.

**All expected behaviours:**
- Merge **CV screening**, **candidate scores** and **post-interview Q&A analysis** into coherent report.
- Present **overall suitability position backed by component scores**—not one opaque number.
- Summarise **strengths, weaknesses, evidence gaps and recommended further verification areas**.
- Make report **exportable or printable** (PDF, structured HTML or equivalent).
- Allow **side-by-side comparison of multiple assessed candidates for the same role**.
- Make **every conclusion traceable** to CV content or timestamped transcript segment.
- **Project-specific decision (§4B-7):** before the report is finalised, the interviewer reviews it (human-in-the-loop) and either approves it or requests changes.

#### F8 — CV Claim Verification Through Interview Analysis [STRETCH]

- Cross-reference CV claims against candidate's interview statements.
- Flag **inconsistencies, contradictions and asserted-but-unsubstantiated claims**.
- Clearly distinguish **actual contradiction vs unverified claim vs never-discussed claim**.
- Flags are **human follow-up prompts**, never accusations or automatic rejections.

#### F9 — Comprehensive Candidate Interview Scoring [STRETCH]

- Overall **interview-performance score distinct from CV-based F2 score**.
- Per-dimension evaluation across **technical competency, communication, response relevance, problem-solving approach, demonstrated experience depth, alignment with job requirements**.
- Show **dimension breakdown with supporting evidence**.

#### F10 — Interview Quality Assessment [STRETCH]

- Evaluate **interview process**, not only candidate.
- Assess **relevance/effectiveness of interviewer's questions, required competency coverage, consistency across candidates, overall interaction quality**.
- Suggest **actionable improvements**, including unexamined competencies, low-signal questions and imbalanced speaking time.
- Trainer Q&A additionally supports **rescheduling an interview when interview quality is assessed as bad**, rather than relying on that poor-quality session as sufficient evidence.

---

## 6. Original Innovation — BID §6, pp. 16–17

**F11 is mandatory** and must be an independently conceived *single* feature. In the original BID it is separate from optional F7–F10; **for this project only, F7 has been promoted to a required implementation**, while F8–F10 remain optional.

| ID | Requirement |
|---|---|
| C1 | **Originality:** own idea; cannot be F1–F10, a cosmetic variation, subset or rename. |
| C2 | **Relevance:** genuinely enhances recruitment/interview intelligence workflow. |
| C3 | **Written rationale (~300–500 words):** problem, beneficiaries, value added, why chosen over considered alternatives. |
| C4 | **Independent design:** trainee designs/implements alone; not trainer-specified. |
| C5 | **Working implementation:** functional live demonstration; mock-up/concept not enough. |
| C6 | **Integration:** coherent with main platform; not disconnected side module. |
| C7 | **Documentation:** clearly identify as “Innovation Feature” in README. |
| C8 | **Presentation:** demonstrate and justify in final presentation. |

**Assessed on:** real problem identification; genuine independent thinking; business-value articulation; deliberate prioritisation vs alternatives; sound working integration; scope discipline. Exactly **one** innovation required; extra ones do not add marks. Do not sacrifice Core to implement it. NFRs/technical constraints/privacy still apply.

**AI-use safeguard:** The innovation idea and independent judgement must belong to trainee (CN9/C4), even though AI coding assistance is allowed (AI1). Do not use this reference as a trainer-provided innovation specification.

---

## 7. Non-Functional Requirements — BID §7, pp. 18–20

### 7.1 Performance & Responsiveness

| ID | Mandatory expectation |
|---|---|
| N1 | **20-CV throughput:** parse, screen, score and rank batch within a defined time and record the **measured figure in README**. Trainer confirmed that a time limit exists, but the Q&A did **not provide the numeric threshold**; the proposed 5-minute figure was not explicitly approved. |
| N2 | Live transcription appears with **minimal perceptible delay**. No explicit millisecond target. |
| N3 | Video/audio remain usable and stable for typical interview. |
| N4 | Non-AI APIs respond promptly; long AI operations **asynchronous**, with progress/status rather than blocked request. |
| N5 | Tolerate **one active interview plus background CV processing simultaneously**. |
| N6 | External AI failure gives **clear error state**, not crash or silent data loss. |

### 7.2 Security

| ID | Mandatory expectation |
|---|---|
| N7 | Keys/secrets/connection strings via **environment variables**; no committed credentials; ship **`.env.example` placeholders**, never populated `.env`. |
| N8 | Validate **all API inputs** and check uploaded **type and size** before processing. File-size limit not specified. |
| N9 | Separate interviewer and candidate capabilities; candidate **cannot access scores/rankings/assessments** (enforce in backend, not just hidden UI). |
| N10 | Secure transport for exposed APIs/media; **document any local-development exceptions**. HTTP localhost may be a documented exception, not blanket permission for insecure network exposure. |
| N11 | **Pin dependency versions**, avoid unmaintained/unnecessary packages. |
| N12 | Client errors must **not disclose stack traces, filesystem paths, internal configuration or prompt content**. |

### 7.3 Candidate Data Privacy — **mandatory and explicitly assessed**

| ID | Mandatory expectation |
|---|---|
| N13 | Use only **20 provided sample CVs or created synthetic data**; never real CVs of non-consenting individuals. CN5 more strictly states real personal data prohibited for assignment. **Impact of §4B-2 and §4B-3:** CVs received from a real job-board posting would be real personal data, so only the provided sample CVs or synthetic CVs may be placed in the CV intake directory. **Impact of §4B-9:** for development and the demo, the Google Form is filled in with the provided sample CVs or synthetic CVs only; real applicants' CVs must not be collected. |
| N14 | No personal data in repository: **CVs, recordings, transcripts, personally identifying screenshots, DB dumps**. Add relevant paths to `.gitignore`; provided CVs **never in a public repository**. **Impact of §4B-3:** the CV intake directory must be in `.gitignore`. |
| N15 | Anonymise/redact **screenshots, README examples, slides, logs**. |
| N16 | **Minimise stored data**. Trainer clarification explicitly says raw audio/video **does not need to be stored**; capture/process it temporarily for transcription and discard the raw media after the required transcript has been generated. |
| N17 | Because F7 is required for this project, face/voice biometric data must be treated as particularly sensitive; **visible consent** and README explanation of **storage method/retention** are mandatory for the biometric flow. |
| N18 | README lists **external providers receiving candidate data** (LLM, transcription APIs), and **what is transmitted to each**. **Impact of §4B:** also list the email service used through MCP (candidate email address, interview link), the calendar service used through MCP (candidate email address, interview date and time) and the job board used through MCP (job description content). **Impact of §4B-9:** also list Google Forms and Google Drive (applicant name, email and CV file) and the Drive API access used by the CV Collector service. |
| N19 | Provide a means of deleting a candidate **and associated data**. Trainer clarification confirms a **backend API endpoint is sufficient**; no UI delete button is required. |
| N20 | Score using **job-relevant criteria only**; do not use, infer or store **age, gender, ethnicity, nationality, religion or marital status as scoring inputs**. Trainer Q&A says the evaluation should simply be based on defined job-related criteria/qualifications, but this does **not** weaken the BID prohibition on protected attributes. Document known fairness limitations in README. |

### 7.4 Reliability, Maintainability & Usability

| ID | Mandatory expectation |
|---|---|
| N21 | Reproducible clean-machine startup via **documented Docker commands only**. |
| N22 | **Structured logs** for key operations/failures; no personal data/secrets in logs. |
| N23 | Clear separation of concerns, consistent structure/meaningful names, no large commented-out/dead code blocks. |
| N24 | README with **purpose, architecture, setup, configuration, usage, known limitations**; FastAPI endpoints via **OpenAPI**. |
| N25 | UI navigable without verbal explanation; progress on long tasks; understandable non-technical errors. |
| N26 | Candidate records, scores, transcripts and assessments must survive application restart. Trainer clarification additionally requires **persisting long-running LangGraph workflow state so interrupted processing can automatically resume from where it stopped**, retaining completed work and continuing remaining work without recruiter re-run. |

---

## 8. Technical Requirements & Constraints — BID §8, pp. 21–23

### 8.1 Mandated stack

| Layer | Required | Nuance |
|---|---|---|
| Backend/AI language | **Python** | All backend and AI logic; recent stable Python **3.10+ recommended**. |
| Agent/orchestration | **LangGraph** | Multi-step explicit graphs, state, nodes, transitions. Single wrapper node around one LLM call **not credited**. |
| API | **FastAPI + Pydantic/OpenAPI** | Backend services exposed via FastAPI; request/response validation; auto API documentation. |
| Containers | **Docker** | Complete app in containers; multiple services via **Docker Compose**. |
| Source control | **GitHub** | Full incremental history. |
| Frontend | **Trainee choice** | Justify in README and presentation. |

**Deviation:** Mandated-stack changes need **written trainer approval during Phase 1**, documented in clarification record.

**Project addition (§4B-6):** MCP is used for the job-board, calendar and email integrations (§4B-8). This adds to the stack rather than replacing any mandated technology.

### 8.2 LangGraph usage expectations

- Model reasoning as explicit **state, nodes and edges**.
- Apply where meaningful: **CV analysis, interview response evaluation, consolidated assessment generation**.
- Carry explicit state through steps; do not rebuild all context for each call.
- Include **error handling and retry paths** within graphs.
- Explain graph topology, why each node exists, and what state it receives/passes.
- **One-node LLM-call graph does not satisfy** requirement.
- **Project-specific decision (§4B-7):** human-in-the-loop review points (LangGraph `interrupt`) pause the Hiring Assistant (LangGraph 1) and the Final Assessment workflow (LangGraph 4) until the interviewer approves, edits or rejects; in the Hiring Assistant the JD must be approved before the `post_to_job_board` tool posts it via MCP; the paused state is checkpointed and resumes afterwards.
- **Project LangGraph structure (§4B-8):** LangGraph 1 is a **tool-calling agent** (Hiring Assistant chatbot); LangGraphs 2–4 are **fixed workflows** so scoring and assessment stay reproducible and traceable.
- **Project LangGraph design patterns:** sequential chains for ordered steps; conditional edges for routing (validation, hard-requirement gate, question type, traceability, review outcome); parallel branches for independent work (JD checks, F2 dimension scoring, assessment analyses) and `Send` fan-out to subgraphs for per-CV and per-Q&A-pair processing; iterative loops for bounded retries (max 2) and human-review feedback.
- The BID does **not** prescribe exact graph topology or require every trivial backend action to become a LangGraph node.

### 8.3 Dockerisation D1–D8

| ID | Requirement |
|---|---|
| D1 | Backend, frontend, supporting database/cache/vector store **run in containers**. |
| D2 | Reviewer starts whole app with **one documented command**. |
| D3 | **Docker Compose** defines services, networks, volumes and dependencies. |
| D4 | All configuration by **environment variables**; `.env.example`, no populated `.env`. |
| D5 | **Named volumes** for data persistence across container restarts. |
| D6 | Verify clean-machine startup without prior project artefacts or cached local dependencies. |
| D7 | Appropriate images, `.dockerignore`, avoid unnecessarily large images. |
| D8 | README documents commands to **build, run, stop, reset**. |

### 8.4 GitHub G1–G8

| ID | Requirement |
|---|---|
| G1 | Use/maintain the designated **BJIT GitHub repository/account** and share it with the trainer team before deadline. Personal GitHub accounts may be added as collaborators for development/remote access, but project code/commits stay in the designated BJIT repository. |
| G2 | Complete README: **name, positioning, Core/attempted Stretch/Innovation list, architecture, tech stack and rationale, prerequisites, setup/run, configuration reference, usage walkthrough, privacy, known limitations**. |
| G3 | **Incremental, meaningful commits** throughout the **confirmed 20-working-day project**; no single final bulk commit. |
| G4 | **Descriptive specific commit messages**, not “update,” “fix,” “wip.” **BJIT commit-message guideline applies — see §8.4.1.** |
| G5 | Sensible branching encouraged; default branch stays working. |
| G6 | `.gitignore` and repository hygiene: **no secrets, personal candidate data, virtual envs, build artefacts, IDE configuration**. |
| G7 | Clarification document, WBS, innovation rationale committed (ideally under **`/docs`**); §10.3 says documentation deliverables **must** be under `/docs`. |
| G8 | Tag final evaluated commit, e.g. **`v1.0-final`**. |

#### 8.4.1 BJIT Git commit message guideline (project standard)

Source: BJIT training slides "Git Commit Message Guideline" (pp. 10–11). All commits in the project repository follow this format.

**Structure:**

```
<type>(<scope>): <summary>

- <body bullet>
- <body bullet>

<footer>
```

| Part | Rule |
|---|---|
| **Type** | Purpose of the commit, e.g. `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`. |
| **Scope** (optional) | Module, component or area affected, e.g. `readme`, `cv-screening`, `api`. |
| **Summary** | Short (**50 characters or less**), written in the **imperative mood** (e.g. "add", "fix", "update"). |
| **Body** (optional) | Separated from the summary by a **blank line**; wrapped at **72 characters or less**; bullet points start with a hyphen and a space (`- `). Explains changes the summary cannot fully describe. |
| **Footer** (optional) | Separated from the body by a **blank line**; references the Redmine task. |

**Footer keywords (Redmine):**

| Keyword | Meaning |
|---|---|
| `Fixes #redmine-id` | The commit fixes a bug. |
| `Refs #redmine-id` | The commit continues a task (a task may need several commits). |
| `Closes #redmine-id` | The last commit of the task; the task should be closed. |

**Examples:**

```
fix(calendar): add calendar.h file to fix the build error

Without this file, it gives error - calendar.h file not found.

Refs #1234
```

```
docs(readme): add README skeleton

- Add product name and positioning statement
- Add required sections: features, architecture, setup, privacy

Refs #<redmine-id>
```

**Command line:** `git commit -m "<summary>" -m "<body>" -m "<footer>"` (each `-m` adds a blank line between parts). A GUI tool may also be used.

**Note:** slide 10 says the summary is "Capitalized", while the slide 11 examples use lowercase after the colon (e.g. `fix(calendar): add …`). This project follows the slide 11 examples (standard Conventional Commits style) unless the trainer asks otherwise.

### 8.5 Sample data

- **20 supplied CVs** for development, test and final presentation; varied layout/format/completeness.
- **Final demo must use provided 20-CV set** unless otherwise agreed.
- May create additional **synthetic** CVs for edge cases; place committed synthetic fixtures under clearly marked `test-data/`.
- **Do not commit provided CVs to a public repository**; follow N14 and personal-data rules.

### 8.6 Recommended, **not mandated**, implementation choices

- Relational/document DB for candidate/session/assessment persistence.
- Vector store for semantic CV matching.
- WebRTC-based video.
- Managed or self-hosted speech-to-text and diarisation.
- Background job handling for lengthy AI work.
- Automated tests of core business logic.

**Key distinction:** the *capability* can be mandatory even when a suggested *technology* is optional. E.g., semantic matching mandatory but vector DB optional; live video mandatory but WebRTC as specific implementation optional; persistence mandatory but PostgreSQL as a brand not specified.

---

## 9. Project Phases, Pacing & Milestones — BID §9, pp. 24–26

> **Timeline clarification resolved for this project:** use **20 working days**. The trainee confirmed **Day 1 = 28 September 2026**, and trainer Q&A confirms **all documents and code are due by 27 October 2026**. Exact Day-number-to-calendar-date mapping should follow the programme's actual working-day/holiday calendar. The following table remains the BID's indicative Day 1–20 pacing, not an AI-authored WBS or trainee's independent plan.

### 9.1–9.2 Phase 1 (Days 1–3) — source-issued activities

| Day | Focus | BID expected outputs |
|---|---|---|
| 1 | Read BID/domain research; identify ambiguous/conflicting requirements; survey video/transcription/CV parsing tech | Draft clarification questions and initial technology research notes. |
| 2 | Ask trainer questions; record answers/assumptions; conceptualise architecture/LangGraph; choose stack; name/positioning | Clarification document with trainer responses, high-level architecture, product name/rationale. |
| 3 | Independently decompose/estimate/sequence tasks; risks/dependencies/mitigations; GitHub skeleton | WBS aligned to the **confirmed 20-working-day project**, risk register, initialized repo, Phase 1 gate review. |

### 9.3 Phase 2 (Days 4–20) — **BID's example schedule**, not a generated individual WBS

| Day(s) | Source-assigned focus and expected output |
|---|---|
| 4–5 | Foundation: repo structure, FastAPI health route, Dockerfile/Compose, database schema/models, CV upload/parser, basic LangGraph state/graph → containerised skeleton and working CV ingestion. |
| 6–8 | F1/F2: job profiles, semantic matching, ranking, per-dimension weighted scoring/justifications and UI → demo on 20 CVs. |
| 9–11 | F3: video UI, session lifecycle, live A/V, continuous audio, candidate/job linkage and session persistence → full live interview. |
| 12–13 | F4: STT, diarisation/channel separation, timestamped structured/live transcript, storage/retrieval → saved speaker-attributed transcripts. |
| 14–15 | F5/F6: Q&A pairs, answer criteria, requirement coverage, final report/export, candidate comparison → **all six core features working end-to-end**. |
| 16–17 | F11: final concept, 300–500-word rationale, implement/integrate/test → innovation functional and documented under `/docs`. |
| 18 | BID originally places optional F7–F10 here only if Core is complete. **Project-specific override:** F7 face/voice recognition is required and therefore cannot be treated as an optional leftover; F8–F10 remain optional. |
| 19 | Full test with 20 CVs, clean-machine Docker, README, diagram, anonymised demo assets, rehearse → release candidate/docs/demo. |
| 20 | Bug fixes/freeze, final tag, repo submission, live presentation and Q&A. |

### 9.4 Fixed milestone/gate register

| Gate | When | Acceptance |
|---|---|---|
| M1 | End Day 3 | Clarification, name, WBS submitted/reviewed; repo initialized. |
| M2 | End Day 8 | F1/F2 demonstrate on sample set. |
| M3 | End Day 13 | F3/F4 demonstrate complete video interview + transcript. |
| M4 | End Day 15 | All F1–F6 work end-to-end. |
| M5 | End Day 17 | F11 implemented/integrated and documented with rationale. |
| M6 | End Day 19 | Clean-machine Docker verified, docs complete; release candidate. |
| M7 | Day 20 | Tagged repo submitted and presentation delivered. |

---

## 10. Deliverables and Submission — BID §10, pp. 27–28

**All listed deliverables mandatory unless marked otherwise.** Section §13's no-AI rules govern the WBS and SRS regardless of whether this reference lists them; see §13 for the trainee-reported diagram permission.

### 10.1 Phase 1 due end Day 3

| ID | Deliverable | Acceptance |
|---|---|---|
| P1.1 | Proposed name/positioning | Name + one-line positioning + **2–4 sentence** rationale; subsequently consistent. |
| P1.2 | Clarification document | Ambiguities, questions, actual trainer responses, assumptions if unanswered; quality over sheer count. |
| P1.3 | WBS | **Trainee independently authors** hierarchical tasks, estimates, dependencies, sequencing over the **confirmed 20-working-day timeline**, and definition of done per task. AI must not generate this WBS. |
| P1.4 | High-level architecture outline | Component diagram, proposed justified stack, intended LangGraph agent design. The trainee reports permission to use AI for the architecture and workflow diagrams (§13). |
| P1.5 | Risk register | Technical/schedule risks, likelihood, impact, mitigation. |
| P1.6 | Initialized repo | Structure, shared with trainers, README skeleton, functioning `.gitignore`. |

### 10.2 Phase 2 due end Day 20

| ID | Deliverable | Acceptance |
|---|---|---|
| P2.1 | Working Dockerised app | BID minimum is clean-machine documented startup with **F1–F6 and F11**. **Project-specific override additionally requires F7 face/voice candidate recognition to be working and demonstrable.** |
| P2.2 | Final GitHub repo | Full source, incremental commits, tagged final release. |
| P2.3 | README | All G2 fields plus all requirements explicitly demanding documentation. |
| P2.4 | Innovation rationale | **300–500 words**, committed under `/docs`. |
| P2.5 | Updated WBS/plan | **Independently authored**, planned vs actual progress, committed under `/docs`. |
| P2.6 | Final architecture docs | Architecture diagram and explanation of LangGraph graph **as built**. The trainee reports permission to use AI for the architecture and workflow diagrams (§13). |
| P2.7 | Privacy/data-handling note | External recipient services/data; stored fields; retention/deletion approach; known fairness limitations. |
| P2.8 | Final presentation | **20–30 minutes**; problem, name/position, architecture, demo **20 sample CVs**, demonstrate the project's required F7 biometric identification, innovation rationale, challenges/lessons, Q&A. |
| P2.9 | Presentation deck | Supporting slides; all demonstration material anonymised. |

### 10.3 Submission standards

- All deliverables are due by **27 October 2026**, corresponding to the confirmed 20-working-day project; late penalty remains at panel discretion.
- Documentation deliverables committed to **`/docs`**, not sent separately.
- App starts **without trainee intervention** following documented steps; “works on my machine” insufficient.
- No candidate personal data in submitted repo.
- Trainee able to explain **any part** of submitted codebase.

---

## 11. Evaluation, Bonus, Rubric & Deductions — BID §11, pp. 29–31

### 11.1 Regular marks = 100

| ID | Evaluation | Marks | Assessed |
|---|---|---:|---|
| E1 | Phase 1 | 10 | Requirement depth, clarifications, detailed/realistic WBS, risks, architecture thinking. |
| E2 | F1/F2 Pre-Interview | 15 | Screening accuracy, semantic matching, ranking, dimension scoring/weights/explanations. |
| E3 | F3/F4 During-Interview | 15 | A/V stability, capture, transcript quality, speaker attribution, structure. |
| E4 | F5/F6 Post-Interview | 15 | Q&A pairing, evaluation, requirement coverage, consolidation, evidence traceability. |
| E5 | F11 Innovation | 10 | Originality, relevance, rationale, priorities, implementation/integration. |
| E6 | Name/product thinking | 5 | Fit/memorability, positioning/rationale, consistent identity. |
| E7 | Engineering quality | 10 | Meaningful LangGraph, API/architecture, code, separation, errors. |
| E8 | Docker/GitHub | 8 | One-command startup, clean-machine, Compose, commits, hygiene, README. |
| E9 | NFRs | 5 | Performance, security, **privacy and fairness**. |
| E10 | Presentation/demo | 7 | Communication, live demo, justified decisions, technical Q&A. |
| | **TOTAL** | **100** | |

**No source-assigned split of the 15 marks within F1 vs F2, F3 vs F4, or F5 vs F6**—do not invent equal allocations.

### 11.2 Stretch bonus — max +10, **only when all six Core work**

| Feature | Maximum | Additional condition |
|---|---:|---|
| F7 | +3 | Original BID bonus allocation; N17 consent/biometric privacy. **F7 is nevertheless required for this project by the latest project instruction.** |
| F8 | +3 | Flags presented as human follow-up prompts. |
| F9 | +2 | Per-dimension breakdown. |
| F10 | +2 | Actionable recommendations. |

### 11.3 Feature-level scoring bands (describes *grading*, not a mandated model scoring algorithm)

| Band | Scale | Meaning |
|---|---|---|
| Excellent | 90–100% | Complete, robust edge-case handling, integrated, explainable, evidence-backed. |
| Good | 75–89% | Main path fully works; minor edge/transparency gaps. |
| Satisfactory | 60–74% | Works on happy path only; shallow analysis or weak explanation. |
| Partial | 40–59% | Implemented but unreliable/incomplete/poor integration. |
| Minimal | 1–39% | Attempted but nonfunctional or placeholder/mock. |
| Not delivered | 0% | Absent. |

### 11.4 Deductions and penalties

| Condition | Consequence |
|---|---|
| Fails to start clean-machine using documented commands | Up to **−10** marks. |
| Secrets/credentials/API keys committed | Up to **−8**. |
| Candidate personal data committed | Up to **−8**. |
| Single bulk commit / no meaningful history | Up to **−5**. |
| Stretch work while Core incomplete | Up to **−5** (scope management). |
| Innovation duplicates/trivially varies F1–F10 | **E5 innovation marks forfeited**. |
| Evidence work not trainee's or inability to explain code | Panel referral; **possible disqualification**. |
| Late submission | Panel discretion. |

### 11.5 Characteristics of strong submission

Complete Core before scattered unfinished extra features; trace every AI score/flag to evidence; defend genuine multi-node LangGraph; effortless Docker setup; visible original requirement analysis/WBS; valuable original innovation and rationale; candid README limitations rather than overclaims.

---

## 12. Assumptions, Constraints & Known Risks — BID §12, pp. 32–33

### 12.1 Assumptions A1–A10

| ID | Issued assumption |
|---|---|
| A1 | Trainee knows Python, REST API concepts and basic containers, independently researches unfamiliar libraries. |
| A2 | Machine can run Docker and local video. |
| A3 | AI/STT services or approved alternatives available during assignment. |
| A4 | 20 representative sample CVs provided **at start Phase 1**. |
| A5 | Trainer available during Phase 1 for reasonably timely clarifications. |
| A6 | Final interviews **simulated** with mock candidates/sample data. |
| A7 | **English only** is sufficient for CVs and interview transcription/analysis, per trainer clarification. |
| A8 | Imperfect AI acceptable; grade design/transparency/robustness, not benchmark accuracy. |
| A9 | **Single concurrent interview** sufficient for demo (while N5 still demands background CV processing during interview). |
| A10 | Raise blockers promptly. |

### 12.2 Constraints CN1–CN10

| ID | Binding constraint |
|---|---|
| CN1 | **20 working days confirmed for this project**. Day 1 is **28 September 2026** and all code/documents are due **27 October 2026**. |
| CN2 | **Solo**; general concept discussions allowed, collaboration on design/code and sharing implementations prohibited. |
| CN3 | Python, LangGraph, FastAPI, Docker non-negotiable without documented trainer approval. |
| CN4 | Run locally in Docker; cloud deployment neither required nor credited. |
| CN5 | Only provided sample CVs or trainee-made synthetic data for dev/demo; **real personal data prohibited**. |
| CN6 | All §7.3 privacy requirements mandatory/graded. |
| CN7 | External AI risks: costs/rate limits/availability; design failure handling, document encountered limits. |
| CN8 | Out-of-scope work not credited, may be penalised. |
| CN9 | Innovation trainee's own; AI coding assistants may help coding, trainee understands/explains all work. |
| CN10 | Feature not **live-demonstrable** at presentation treated as **not delivered**. |

### 12.3 Known risks and BID-suggested mitigations

| Risk | BID likelihood | BID mitigation |
|---|---|---|
| Live audio/video pipeline harder than estimated | **High** | Prototype risky component **Days 4–5**, not Day 9. |
| Poor speaker diarisation | **Medium** | Consider separate participant audio channels instead of mixed stream. |
| Non-standard CV fails extraction | **High** | Handle failure/log/skip individual CV, preserve batch. |
| AI service rate/cost limit reached | **Medium** | Cache during development, batch requests, avoid re-running full pipeline. |
| Over-engineering first feature | **High** | Thin complete pipeline first; deepen later; track daily against independently written WBS. |
| Docker local-only success | **Medium** | Clean-environment verification **by Day 19, not Day 20**. |

---

## 13. AI Usage Guidelines — BID §13, p. 34

**These restrictions apply in both phases.**

| ID | AI permitted for |
|---|---|
| AI1 | Coding. |
| AI2 | UI design. |
| AI3 | Paid LLM/local LLM. |
| AI4 | Speech-to-text. |
| AI5 | Video feed collection. |

| ID | Must be completed **without any AI support** |
|---|---|
| NA1 | Work Breakdown Structure (**WBS**). |
| NA2 | Software Requirements Specification (**SRS**). |
| NA3 | **Workflow diagram**. |

**Accountability:** Any AI-assisted code/artefact must still be completely understood and explainable by trainee (CN9). This document is a **reference summary of the issued BID plus trainer clarifications** and must **not** be used as a generated SRS/WBS/workflow diagram or submitted as one. Trainer clarification confirms that a **separate SRS is a required deliverable**, but it must be prepared **without AI support**. **Trainee-reported permission:** the trainee states that permission has been received to use AI for the **architecture diagram and the workflow diagram**. The WBS and SRS remain without AI support. Keep a record of this permission (e.g. in the clarification document) in case the panel asks.

---

## 14. Ambiguities / Questions Requiring Written Trainer Clarification

> These are **observations about source gaps/conflicts**, not claimed trainer answers, adopted assumptions, or the trainee's completed P1.2 document. The trainee must independently decide what to raise and record actual responses during Phase 1.

| Topic | Document evidence and open question |
|---|---|
| **Timeline** | **Resolved:** use 20 working days. Project started **28 September 2026** and all documents/code are due **27 October 2026**. |
| **Formal SRS** | **Resolved in trainer Q&A:** a separate SRS **must be submitted**. It remains subject to §13 NA2: no AI support for preparing the SRS. Exact template/format can still be confirmed if the programme provides one. |
| **Workflow vs architecture diagrams** | **Resolved by trainee-reported permission:** AI may be used for the architecture and workflow diagrams. WBS and SRS remain no-AI. |
| **Job-board publishing via MCP (§4B-2)** | BID §4.2 excludes job-board publishing and CN8 warns out-of-scope work may be penalised. Get **written trainer approval**, and confirm that only a demo/test posting is used so no real applicant CVs are collected (N13/CN5). |
| **CV collection (§4B-3, §4B-9)** | **Resolved by project decision (2 Oct 2026):** CVs are submitted through a Google Form linked in the job post and saved to Google Drive; a backend CV Collector service fetches them into the CV intake directory. For development and the demo, only the provided 20 sample CVs (plus any synthetic test CVs) are submitted through the form (N13/CN5). Google Forms file upload requires respondents to sign in with a Google account, which should be checked during setup. |
| **F5 company-related scoring (§4B-5)** | Resolved 17 Oct 2026 for technical answers: both job-related and company-related answers are now checked through RAG (job answers against the authoritative reference library), as the trainer answer requires. Still to confirm: whether company-related answers may be scored at all. |
| **F7 status** | This reference records F7 face/voice recognition as required for this project, but the project manager has asked for face/biometric parts to be left out of the architecture and workflow diagrams. Confirm whether F7 is still being implemented; if it is dropped, update §0, §3.3, §5.3, §7.3 N17, §9.3, §10.2 and §15. |
| **Calendar MCP (§4B-8)** | The Hiring Assistant books interviews through a calendar MCP. The BID lists external calendar integration as out of scope unless chosen as F11. Get **written trainer approval**, or present the Hiring Assistant with calendar scheduling as the F11 innovation feature. |
| **F3 scheduling** | **Resolved:** future date/time scheduling is required; external calendar integration is not required. Unique candidate-specific interview links are expected after selection. |
| **F1 scanned files** | **Resolved at requirement level:** OCR fallback is expected when text is unavailable. Exact OCR engine/accuracy threshold remains an implementation choice. |
| **Numeric targets** | BID says “reasonable” 20-CV throughput, “minimal perceptible” transcription delay, “quick” non-AI APIs and typical interview stability, without hard limits; ask whether trainer has test thresholds. |
| **F1 ranking vs F2 scoring** | Still not clearly resolved. One Q&A row proposes F1 ranking by separate criteria such as number of met requirements, but the trainer-answer cell is blank; a later row only says the answer was already given above. Do **not** assume F1 must rank by F2 aggregate until trainer confirms. |
| **N1 numeric throughput threshold** | Trainer confirmed a time limit exists, but did not provide the actual threshold. The proposed 5-minute value was not explicitly accepted. |
| **Transcript correction** | Q&A asked whether interviewer can correct STT errors and whether F5 should use corrected text; trainer only said Google STT is good enough. Correction workflow remains unspecified. |
| **F6 side-by-side evidence detail** | Q&A did not clearly answer whether comparison view must display evidence side by side; BID still requires evidence-backed conclusions and candidate comparison. |
| **F5 RAG reference policy** | One trainer answer explicitly requires **authoritative external documentation through RAG** for technical answer verification; a later answer says the LLM evaluates interview responses and criteria without explicitly mentioning RAG. Treat RAG as the stronger current clarification unless trainer resolves the inconsistency. |
| **Assessment score aggregation** | F2 now uses a required 0–100 scale and should include ATS-style CV–JD matching. Exact weight values/formula and overall CV+interview aggregation are still not prescribed. Trainer says AI determines weights from the prompt. |
| **Candidate/role data and privacy** | Distinguish synthetic fixtures allowed under `test-data/` from provided CVs barred from public repo and all real personal data barred. Confirm distribution mechanism for evaluation CVs if needed. |
| **F7 biometric enrolment/reference data** | F7 is required for this project, but the source set still does not define how reference face/voice data is collected. A consent-based enrolment/reference-data flow or trainer-provided reference data is needed; exact mechanism remains a design/clarification point. |
| **Job-description chatbot visibility** | Trainer answer indicates this is interviewer-side, but wording about who can see which video/chatbot view is unclear. Do not interpret it as cancelling the F3 requirement for a two-party interview; clarify UI visibility only if it affects implementation. |
| **F10 rescheduling trigger** | Q&A supports rescheduling when interview quality is bad, but no threshold/automatic trigger is specified. |

---

## 15. Cross-Requirement Acceptance Index (for reviewing project status, **not a trainee WBS**)

| Area | Must show by final evaluation | Source IDs |
|---|---|---|
| Pre-interview | **Multiple job profiles** created through the **Hiring Assistant chatbot** (project decision); LLM-assisted job-description generation, with RAG used when the chatbot decides it is needed (project decision); CV screening started separately from the application (not by the chatbot); interviewer approval of the JD through a **human-in-the-loop** step (project decision); JD posted to a job board **through MCP** after approval (project decision, needs trainer approval); CVs submitted via a **Google Form**, saved to **Google Drive** and fetched by the **CV Collector service** into the CV intake directory (project decision); 20-CV batch; text extraction + OCR fallback; semantic requirement matches; mandatory-requirement gate; explained rank; F2 0–100 scoring with ATS-style CV–JD component; reproducibility; saved scores. | F1, F2, B1/B2, N1, N26 + trainer Q&A + project-specific decision |
| Video/transcript | 1-on-1 interviewer/candidate session; interviewer can ask the **Hiring Assistant** on the interview page for **RAG-suggested questions** from the question bank (project decision §4B-10); future scheduling; candidates chosen and interviews scheduled through the **Hiring Assistant chatbot**, booked via **calendar MCP** and the unique link **emailed through MCP** with a RAG-retrieved template after interviewer confirmation (project decisions; calendar needs trainer approval); automatic reconnect; capture/controls/job+candidate linkage; participant-metadata speaker attribution; English near-real-time transcript with timestamps; raw media discarded after transcription. | F3, F4, N16, A7/A9, N2/N3/N5/N26 + trainer Q&A |
| Candidate identification | **Required project override:** F7 face/voice biometric identification, confident match profile display, explicit low-confidence/no-match handling, consent and biometric retention/storage safeguards. | F7, N17 + project-specific instruction |
| Post-interview | Correct Q&A pairing and four quality dimensions; job-related answers evaluated by the LLM against the authoritative reference library and company-related answers against company documents, both via RAG (project decision of 17 Oct 2026; company-related scoring pending trainer confirmation); mapped/gap requirements; cited evidence; interviewer **human-in-the-loop** review of the final report (project decision); export/print final assessment and side-by-side comparison. | F5, F6, B3–B5 |
| Innovation | ONE genuinely original integrated live feature, 300–500-word reasoned document, README and demo. | F11, C1–C8, P2.4, E5 |
| Privacy | Synthetic/provided data; safe Git repo/screenshots/logs; minimisation, provider disclosure, backend data deletion, job-related fair scoring and noted limitations; **biometric consent/storage/retention required because F7 is in scope for this project**. | N13–N20, CN5/6 |
| Engineering/delivery | Meaningful LangGraph, FastAPI/Pydantic/OpenAPI, responsive async AI, graceful errors, access separation, persistent Docker services, clean-machine one-command startup, complete GitHub docs and commits/tag in the designated BJIT repository (personal collaborator accounts allowed). | N4/N6–N12/N21–N26, D1–D8, G1–G8 + trainer Q&A |
| Presentation | Live demo all functions, provided sample CVs, own innovation, clear technical answers; no personal identifying materials; meet deadline. | P2.8–P2.9, CN10, E10 |

## 16. Distinctions That Must Not Be Lost in a New Chat

1. **F1 vs F2:** F1 extracts/screens/semantically matches, applies mandatory-requirement gating, explains and ranks; F2 supplies 0–100 numerical CV-based suitability scoring, including required dimensions plus ATS-style CV–JD match, and persists results. **The exact relationship between F1 ranking order and F2 aggregate score is still not explicitly resolved by trainer Q&A.**
2. **F3 vs F4:** F3 video/audio session and capture; F4 live speech recognition + speaker-attributed timestamped transcript.
3. **F5 vs F9:** F5 mandatory per-Q&A qualitative evaluation; F9 optional separate *comprehensive numeric interview score*.
4. **F6 vs F8:** F6 mandatory consolidated report; F8 optional CV/interview claim consistency checking with careful flag categories.
5. **F5 vs F10:** F5 evaluates candidate's answers; F10 optionally evaluates interviewer/process and actionability.
6. **F7 vs session lookup:** F7 face/voice recognition is **required for this project**. Biometric verification needs prior consented reference data; linking an interview session to candidate ID **does not by itself verify the face/voice**.
7. **Job profile vs job board:** Configuring job requirements is required; the BID excludes publishing/sourcing/job portals. The project has decided to post the JD through MCP (§4B-2), which needs written trainer approval and must not bring real applicant CVs into the system.
8. **Create interview vs calendar integration:** Basic session creation required; external automated calendaring excluded unless F11. The project's calendar MCP (§4B-8) therefore needs trainer approval or must be the F11 feature.
9. **Local Docker vs external AI API:** Platform runs locally; approved external model/STT APIs may still be used, with privacy disclosure and failure handling. Cloud *deployment* not required/credited.
10. **Optional tool vs mandatory result:** Database brand, vector DB, WebRTC, STT vendor, job runner and test framework optional; corresponding functional outcomes/persistence/live call/transcript/responsiveness are mandatory.
11. **Source-scoring vs grading rubric:** Model suitability score method is not mandated by feature-evaluation percentage bands in §11.3.
12. **20 working days:** The timeline conflict is resolved for this project: **20 working days**, starting **28 September 2026**, with all code/documents due **27 October 2026**.
13. **SRS:** A separate SRS is required, but must be prepared without AI assistance.
14. **AI boundaries:** Explaining the issued requirements does not authorise AI to generate the trainee's WBS or SRS. AI may be used for the architecture and workflow diagrams under the trainee-reported permission.

---

## 17. Source Reference Map

| Source pages | Content |
|---|---|
| 1 | Cover, assignment metadata and **conflicting 17-day schedule** |
| 2–3 | Table of contents |
| 4 | Purpose/audience |
| 5–6 | Business context, stages, product naming |
| 7–8 | Business/learning objectives, success conditions |
| 9–10 | In-scope, excluded scope, thin-slice advice |
| 11–15 | F1–F10 acceptance and F11 feature register |
| 16–17 | Innovation C1–C8, assessment and constraints |
| 18–20 | N1–N26 |
| 21–23 | Mandated stack, LangGraph, D1–D8, G1–G8, sample data, optional implementation choices |
| 24–26 | Body's 20-day plan, source pacing and milestone gates |
| 27–28 | P1.1–P1.6; P2.1–P2.9; submission standards |
| 29–31 | E1–E10 marks, stretch credit, grading rubric, deductions, strong-submission criteria |
| 32–33 | A1–A10, CN1–CN10, known risks |
| 34 | AI use AI1–AI5, no-AI NA1–NA3 |
| Trainer Q&A sheet (25–28 Sep 2026) | Written clarifications on technology, GitHub, OCR, hard-requirement screening, scoring, video/transcription, authentication, roles, scheduling, multiple jobs, LangGraph persistence, SRS, F5/RAG and other implementation expectations. |
| Latest trainee project instruction (28 Sep 2026) | F7 face/voice recognition is required for this project; use a 20-working-day timeline starting 28 Sep 2026. |
| Trainee project decisions (28 Sep–2 Oct 2026) | Hiring Assistant chatbot (LangGraph agent) with calendar and email MCP scheduling and three background workflows (§4B-8); RAG for JD generation; JD posting to a job board via MCP; Google Form → Google Drive → CV Collector service → CV intake directory (§4B-9); Hiring Assistant suggests interview questions from a RAG question bank during the live interview (§4B-10); interview-link email via MCP; F5 LLM/RAG split; human-in-the-loop review in the LangGraph workflows; permission for AI-assisted architecture and workflow diagrams (§4B, §13). |

**End of standalone BID + trainer-Q&A requirements reference.**
