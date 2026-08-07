# Aegis — AI Code Intelligence Platform

An AI-driven development and quality engineering platform that converts software backlogs into production code with human oversight at every stage.

Built at the **Philips Global Hackathon**.

---

## What Aegis Does

Aegis automates the journey from a product backlog to reviewed, tested, committed code:

```
Import Backlog
  → AI Requirement Intelligence    ← Day 1
      - Summary, Acceptance Criteria, Functional Rules
      - Edge Cases, Assumptions, Dependencies
      - Ambiguities, Risks, Questions, Risk Level
  → Human Approval Gate            ← Day 1
  → AI Code Generation             ← existing
  → Automated Testing + Fix Loop   ← existing
  → GitHub PR Creation             ← existing
```

---

## Branches

| Branch | Description |
|---|---|
| `main` | Baseline — AI code generation from backlog |
| `feature/requirement-intelligence` | Day 1 — Requirement Intelligence + Human Approval |

---

## Day 1 — Requirement Intelligence

Before AI writes any code, Aegis converts each user story into a structured, testable implementation contract and requires a human to approve it.

**New flow:**
1. Open a user story in the Backlog view — click **AI Analyze**
2. Aegis calls Claude (read-only, no code edits) to produce a structured contract
3. Review the analysis: Summary, Acceptance Criteria, Functional Rules, Edge Cases, Assumptions, Dependencies, Ambiguities, Risks, Questions, Risk Level
4. Edit any section inline if needed (individual items can be added, changed or removed)
5. Click **Approve Requirement** — story is now ready for code generation
6. Regenerating or editing resets approval back to draft

**New API endpoints:**
```
GET  /api/projects/{project_id}/requirements/{story_id}
POST /api/projects/{project_id}/requirements/{story_id}/analyze
POST /api/projects/{project_id}/requirements/{story_id}/approve
POST /api/projects/{project_id}/requirements/{story_id}/reopen
PATCH /api/projects/{project_id}/requirements/{story_id}
```

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- Claude Code CLI installed and authenticated (`claude --version`)
- Git configured

---

## Quick Start

### 1. Backend

```bash
cd backend
python -m venv .venv

# Git Bash
source .venv/Scripts/activate
# PowerShell
# .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Swagger UI: http://127.0.0.1:8000/docs

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

---

## Configuration

```bash
cp .env.example backend/.env
```

Key settings in `backend/.env`:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./codegen_hub.db` | SQLite database path |
| `WORKSPACE_PATH` | system temp dir | Where repos are cloned |
| `ENCRYPTION_KEY` | auto-generated | Encrypts stored PATs |
| `claude_timeout_seconds` | 300 | Claude CLI subprocess timeout |
| `claude_max_budget_usd` | 5.0 | Max spend per Claude invocation |

---

## Usage

1. **Create a project** — provide a name and workspace path (GitHub repo + PAT optional for code generation)
2. **Import backlog** — upload Excel / CSV / JSON / YAML or connect to Azure DevOps
3. **AI Analyze** each user story — review and approve the requirement contract
4. **Start code generation** — Aegis generates code per task, runs tests, fixes failures, commits and raises PRs

---

## Supported Backlog Formats

- **Excel (.xlsx)** — hierarchical columns (Feature, User Story, Task) or flat with a Type column
- **CSV** — same structure as Excel
- **JSON / YAML** — nested `features > user_stories > tasks`
- **Azure DevOps** — WIQL query import

---

## Architecture

```
frontend/          Vue 3 + PrimeVue + Tailwind CSS
backend/
  app/
    api/           FastAPI routers (projects, backlog, github, execution, testing, requirements)
    models/        SQLAlchemy ORM (Project, Feature, UserStory, Task, ...)
    services/      Business logic
      claude_runner.py        Subprocess wrapper for Claude Code CLI
      requirement_analyzer.py Day 1 — structured requirement analysis
      orchestrator.py         Code generation orchestration
      test_runner.py          AI-powered test execution + fix loop
      prompt_builder.py       All Claude prompts
      github_service.py       Git + GitHub API operations
    database.py    Async SQLAlchemy engine + lightweight migrations
```

**Tech stack:** FastAPI · SQLAlchemy 2 (async) · SQLite · Vue 3 · Pinia · PrimeVue · Tailwind · Claude Code CLI

---

## Day 2 Preview (not yet implemented)

The approved Requirement Intelligence contract will feed directly into the code generation prompt — acceptance criteria, functional rules and edge cases become the specification Claude implements against, and AI-generated tests are derived from the same contract.
