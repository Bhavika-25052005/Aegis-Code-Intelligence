# Aegis — AI-Powered Code Intelligence Platform

> From a product backlog to deployment-ready, tested, reviewed code — with human oversight at every gate.

---

## Overview

Aegis is an end-to-end AI development platform that takes a product backlog and drives it through six tightly integrated stages. Every stage requires explicit human approval before proceeding. No code is generated until requirements are approved, a plan is approved, and a data model is in place.

```
Backlog Import
     ↓
Requirement Intelligence  →  Human approves contract
     ↓
Implementation Planning   →  Human approves plan + data model
     ↓
Code Generation + Testing →  Self-repair loop, quality gate
     ↓
Quality Dashboard          →  Coverage, code review, traceability
     ↓
Deployment Readiness       →  8-gate checklist → Push to GitHub → PR
```

---

## Feature Set

### Authentication
- Login page with session persistence (localStorage)
- Profile avatar with user initials in the header
- Secure logout from the dropdown

---

### Requirement Intelligence
Claude analyses each user story and produces a structured 10-field contract:
- Summary, Acceptance Criteria, Functional Rules, Edge Cases
- Assumptions, Dependencies, Ambiguities, Risks, Open Questions, Risk Level

Human edits inline, then **Approves** to lock the contract. Editing after approval resets the plan.

---

### Implementation Planning
Claude scans repository metadata (read-only) and produces:
- Dependency-safe ordered task execution plan
- File-level planned changes (create / modify / reuse) with purpose
- Architecture observations and test strategy

Human approves the plan before code generation starts.

---

### Data Model
Generated automatically alongside the implementation plan. Claude designs the full entity-relationship schema:
- **Entities** — tables with all fields (name, type, PK, nullable, unique, indexed, default, description)
- **Relationships** — one-to-many, many-to-one, many-to-many, one-to-one with FK and ON DELETE
- **Enums** — separate enum definitions with value descriptions
- **Change log** — incremental enhancement tracking across stories

**Views:** Interactive table (expandable entities) + VueFlow ER diagram

**Editing:** Click any field row to edit inline — change name, type, nullable, unique, indexed. Add/remove fields and entities without regenerating.

**Import:** Upload a `.json` file (Aegis format) to bring in an existing schema.

**Export:** Download in JSON, SQL (`CREATE TABLE`), or DBML format.

**Code generation** receives the approved data model as context — Claude uses the exact field names and types when writing models and schemas.

---

### Knowledge Graph
Claude reads the workspace and generates an interactive architecture graph:
- **Nodes:** file, service, model, api, controller, frontend, task, acceptance_criterion
- **Edges:** IMPORTS, DEPENDS_ON, USES, CALLS, MODIFIES, IMPLEMENTS, CONTAINS, VALIDATES_BY
- Each node has a one-sentence Claude-generated description shown on click

**Rendering:** vis-network physics simulation — nodes auto-space, arrows render correctly

**Interactions:** Click node → detail panel (description, depends-on, used-by, file path). Analyze Impact → shows risk (LOW/MEDIUM/HIGH) and affected files/tasks/ACs.

**Filters:** Node type toggle, search, layout switch (force/hierarchy), depth selector for impact analysis.

Available in the **Implementation Plan** page (architecture graph) and **Quality & Delivery** page (enriched with test traceability after code runs).

---

### Code Generation + Automated Testing

Execution runs each approved task in dependency order. Each task goes through a full code-generate → test → repair cycle before the next task starts.

**Per-task cycle:**
```
1. Claude generates code for the task
2. Test Intelligence generates requirement-aware unit tests
   (mapped to Acceptance Criteria, Functional Rules, Edge Cases)
3. Tests run natively (sys.executable for Python, npm for JS/TS)
4. If PASS  → task marked complete, move to next task
5. If FAIL  → Aegis builds a repair prompt with:
              - the failing test output
              - the original requirement contract
              - the implementation plan context
              Sends to Claude for a targeted fix
6. Repair runs again (step 3)
7. If PASS  → task complete
8. If FAIL  → repeat steps 5-7 up to 3 total attempts
9. After 3 failures → task marked "Needs Human Review"
              Execution pauses. Human reviews the failure,
              optionally edits the code, then resumes.
```

**Story quality gate** (after all tasks complete):
```
1. Test Intelligence generates integration/system tests for the full story
2. Tests run natively
3. If tests/regression/ exists → regression suite runs automatically
4. PASS → story quality gate passes, Quality & Delivery unlocked
5. FAIL → same repair loop (max 3 attempts)
6. After 3 failures → story marked "Needs Human Review"
```

