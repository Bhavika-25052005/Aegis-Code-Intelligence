# Aegis — AI-Powered Code Intelligence Platform

> Convert a product backlog into reviewed, tested, committed code — with human oversight at every stage.

Built at the **Philips Global Hackathon** using Claude Code as the AI execution engine.

---

## What Aegis Does

Aegis is an end-to-end AI development assistant that takes a product backlog and drives it through four tightly integrated stages:

```
Import Backlog (Excel / CSV / JSON / YAML / Azure DevOps)
        │
        ▼
┌─────────────────────────────────┐
│  Requirement Intelligence       │  Claude analyses each user story → structured
│                                 │  10-field contract → human edits & approves
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  Implementation Planning        │  Claude scans repository metadata → produces
│                                 │  dependency-safe task plan → human approves
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  Code Generation                │  Claude writes code for every task in approved
│                                 │  execution order, respecting dependencies
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  Automated Testing & Self-Repair│  Requirement-aware unit tests per task,
│                                 │  quality gate after story, repair loop (max 3),
│                                 │  regression suite, custom NL test input
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  Quality Traceability & Delivery│  AC → Test traceability explorer, filtered PDF
│                                 │  report, Claude README update, Push to Repo
└─────────────────────────────────┘
        │
        ▼
  GitHub Branch → Commit → Pull Request
```

No stage proceeds without human approval. No code is generated until the requirement contract and the implementation plan are both explicitly approved.

---

## Key Features

| Feature | Detail |
|---|---|
| **Requirement Intelligence** | Claude produces summary, acceptance criteria, functional rules, edge cases, assumptions, dependencies, ambiguities, risks, open questions and risk level for every user story |
| **Repository Intelligence** | Walks the workspace and builds a metadata-only index (symbols, imports, SHA-256, size) — never stores full source. Incremental refresh via git diff |
| **Implementation Planning** | Claude (read-only tool access) produces a dependency-safe execution plan with file-level change descriptions and a test strategy |
| **Dual Approval Gates** | Both requirement contract and implementation plan must be approved before execution starts |
| **Requirement-Aware Code Generation** | Every Claude code-gen prompt carries the full approved requirement contract and approved plan as context |
| **Test Intelligence** | Unit tests generated per task, mapped to acceptance criteria / functional rules / edge cases with traceability IDs |
| **Self-Repair Loop** | Failing tests trigger a requirement-aware repair prompt; capped at 3 attempts, then marks Needs Human Review |
| **Quality Gate** | After all story tasks complete — runs generated integration/system tests + any existing `tests/regression/` suite |
| **Custom Natural-Language Tests** | Describe a test objective in plain English; Aegis generates, runs and retains it for regression |
| **Test Traceability Explorer** | Every test mapped to its AC (3-strategy: test_id pattern, source text, keyword) — searchable, filterable, paginated |
| **Downloadable PDF Report** | Filtered traceability view exported as a clean PDF with legend, active filters, test table and summary |
| **Quality Snapshot Cache** | Traceability computed once and cached by hash — subsequent page loads are instant until tests change |
| **README Auto-Update** | Claude inspects the workspace and updates README.md based on completed implementation before delivery |
| **Push to Repo** | Quality-gated delivery — requires all approvals + quality gate passed; supports existing and new repo config |
| **GitHub Integration** | Clone, branch-per-task/story/feature, commit, push, PR creation with test report in PR body |
| **Azure DevOps Import** | WIQL query import of Feature / User Story / Task work items |
| **Real-Time Dashboard** | WebSocket-powered execution view with per-task status, live logs, test results and repair history |

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- Claude Code CLI installed and authenticated

```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

---

## Quick Start

### 1. Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/Scripts/activate        # Git Bash / macOS / Linux
# .\.venv\Scripts\Activate.ps1       # Windows PowerShell

pip install -r requirements.txt
python -m uvicorn app.main:app --port 8001
```

