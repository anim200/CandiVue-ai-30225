# CandiVue AI – Instructions for Claude

## Project
- CandiVue AI: AI-powered recruitment and interview platform (BJIT AI Trainee final project, due 27 Oct 2026).
- Repository: candivue-ai-30225 (BJIT GitHub).
- Source of truth for requirements: docs/requirement.md (including project decisions in §4B).
- Progress and next steps: docs/PROJECT_STATUS.md.
- Designs: docs/diagrams/ (Fig 1 high-level, Fig 2 detailed architecture, Fig 3–7 LangGraphs 1–5);
  source: docs/diagrams/src/build_diagrams.py.

## Mandatory stack
- Python, FastAPI + Pydantic (OpenAPI docs), LangGraph, Docker Compose, PostgreSQL, vector store.
- LangGraph 1 = Hiring Assistant chatbot (tool-calling agent with human-in-the-loop interrupts).
- LangGraph 2–4 = fixed workflows (CV Screening, Q&A Analysis, Final Assessment) started by the application.
- CV Collector service fetches CVs from Google Drive into data/cv_intake (Drive API, not LangGraph).
- MCP for job board, calendar and email.

## Rules
- Follow requirement.md. If a request conflicts with it, say so before writing code.
- Do not write the WBS or SRS. They must be done without AI.
- Never put real candidate data, CVs or secrets in code, examples, logs or commits. Secrets come from .env only.
- Plan first: show a short plan and wait for approval before writing code for a new feature.
- Keep code simple and explain it in plain language. I must be able to explain every part.
- Candidates must never be able to access scores, rankings or reports (enforce in the backend).
- Commit messages follow the BJIT guideline:
  type(scope): summary (≤50 chars, imperative)
  optional body with "- " bullets wrapped at 72 chars
  footer: Refs #id / Closes #id / Fixes #id (Redmine)
- End each task with a short handoff summary: what changed, files, Redmine task, next step.
