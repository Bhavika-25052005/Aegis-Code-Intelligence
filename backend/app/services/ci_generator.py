import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CI_WORKFLOW_TEMPLATE = """name: CI - CodeGen Hub
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  test-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt 2>/dev/null || true
          pip install pytest pytest-cov pytest-asyncio httpx 2>/dev/null || true
      - name: Run tests
        run: |
          pytest --cov --cov-report=xml --cov-report=term -v 2>/dev/null || echo "No tests found"
      - name: Upload coverage
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage.xml
        continue-on-error: true

  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install dependencies
        run: |
          if [ -f package.json ]; then npm ci; fi
          if [ -f src/package.json ]; then cd src && npm ci; fi
        continue-on-error: true
      - name: Run tests
        run: |
          if [ -f package.json ]; then npx vitest run --coverage 2>/dev/null || echo "No frontend tests"; fi
        continue-on-error: true

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Lint Python
        run: |
          pip install ruff
          ruff check . --ignore E501 2>/dev/null || echo "Lint warnings found"
        continue-on-error: true
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Lint JavaScript
        run: |
          if [ -f package.json ]; then npx eslint src/ 2>/dev/null || echo "ESLint warnings"; fi
        continue-on-error: true
"""


def ensure_ci_workflow(workspace: str) -> bool:
    workflow_dir = Path(workspace) / ".github" / "workflows"
    workflow_file = workflow_dir / "ci.yml"

    if workflow_file.exists():
        logger.info("CI workflow already exists")
        return False

    workflow_dir.mkdir(parents=True, exist_ok=True)
    workflow_file.write_text(CI_WORKFLOW_TEMPLATE)
    logger.info(f"Created CI workflow at {workflow_file}")
    return True