Swagger UI: `http://127.0.0.1:8001/docs`

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`

> **Note:** If port 8001 conflicts, change `--port 8001` in the backend command and update the two `8001` references in `frontend/vite.config.ts`.

---

## Configuration

```bash
cp .env.example backend/.env
```

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./codegen_hub.db` | SQLite database path |
| `WORKSPACE_PATH` | system temp dir | Where repos are cloned and code is written |
| `ENCRYPTION_KEY` | auto-generated on first run | Fernet key for encrypting stored PATs |
| `claude_timeout_seconds` | `300` | Claude CLI subprocess timeout per invocation |
| `claude_max_budget_usd` | `5.0` | Max spend per Claude invocation |
| `claude_max_retries` | `3` | Max retries on partial Claude results |

---

## Usage Walkthrough

### Step 1 — Create a Project

Go to **Dashboard → New Project**. Fill in:
- Project name
- Local workspace path (e.g. `C:\workspace\my-project`) — this is where code will be written
- Optionally: GitHub repo URL + Personal Access Token for branch/commit/PR creation
- Optionally: Azure DevOps org URL + project + PAT for backlog import
- PR strategy: per task / per story / per feature

### Step 2 — Import a Backlog

In the **Backlog** view, upload a file or connect Azure DevOps.

Supported formats:

| Format | Notes |
|---|---|
| **Excel (.xlsx)** | Hierarchical columns (Feature / User Story / Task) or flat with a `Type` column |
| **CSV** | Same structure as Excel |
| **JSON / YAML** | Nested `features → user_stories → tasks` |
| **Azure DevOps** | WIQL query — fetches Feature / User Story / Task work items with parent links |

### Step 3 — Requirement Intelligence

1. In the Backlog view, click **AI Analyze** on any User Story
2. Claude analyses the story (no file access — read-only mode) and produces:
   - Summary, Acceptance Criteria, Functional Rules, Edge Cases
   - Assumptions, Dependencies, Ambiguities, Risks, Open Questions, Risk Level
3. Edit any field inline
4. Click **Approve** — this locks the contract and enables implementation planning

> Editing an approved requirement automatically invalidates the implementation plan, requiring re-generation.

### Step 4 — Implementation Planning

1. From the Requirement view, click **Continue to Implementation Plan**
2. Click **Generate Plan** — Claude scans the workspace metadata and produces:
   - Ordered task list with `execution_order` and `depends_on` relationships
   - Per-task planned file changes (create / modify / reuse) with purpose descriptions
   - Architecture observations and test strategy
3. Edit any section inline
4. Click **Approve Implementation Plan**

### Step 5 — Code Generation + Testing

Click **Generate Code + Tests** (or **Generate Code Only** to skip tests).

The execution dashboard shows the full pipeline in real time:

```
[CLAUDE] Invoking Claude Code CLI for: Create Patient Model
[CLAUDE] Code generated: Create Patient Model
[CLAUDE] Generating requirement-aware unit tests for: Create Patient Model
[CLAUDE] Generated 12 unit test(s) across 1 file(s): tests/unit/test_patient_model.py
[CLAUDE] Running 1 unit test file(s)...
[✓ PASS] unit tests: 12/12 passed

[CLAUDE] Invoking Claude Code CLI for: Create Patient Service
[CLAUDE] Code generated: Create Patient Service
[CLAUDE] Generating requirement-aware unit tests for: Create Patient Service
[CLAUDE] Generated 8 unit test(s) across 1 file(s): tests/unit/test_patient_service.py
[✗ FAIL] unit tests: 6/8 passed
[REPAIR] Attempt 1/3
[✓ PASS] unit tests: 8/8 passed (after fix #1)

[CLAUDE] Quality gate starting for 'Register Patient'
[CLAUDE] Quality gate — running integration/system tests...
[CLAUDE] Regression: no tests/regression folder found — skipped (0 tests)
[✓ PASS] Quality Tests: 20/20 passed
```

### Step 6 — Custom Tests (Optional)

On the Execution page, scroll to **Custom Test**. Type a natural-language objective:

