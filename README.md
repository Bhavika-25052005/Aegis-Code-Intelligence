# Aegis — AI Code Intelligence Platform

An AI-driven development and quality engineering platform that converts software backlogs into production code with human oversight at every stage.

Built at the **Philips Global Hackathon**.

---

## What Aegis Does

Aegis automates the journey from a product backlog to reviewed, tested, committed code:

```
Import Backlog
  → Day 1: AI Requirement Intelligence
      - Summary, Acceptance Criteria, Functional Rules
      - Edge Cases, Assumptions, Dependencies
      - Ambiguities, Risks, Questions, Risk Level
      - Human edit + Approval Gate
  → Day 2: Repository-Aware Implementation Planning
      - Local metadata index of the entire workspace
      - Relevant file discovery (no full source stored)
      - Dependency-safe task ordering
      - Human edit + Approval Gate
  → Day 2: AI Code Generation (requirement + plan aware)
      - Claude receives approved contract + approved plan
      - Tasks executed in approved dependency order
      - Blocked tasks flagged automatically
      - Code-only mode or full test + fix loop
  → Automated Testing + Fix Loop
  → GitHub Branch / Commit / PR Creation
  → Day 3 (planned): Automated Regression Testing
```

---

## Branches

| Branch | Description |
|---|---|
| `main` | Full Day 1 + Day 2 implementation |
| `feature/requirement-intelligence` | Original Day 1 branch (superseded by main) |

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

# Git Bash / macOS / Linux
source .venv/Scripts/activate

# Windows PowerShell
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
| `WORKSPACE_PATH` | system temp dir | Where repos are cloned / code is written |
| `ENCRYPTION_KEY` | auto-generated | Encrypts stored GitHub / ADO PATs |
| `claude_timeout_seconds` | `300` | Claude CLI subprocess timeout |
| `claude_max_budget_usd` | `5.0` | Max spend per Claude invocation |

---

## End-to-End Usage

### Step 1 — Create a Project
- Give it a name and a local workspace path (e.g. `C:\workspace\my-project`)
- Optionally add a GitHub repo URL + PAT for branch/commit/PR creation

### Step 2 — Import a Backlog
Upload Excel / CSV / JSON / YAML or connect Azure DevOps.  
Supported hierarchy: **Feature → User Story → Task**

### Step 3 — Day 1: Requirement Intelligence
1. Open the Backlog view → click **AI Analyze** on any User Story
2. Claude analyses the story and produces a structured contract:
   - Summary, Acceptance Criteria, Functional Rules
   - Edge Cases, Assumptions, Dependencies, Risks, Questions, Risk Level
3. Edit any section inline, then **Approve**

### Step 4 — Day 2: Implementation Planning
1. After approving the requirement, click **Continue to Implementation Plan →**
2. Claude scans the workspace (metadata only — symbols, imports, file hashes) and produces:
   - Ordered task execution list with dependency graph
   - Planned files to create / modify / reuse, each with purpose and reason
   - Architecture observations and test strategy for Day 3
3. Edit any section inline, then **Approve Implementation Plan**

### Step 5 — Code Generation
Click either button:
- **Generate Code + Tests** — Claude writes code, then writes and runs tests, fixing failures automatically
- **Generate Code Only** — Claude writes code immediately, no test runner invoked

Both modes run tasks in the plan's approved `execution_order`.  
Tasks whose dependencies haven't completed are automatically marked **blocked**.

After each task Claude generates real source files in your workspace folder — you can open and run them.

---

## Supported Backlog Formats

| Format | Notes |
|---|---|
| **Excel (.xlsx)** | Hierarchical columns (Feature / User Story / Task) or flat with a `Type` column |
| **CSV** | Same structure as Excel |
| **JSON / YAML** | Nested `features > user_stories > tasks` |
| **Azure DevOps** | WIQL query import — fetches Feature / User Story / Task work items |

---

## Architecture

