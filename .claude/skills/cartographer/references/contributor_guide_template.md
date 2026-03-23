# Contributor Guide Template for ContextCrawler

Use this template when generating a contributor guide. Fill in sections based on the actual codebase state.

---

# Contributing to ContextCrawler

Thanks for your interest in contributing! This guide will help you get set up and understand how the project is organized.

## Development Setup

### Prerequisites

- Python 3.11+
- Git

### Getting Started

```bash
# Clone the repository
git clone https://github.com/<org>/contextcrawler.git
cd contextcrawler

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Verify the setup
pytest
ruff check .
```

### Dev Dependencies

These are installed with `pip install -e ".[dev]"`:

- `pytest`, `pytest-asyncio`, `pytest-cov` — testing
- `ruff` — linting and formatting
- `mypy` — type checking
- `pre-commit` — git hooks (optional)

## Project Architecture

ContextCrawler follows a layered architecture:

```
Layer 0 (Foundation):  utils/, core/config
Layer 1 (Infrastructure):  http/, filter/, extract/
Layer 2 (Orchestration):  core/engine, core/scheduler, core/frontier, pipeline/
Layer 3 (Application):  spider/
Layer 4 (Monitoring):  monitor/
```

Dependencies flow downward only. See `docs/architecture.md` for the full dependency graph and data flow diagrams.

### Key Modules

| Module | Purpose |
|--------|---------|
| `core/engine.py` | Central crawl orchestrator — coordinates all components |
| `core/scheduler.py` | URL queue with priority and fairness |
| `core/frontier.py` | URL frontier with deduplication |
| `http/client.py` | httpx-based async HTTP client |
| `extract/links.py` | Link extraction from HTML |
| `filter/url.py` | URL pattern filtering |
| `pipeline/store.py` | Storage backends |
| `spider/base.py` | Base spider class |

## How To Add Things

### Adding a New Spider

1. Create `contextcrawler/spider/my_spider.py`
2. Subclass `BaseSpider`
3. Implement `should_follow(url)` and `parse(response)`
4. Add tests in `tests/unit/test_my_spider.py`
5. Export from `contextcrawler/spider/__init__.py`

### Adding a New Middleware

1. Create the middleware in `contextcrawler/http/middleware.py` (or a new file if large)
2. Implement `on_request(request)` and `on_response(response)`
3. Register in the middleware chain config
4. Add tests with mocked HTTP transport

### Adding a New Storage Backend

1. Create `contextcrawler/pipeline/stores/my_store.py`
2. Subclass `StorageStage`
3. Implement `store(item)` and optionally `close()`
4. Add tests
5. Export from package

### Adding a New Filter

1. Create or extend a file in `contextcrawler/filter/`
2. Implement the filter as a callable: `(url: str) -> bool`
3. Make it configurable through `CrawlerConfig`
4. Add parameterized tests covering edge cases

## Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=contextcrawler --cov-report=term-missing

# Only unit tests (fast)
pytest tests/unit/

# Only integration tests
pytest -m integration

# Type checking
mypy contextcrawler/
```

## Code Style

- Formatting: `ruff format .`
- Linting: `ruff check . --fix`
- Line length: 100 characters
- Type annotations: required on all public functions
- Docstrings: required on all public classes and methods

## Pull Request Process

1. Create a feature branch: `feat/my-feature` or `fix/bug-description`
2. Write code + tests
3. Run `pytest` and `ruff check .` locally
4. Open a PR with a clear description
5. Address review feedback
6. Squash-merge when approved

### Commit Message Format

```
feat(module): short description of what changed

Longer explanation if needed. Focus on WHY, not WHAT.
```

Prefixes: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