> `Test that a patient cannot be registered without a date of birth`

Aegis generates an executable test, runs it, and retains it for future regression runs.

### Step 7 — Quality & Delivery

When execution completes, click **Quality & Delivery** (purple button). The quality page shows:

- **Quality Gate** — passed/failed banner
- **Test Summary** — counts by type: Unit, Integration, System, Regression, Custom, Total, Passed, Failed
- **Test Traceability Explorer** — every test mapped to its acceptance criterion (AC1, AC2, ...) with search, filter by AC / type / status, and pagination
- **Download Filtered PDF** — exports the current filtered view as a PDF with legend, filters, test table and summary
- **README** — generate or update the workspace README.md using Claude
- **Push to Repo** — quality-gated delivery; reuses existing GitHub config or asks for URL + token

---

## Repository Structure

```
Aegis-Code-Intelligence/
│
├── backend/                         FastAPI application
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── validate_quality_traceability.py  Validation suite for Quality Traceability service
│   └── app/
│       ├── main.py                  App entry point, CORS, lifespan (DB init + orphan run cleanup)
│       ├── config.py                Pydantic settings, auto-generates encryption key
│       ├── database.py              Async SQLAlchemy engine + inline schema migrations
│       │
│       ├── models/
│       │   ├── project.py           Project ORM model, RepositoryFile (metadata index)
│       │   ├── backlog.py           Feature, UserStory (req + plan + test + quality fields), Task
│       │   ├── execution.py         ExecutionRun, PullRequest
│       │   └── testing.py           TestRun, TestReport
│       │
│       ├── schemas/
│       │   ├── project.py           Pydantic request/response schemas for projects
│       │   ├── backlog.py           Backlog import and tree response schemas
│       │   ├── execution.py         ExecutionStartRequest, ExecutionStatusResponse
│       │   └── testing.py           TestRun/Report responses, CustomTestRequest/Response
│       │
│       ├── api/
│       │   ├── __init__.py          Aggregates all routers under /api prefix
│       │   ├── projects.py          GET/POST/PUT/DELETE /api/projects
│       │   ├── backlog.py           Backlog upload, Azure DevOps import, tree view
│       │   ├── requirement_analysis.py  Requirement + implementation plan endpoints
│       │   ├── execution.py         Start/pause/resume/reset execution, status
│       │   ├── testing.py           Test runs, reports, custom test endpoint
│       │   ├── quality.py           Quality explorer, PDF report, traceability, README, push
│       │   ├── github.py            GitHub repo validation, branch listing
│       │   └── websocket.py         WebSocket endpoint for live execution events
│       │
│       └── services/
│           ├── requirement_analyzer.py   Sends story to Claude (no tools) → 10-field JSON contract
│           ├── repository_intelligence.py  Metadata-only workspace index, incremental git-diff refresh
│           ├── implementation_planner.py   Claude (Read/Glob/Grep) → dependency-safe task plan
│           ├── orchestrator.py             Main execution engine — approval gates, dependency
│           │                               ordering, code gen loop, test integration
│           ├── test_intelligence.py        Generates requirement-aware test files via Claude
│           │                               (unit per task, integration/system per story, custom)
│           ├── test_runner.py              Runs tests natively (sys.executable + PYTHONPATH),
│           │                               framework detection, quality gate, regression discovery
│           ├── quality_reporter.py         AC→test traceability (3-strategy mapping), summary
│           │                               from TestRun records, snapshot cache, ReportLab PDF
│           ├── prompt_builder.py           All Claude prompt construction — task, test, repair,
│           │                               quality gate, continuation, verification
│           ├── claude_runner.py            Subprocess wrapper for Claude Code CLI, JSON output parsing
│           ├── github_service.py           GitPython + GitHub REST API — clone, branch, commit, push, PR
│           ├── backlog_parser.py           Excel/CSV/JSON/YAML → Feature/UserStory/Task tree
│           ├── azure_devops.py             WIQL query runner, batch work item fetch, hierarchy builder
│           ├── ci_generator.py             Writes .github/workflows/ci.yml if absent
│           ├── manual_test_runner.py       On-demand regression / PR-branch test runs
│           ├── websocket_manager.py        WebSocket connection registry and broadcaster
│           └── crypto.py                   Fernet encryption/decryption for stored PATs
│
├── frontend/                        Vue 3 application
│   ├── package.json
│   ├── vite.config.ts               Dev server proxy → backend :8001
│   ├── tailwind.config.js
│   └── src/
│       ├── main.ts                  Vue app bootstrap — Pinia, Router, PrimeVue (Aura theme)
│       ├── App.vue
│       ├── router/index.ts          8 routes: Dashboard, ProjectSetup, Backlog,
│       │                            RequirementAnalysis, ImplementationPlan, Execution, Quality, Settings
│       ├── api/client.ts            Axios instance with baseURL /api
│       ├── composables/
│       │   └── useWebSocket.ts      WebSocket composable with auto-reconnect
│       ├── stores/
│       │   ├── project.ts           Project CRUD state (Pinia)
│       │   ├── backlog.ts           Backlog fetch, upload, ADO import state
│       │   └── execution.ts         Execution start/pause/resume, status, logs
│       ├── types/index.ts           TypeScript interfaces for all domain objects
│       ├── views/
│       │   ├── DashboardView.vue    Project cards with delete confirmation
│       │   ├── ProjectSetupView.vue Create project — name, workspace, GitHub, ADO, strategy
│       │   ├── BacklogView.vue      Feature/Story/Task tree, upload, ADO import
│       │   ├── RequirementAnalysisView.vue  10-field contract editor + approve/reopen
│       │   ├── ImplementationPlanView.vue   Plan viewer/editor + approve + launch execution
│       │   ├── ExecutionView.vue    Live execution dashboard — task progress, logs,
│       │   │                        test results, custom test panel, Continue to Quality button
│       │   ├── QualityView.vue      Quality gate banner, test summary, traceability explorer,
│       │   │                        AC legend, filters, pagination, PDF download, README, push
│       │   └── SettingsView.vue     Project settings editor
│       └── components/
│           ├── backlog/
│           │   ├── BacklogTree.vue      Collapsible Feature/Story/Task tree with AI Analyze
│           │   ├── BacklogUploader.vue  Drag-and-drop file upload
│           │   └── AzureDevOpsConnect.vue  ADO WIQL import form
│           ├── execution/
│           │   └── TestReport.vue       Test run history table with manual trigger panel
│           └── layout/
│               ├── AppLayout.vue    Shell with sidebar and content area
│               ├── AppHeader.vue    Title, dark mode toggle
│               └── AppSidebar.vue   Navigation links
│
├── docs/
│   ├── sample_backlog.xlsx          Sample backlog for testing
│   ├── sample_backlog.yaml          Same backlog in YAML format
│   └── feature2_prescriptions.xlsx  Prescription feature sample backlog
│
└── .env.example                     Environment variable template
```