**Custom tests:** Describe any test objective in plain English on the Execution page → Aegis generates an executable test, runs it immediately, and retains it in the regression suite for all future runs.

**Test traceability:** Every generated test is mapped back to its Acceptance Criterion (AC) using a 3-strategy approach (test ID pattern, source text, keyword matching) — visible in the Test Traceability Explorer.

---

### Quality Dashboard

Three-tab view available after execution:

**Tab 1 — Test Coverage**
- Test summary by type (Unit, Integration, System, Regression, Custom)
- Run history with per-type pass/fail breakdown
- Test Traceability Explorer — every test mapped to its AC with search, filters, 10 per page, PDF download

**Tab 2 — Code Coverage**
- Real coverage metrics from pytest-cov / Vitest / Jest — never estimated
- Per-file coverage table with progress bars
- Code Review: 5 findings per page with filters (severity, category, file, free text)
- Code Review Details tab: Personal Info collected, Sensitive Info generated, Bad Code Practices

**Tab 3 — Deployment**
- **Deployment Readiness Checklist** — 8 deterministic gates (all must pass):
  1. Requirements Contract Approval
  2. Implementation Plan Generation
  3. Code Coverage > 70%
  4. Code Review completed
  5. No Critical Security Flaws
  6. Tests Passing
  7. Deployment Guide (README)
  8. GitHub Configuration

  > All thresholds and gate conditions are configurable in `code_quality.py` (`DEFAULT_RELEASE_RULES`). The coverage threshold (default 70%), maximum allowed critical findings, and which gates are blocking can all be adjusted per project.

- README auto-generation / update via Claude
- GitHub push: creates branch, commits, opens Pull Request

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Claude Code CLI

```bash
npm install -g @anthropic-ai/claude-code
claude login
```

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate.bat        # Windows CMD
# source .venv/Scripts/activate   # Git Bash / macOS

pip install -r requirements.txt
cp ../.env.example .env
python -m uvicorn app.main:app --port 8001
```

Swagger UI: `http://127.0.0.1:8001/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **`http://localhost:5173`**

> If port 8001 conflicts, change `--port 8001` in the backend command and update both `8001` references in `frontend/vite.config.ts`.

---

## Configuration

```bash
cp .env.example backend/.env
```

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./codegen_hub.db` | SQLite database |
| `WORKSPACE_PATH` | system temp dir | Where repos are cloned and code is written |
| `ENCRYPTION_KEY` | auto-generated | Fernet key for encrypting stored GitHub PATs |
| `claude_timeout_seconds` | `300` | Claude CLI timeout per call |
| `claude_max_budget_usd` | `5.0` | Max spend per Claude call |

---

## Usage Walkthrough

### 1. Create a Project
Dashboard → **New Project** → name, local workspace path, optional GitHub URL + PAT, optional Azure DevOps connection, PR strategy.

### 2. Import a Backlog
Backlog view → upload Excel / CSV / JSON / YAML, or connect Azure DevOps (WIQL).

### 3. Requirement Intelligence
Click **AI Analyze** on a User Story → review and edit the 10-field contract → **Approve**.

### 4. Implementation Planning
Continue to Implementation Plan → **Generate Plan** → review tasks, architecture notes, planned files → optionally edit approaches → **Approve**.

The **Data Model** tab generates automatically alongside the plan. Review entities, edit fields inline, approve the schema.

View the **Knowledge Graph** tab to understand architecture dependencies and planned change impact before writing code.

### 5. Code Generation
Click **Generate Code + Tests** (or code-only). Watch live execution in the dashboard — tasks, test results, repair attempts, quality gate.

### 6. Custom Tests (optional)
Describe a test objective in plain English on the Execution page → Aegis generates and runs it, retaining for regression.

### 7. Quality Analysis
Click **Quality & Delivery** → click **Refresh Quality Analysis** to run coverage + code review. Review the three tabs (Test Coverage, Code Coverage, Deployment).

### 8. Deploy
On the Deployment tab: once all 8 readiness checks pass, configure your GitHub repo (URL + PAT) and click **Push to GitHub** → branch is created and a Pull Request is opened automatically.

---

## Architecture

```
Browser (Vue 3)
    │ REST (axios)          WebSocket
    ▼                           ▼
