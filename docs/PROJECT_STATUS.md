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
  - Remaining (each on its own module branch): database schema + Alembic, frontend foundation (React/Vite container) and role access, LangGraph setup

## Git workflow
- Branches: main (initial structure only), dev, module/<name> per feature
- module/* branches start from dev and merge into dev by pull request; dev merges into main when the project is complete
- Git Bash is used for git commands; check the branch name in the prompt before committing

## Next
- Set up Cowork project and Claude Code on the repository folder
- Technical risk prototype: two-party video call, speech-to-text trial, multi-node LangGraph trial

## Open decisions (need trainer confirmation)
- Job-board posting via MCP (out of scope in the BID)
- Calendar MCP integration (out of scope in the BID unless it is the F11 innovation feature)
- F5 split: job-related answers → LLM, company-related answers → RAG
- F7 face/voice recognition: keep or drop?

## Redmine task IDs
- #646013 Initialize and share the BJIT GitHub repository, README and .gitignore
- #646476 Platform foundation: backend skeleton, health endpoint, Docker Compose with PostgreSQL + pgvector (closed 02-10-2026)