---

## Architecture

### Data Flow

```
Browser (Vue 3)
    │  REST (axios)          WebSocket
    ▼                            ▼
FastAPI (uvicorn)  ◄────────────────────────────────┐
    │                                               │
    ├── Requirement Analysis API                    │
    │       └── RequirementAnalyzerService          │
    │               └── ClaudeRunner (no tools)     │
    │                                               │
    ├── Implementation Plan API                     │
    │       ├── RepositoryIntelligence              │
    │       └── ImplementationPlannerService        │
    │               └── ClaudeRunner (Read/Glob/Grep)│
    │                                               │
    ├── Execution API                               │
    │       └── Orchestrator (asyncio background)   │
    │               ├── ClaudeRunner (all tools)  ──┘ WS broadcasts
    │               ├── TestIntelligence             (via WebSocketManager)
    │               │       └── ClaudeRunner (Bash/Read/Write/Edit/Glob/Grep)
    │               ├── TestRunnerService
    │               │       └── subprocess pytest / npm test
    │               └── GitHubService
    │
    └── SQLite (aiosqlite / SQLAlchemy async)
```

### Approval Gates

```
User Story
    │
    ├── [GATE 1] requirement_analysis_status == "approved"
    │               ↓ blocked if not approved
    ├── [GATE 2] implementation_plan_status == "approved"
    │               ↓ blocked if not approved
    └── Execution starts
            │
            └── Per-task dependency check (depends_on from approved plan)
                    ↓ blocked if dependency not completed
```