FastAPI (uvicorn :8001)  ◄──────────────────────┐
    │                                            │
    ├── Requirement Analysis API                 │
    │       └── RequirementAnalyzerService       │
    │                                            │
    ├── Implementation Plan API                  │
    │       ├── RepositoryIntelligence           │
    │       ├── ImplementationPlannerService     │
    │       ├── DataModelGenerator               │
    │       └── KnowledgeGraphService            │
    │                                            │
    ├── Execution API                            │
    │       └── Orchestrator (asyncio)           │
    │               ├── ClaudeRunner  ───────────┘ WebSocket broadcasts
    │               ├── TestIntelligence
    │               └── TestRunnerService
    │
    ├── Quality API
    │       ├── QualityReporter (traceability, PDF)
    │       └── CodeQualityService (coverage, review, readiness)
    │
    └── SQLite (aiosqlite / SQLAlchemy async)
```

---

## Repository Structure

```
Aegis-Code-Intelligence/
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py                     App entry, CORS, lifespan
│       ├── config.py                   Pydantic settings
│       ├── database.py                 Async SQLAlchemy + inline migrations
│       ├── models/
│       │   ├── project.py              Project, RepositoryFile, GraphNode, GraphEdge
│       │   ├── backlog.py              Feature, UserStory, Task
│       │   ├── execution.py            ExecutionRun, PullRequest
│       │   └── testing.py              TestRun, TestReport
│       ├── api/
│       │   ├── requirement_analysis.py Requirement, Plan, DataModel, KnowledgeGraph endpoints
│       │   ├── execution.py            Start/pause/resume/reset
│       │   ├── testing.py              Test runs, custom tests
│       │   ├── quality.py              Traceability, coverage, review, push
│       │   └── websocket.py            Live execution events
│       └── services/
│           ├── requirement_analyzer.py      Claude → 10-field contract
│           ├── repository_intelligence.py   Metadata-only workspace index
│           ├── implementation_planner.py    Claude → dependency-safe task plan
│           ├── data_model_generator.py      Claude → entity-relationship schema
│           ├── data_model_serializer.py     JSON / SQL / DBML export
│           ├── knowledge_graph.py           Architecture graph builder
│           ├── orchestrator.py              Main execution engine
│           ├── test_intelligence.py         Requirement-aware test generation
│           ├── test_runner.py               Native test execution + repair
│           ├── quality_reporter.py          Traceability, snapshot cache, PDF
│           ├── code_quality.py              Coverage runner, Claude review, scoring
│           ├── prompt_builder.py            All Claude prompt construction
│           ├── claude_runner.py             Subprocess wrapper for Claude CLI
│           ├── github_service.py            Clone, branch, commit, push, PR
│           └── crypto.py                   Fernet encryption for PATs
├── frontend/
│   ├── package.json
│   ├── vite.config.ts                  Dev proxy → backend :8001
│   └── src/
│       ├── composables/
│       │   ├── useAuth.ts              Session auth (localStorage)
│       │   └── useWebSocket.ts         Auto-reconnect WebSocket
│       ├── views/
│       │   ├── LoginView.vue           Authentication page
│       │   ├── DashboardView.vue       Project cards
│       │   ├── BacklogView.vue         Feature/Story/Task tree, import
│       │   ├── RequirementAnalysisView.vue  10-field contract editor
│       │   ├── ImplementationPlanView.vue   Plan + Data Model + Knowledge Graph tabs
│       │   ├── ExecutionView.vue        Live dashboard, custom test panel
│       │   ├── QualityView.vue          3-tab quality dashboard
│       │   └── SettingsView.vue
│       ├── components/
│       │   ├── implementation/
│       │   │   ├── DataModelTable.vue   Expandable entity table with inline editing
│       │   │   └── DataModelDiagram.vue VueFlow ER diagram
│       │   ├── execution/
│       │   │   └── TestReport.vue       Test run history + manual trigger
│       │   ├── layout/
│       │   │   ├── AppLayout.vue
│       │   │   ├── AppHeader.vue        Profile avatar + logout dropdown
│       │   │   └── AppSidebar.vue
│       │   └── KnowledgeGraphPanel.vue  vis-network graph with detail panel
│       └── types/index.ts               All TypeScript interfaces
└── .env.example
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI Engine | Claude Code CLI (Anthropic) |
| Backend | FastAPI 0.115+, Python 3.11+ |
| Database | SQLite via SQLAlchemy 2 async + aiosqlite |
| Frontend | Vue 3 + Vite 5 + TypeScript |
| UI Components | PrimeVue 4 (Aura theme) + Tailwind CSS 3.4 |
| Graph Visualization | vis-network (architecture graph), Vue Flow (ER diagram) |
| State Management | Pinia |
| HTTP Client | Axios |
| Real-time | WebSockets (FastAPI native) |
| Git Integration | GitPython + GitHub REST API |
| Coverage | pytest-cov / Vitest / Jest |
| PDF Generation | ReportLab 5 |
| Encryption | Python cryptography (Fernet) |
