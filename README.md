# Aegis — AI Code Intelligence Platform

An AI-driven development and quality engineering platform that converts software backlogs into production code with human oversight at every stage.

Built at the **Philips Global Hackathon**.

---

## What Aegis Does

Aegis automates the journey from a product backlog to reviewed, tested, committed code:

```
Import Backlog
  → AI Requirement Intelligence    ← Day 1 (feature/requirement-intelligence)
      - Summary, Acceptance Criteria, Functional Rules
      - Edge Cases, Assumptions, Dependencies
      - Ambiguities, Risks, Questions, Risk Level
  → Human Approval Gate            ← Day 1
  → AI Code Generation             ← this branch
  → Automated Testing + Fix Loop   ← this branch
  → GitHub PR Creation             ← this branch
```

---

## Branches

| Branch | Description |
|---|---|
| `main` | Baseline — AI code generation from backlog |
| `feature/requirement-intelligence` | Day 1 — Requirement Intelligence + Human Approval |

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

1. **Create a project** — provide a name and workspace path (GitHub repo + PAT optional)
2. **Import backlog** — upload Excel / CSV / JSON / YAML or connect to Azure DevOps
3. **Start code generation** — Aegis generates code per task, runs tests, fixes failures, commits and raises PRs
4. Monitor progress in real-time via the Execution view

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
    api/           FastAPI routers (projects, backlog, github, execution, testing)
    models/        SQLAlchemy ORM (Project, Feature, UserStory, Task, ...)
    services/
      claude_runner.py     Subprocess wrapper for Claude Code CLI
      orchestrator.py      Code generation orchestration
      test_runner.py       AI-powered test execution + fix loop
      prompt_builder.py    All Claude prompts
      github_service.py    Git + GitHub API operations
    database.py    Async SQLAlchemy engine + migrations
```

**Tech stack:** FastAPI · SQLAlchemy 2 (async) · SQLite · Vue 3 · Pinia · PrimeVue · Tailwind · Claude Code CLI

---

## Day 1 — Requirement Intelligence

See branch `feature/requirement-intelligence` for the full implementation.

Before AI writes any code, Aegis converts each user story into a structured, testable implementation contract and requires a human to approve it — acceptance criteria, functional rules, edge cases, assumptions, dependencies, ambiguities, risks, and open questions are all surfaced before a single line of code is generated.