### Test Pipeline

```
Per Task:
  Claude builds task code
      → TestIntelligence generates unit tests (mapped to AC/FR/EC)
          → pytest runs test files natively (sys.executable)
              → PASS: next task
              → FAIL: repair loop (max 3) → PASS or Needs Human Review

After all tasks complete (Story Quality Gate):
  TestIntelligence generates integration/system tests
      → Claude runs generated tests
      → If tests/regression/ exists → pytest runs those files natively
      → Combined result → PASS or repair loop (max 3)
```

---

## API Reference

### Projects
```
GET    /api/projects
POST   /api/projects
GET    /api/projects/{id}
PUT    /api/projects/{id}
DELETE /api/projects/{id}
```

### Backlog
```
POST   /api/projects/{id}/backlog/upload
POST   /api/projects/{id}/backlog/azure-devops
GET    /api/projects/{id}/backlog
DELETE /api/projects/{id}/backlog/features/{feature_id}
```

### Requirement & Plan
```
GET    /api/projects/{id}/requirements/{story_id}
POST   /api/projects/{id}/requirements/{story_id}/analyze
PATCH  /api/projects/{id}/requirements/{story_id}
POST   /api/projects/{id}/requirements/{story_id}/approve
POST   /api/projects/{id}/requirements/{story_id}/reopen
GET    /api/projects/{id}/requirements/{story_id}/implementation-plan
POST   /api/projects/{id}/requirements/{story_id}/implementation-plan
PATCH  /api/projects/{id}/requirements/{story_id}/implementation-plan
POST   /api/projects/{id}/requirements/{story_id}/implementation-plan/approve
POST   /api/projects/{id}/requirements/{story_id}/implementation-plan/reopen
```

### Execution
```
POST   /api/projects/{id}/execute
POST   /api/projects/{id}/execute/pause
POST   /api/projects/{id}/execute/resume
POST   /api/projects/{id}/execute/reset
GET    /api/projects/{id}/execute/status
```

### Testing
```
GET    /api/projects/{id}/tests/runs
GET    /api/projects/{id}/tests/reports
GET    /api/projects/{id}/tests/latest-report
POST   /api/projects/{id}/tests/trigger
POST   /api/projects/{id}/tests/{story_id}/custom-test
```

### Quality & Delivery
```
GET    /api/projects/{id}/quality/{story_id}
GET    /api/projects/{id}/quality/{story_id}/report.pdf
POST   /api/projects/{id}/quality/{story_id}/verify-traceability
POST   /api/projects/{id}/quality/{story_id}/update-readme
POST   /api/projects/{id}/quality/{story_id}/push
```

### WebSocket
```
WS     /ws/projects/{id}/progress
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI Engine | Claude Code CLI (Anthropic) |
| Backend | FastAPI 0.110+, Python 3.11+ |
| ORM | SQLAlchemy 2 async + aiosqlite |
| Database | SQLite (file-based, zero config) |
| Frontend | Vue 3 + Vite 5 |
| State | Pinia |
| UI Components | PrimeVue 4 (Aura theme) + Tailwind CSS 3 |
| HTTP Client | Axios |
| Real-time | WebSockets (native FastAPI + useWebSocket composable) |
| Git | GitPython + GitHub REST API |
| Encryption | Python cryptography (Fernet) |
| PDF Generation | ReportLab 5 |
| Testing | pytest, subprocess-based native runner |

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "feat: description"`
4. Push and open a Pull Request

---

## License

MIT
