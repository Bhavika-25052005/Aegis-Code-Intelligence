# CodeGen Hub

AI-powered code generation from project backlogs using Claude Code CLI.

## Prerequisites

- Python 3.11+
- Node.js 18+
- Claude Code CLI installed and authenticated (`claude --version`)
- Git configured

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 in your browser.

## Configuration

Copy `.env.example` to `backend/.env` and update values as needed:

```bash
cp .env.example backend/.env
```

## Usage

1. Create a new project (provide GitHub repo URL + PAT)
2. Import your backlog (upload Excel/CSV/JSON/YAML or connect to Azure DevOps)
3. Review the parsed backlog tree
4. Start code generation
5. Monitor progress in real-time
6. PRs are automatically created on GitHub

## Supported Backlog Formats

- **Excel (.xlsx)**: Hierarchical columns (Feature, User Story, Task) or flat with Type column
- **CSV**: Same formats as Excel
- **JSON/YAML**: Nested structure with features > user_stories > tasks

## Architecture

- **Backend**: FastAPI + SQLAlchemy + SQLite
- **Frontend**: Vue 3 + PrimeVue + Tailwind CSS
- **Code Generation**: Claude Code CLI (subprocess)
- **Real-time Updates**: WebSocket