```
frontend/                     Vue 3 + PrimeVue + Tailwind CSS
  src/
    views/
      BacklogView.vue               Backlog tree + import
      RequirementAnalysisView.vue   Day 1 — edit + approve requirement
      ImplementationPlanView.vue    Day 2 — edit + approve plan, launch execution
      ExecutionView.vue             Live code generation log + task status
    components/
      backlog/BacklogTree.vue       Feature/Story/Task tree with AI Analyze buttons
      execution/TestReport.vue      Test run history

backend/
  app/
    api/
      requirement_analysis.py   Day 1 + Day 2 REST endpoints
      execution.py              Start/pause/resume/reset execution
      backlog.py                Backlog import + tree
      projects.py               Project CRUD
    models/
      project.py                Project + RepositoryFile (metadata index)
      backlog.py                Feature, UserStory (req + plan fields), Task
      execution.py              ExecutionRun, PullRequest
    services/
      requirement_analyzer.py   Day 1 — Claude analyses requirement (read-only)
      repository_intelligence.py Day 2 — local metadata index, incremental refresh
      implementation_planner.py Day 2 — Claude plans task order (Read/Glob/Grep only)
      orchestrator.py           Dependency-ordered code generation loop
      prompt_builder.py         Builds Claude prompts with req contract + plan
      claude_runner.py          Subprocess wrapper for Claude Code CLI
      test_runner.py            AI-powered test execution + fix loop
      github_service.py         Git clone, branch, commit, push, PR creation
    database.py                 Async SQLAlchemy + inline migrations
```

**Tech stack:** FastAPI · SQLAlchemy 2 async · SQLite · Vue 3 · Pinia · PrimeVue 4 · Tailwind CSS 3 · Claude Code CLI

---

## Day 1 — Requirement Intelligence

Before any code is generated, Aegis converts each user story into a structured, human-approved implementation contract. Claude analyses the requirement in read-only mode (no file access) and produces 10 structured sections. A human reviews, edits, and approves before anything proceeds.

**API surface:**
```
GET  /api/projects/{id}/requirements/{story_id}
POST /api/projects/{id}/requirements/{story_id}/analyze
PATCH /api/projects/{id}/requirements/{story_id}
POST /api/projects/{id}/requirements/{story_id}/approve
POST /api/projects/{id}/requirements/{story_id}/reopen
```

---

## Day 2 — Requirement-Aware, Repository-Aware Code Generation

Day 2 connects the approved requirement contract to repository context and produces a human-approved implementation plan before Claude writes a single line of code.

### Repository Intelligence
- Walks the workspace and indexes every source file: path, category, symbols, imports, SHA-256, size
- **Never stores full source code** — metadata only
- Incremental refresh: git diff between commits, or SHA-256 comparison for non-git workspaces
- Scores files by keyword relevance to the requirement to surface the most useful context

### Implementation Planner
- Claude (Read/Glob/Grep only — cannot write files) creates:
  - A dependency-safe execution order for the imported tasks
  - Planned file changes with action (create/modify/reuse), purpose, and reason
  - Architecture observations and Day 3 test strategy
- Validates: every imported task appears exactly once, no cycles, no invented tasks

### Execution Gate
- Both Requirement approval **and** Implementation Plan approval are required before the Orchestrator runs
- Tasks execute in `execution_order` from the approved plan
- Tasks whose `depends_on` entries haven't completed are marked **blocked**

### Code Generation Modes
| Mode | Behaviour |
|---|---|
| Code + Tests | Claude generates code → writes tests → runs tests → fixes failures (up to 3 attempts) |
| Code Only | Claude generates code → task marked complete, no test runner |

### Story Scope Filter
Launch from the Implementation Plan page to run only the current story's tasks, not the entire project backlog.

**New API surface (Day 2):**
```
GET  /api/projects/{id}/requirements/{story_id}/implementation-plan
POST /api/projects/{id}/requirements/{story_id}/implementation-plan
PATCH /api/projects/{id}/requirements/{story_id}/implementation-plan
POST /api/projects/{id}/requirements/{story_id}/implementation-plan/approve
POST /api/projects/{id}/requirements/{story_id}/implementation-plan/reopen
```

---

## What the Generated Code Looks Like

After execution, your workspace contains real source files written by Claude Code:

```
workspace/
├── backend/
│   ├── models/prescription.py        ← SQLAlchemy ORM models
│   ├── routes/prescriptions.py       ← FastAPI endpoint
│   └── schemas/prescription.py       ← Pydantic schemas
└── frontend/
    └── src/components/
        └── PrescriptionForm.vue      ← Vue 3 component
```

These are runnable files. You still need to install dependencies, run migrations, and wire up any external services the tasks depend on.

---

## Day 3 (Planned) — Automated Regression Testing

- Full codebase regression on every PR
- Expanded test coverage beyond the unit/integration loop
- Test history and coverage trend reporting
