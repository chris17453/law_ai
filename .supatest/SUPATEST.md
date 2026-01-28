# LawBot CLI - Test Framework & Recommendations

## Project Overview
LawBot is a Python CLI/TUI application for Georgia legal research using:
- **CLI Framework**: Click (for command structure)
- **TUI Framework**: Textual (for terminal UI)
- **Database**: PostgreSQL with pgvector for vector search
- **LLM Integration**: Azure OpenAI, OpenAI, or Anthropic
- **Config**: TOML-based configuration

## Test Framework Analysis

### Current State
❌ **No tests exist** in the project (confirmed: no `tests/` directory or `test_*.py` files)

### Recommended Test Stack

#### 1. **CLI Testing**
- **Library**: `pytest` + `click.testing.CliRunner`
- **Why**: pytest is the Python standard, Click provides built-in CLI testing
- **Coverage**: All commands in `main.py` (chat, search, config, history, db backup/restore)

#### 2. **TUI Testing** (Limited scope)
- **Library**: `pytest-asyncio` + Textual's testing utilities
- **Why**: Textual is async-first; minimal UI testing since TUI is interactive
- **Coverage**: Critical user flows (message sending, navigation, modals)

#### 3. **Unit Testing**
- **Library**: `pytest` + `pytest-cov` + `pytest-mock`
- **Why**: Standard pytest ecosystem
- **Coverage**: Individual modules (config, session, search, llm)

#### 4. **Integration Testing**
- **Library**: `pytest-postgresql` (for test database) + `pytest-vcr` (for LLM mocking)
- **Why**: Need isolated DB and mocked external LLM calls
- **Coverage**: End-to-end search, session persistence, config I/O

---

## Recommended Test Structure

```
tests/
├── conftest.py                 # Shared fixtures
├── test_cli/
│   ├── test_main.py           # CLI entry point, version
│   ├── test_chat.py           # Chat command (simple + TUI modes)
│   ├── test_search.py         # One-shot search command
│   ├── test_config.py         # Config command (show, edit, reset, set)
│   ├── test_history.py        # History listing
│   └── test_db_commands.py    # Backup/restore commands
├── test_unit/
│   ├── test_config.py         # Config loading, saving, env vars
│   ├── test_session.py        # Session CRUD, persistence
│   ├── test_search.py         # Search logic, query expansion
│   ├── test_llm.py            # LLM client, provider switching
│   └── test_themes.py         # Theme loading, CSS generation
├── test_integration/
│   ├── test_search_flow.py    # Full search with DB + embeddings
│   ├── test_session_flow.py   # Chat session lifecycle
│   └── test_config_flow.py    # Config setup wizard
└── test_tui/
    ├── test_app.py            # TUI app initialization
    ├── test_screens.py        # Modal screens (help, model/theme select)
    └── test_widgets.py        # Custom widgets (MessageWidget, etc.)
```

---

## Priority Test Recommendations

### **HIGH PRIORITY** (Start Here)

#### 1. CLI Command Tests (`test_cli/test_main.py`)
**Why**: These are fast, isolated, and cover user-facing features

```python
def test_version():
    """Test --version flag"""
def test_no_command_runs_chat():
    """Test default command is chat"""
def test_help_command():
    """Test --help displays usage"""
```

#### 2. Config Tests (`test_unit/test_config.py`)
**Why**: Config is foundational; bugs here break everything

```python
def test_default_config_creation():
    """Test config is created with defaults if missing"""
def test_config_load_and_save():
    """Test config persists to disk"""
def test_env_var_override():
    """Test environment variables override config file"""
def test_config_get_value():
    """Test Config class property accessors"""
```

#### 3. Session Tests (`test_unit/test_session.py`)
**Why**: Session management is core to chat history

```python
def test_session_creation():
    """Test new session gets unique ID"""
def test_add_message():
    """Test adding user/assistant messages"""
def test_session_save_and_load():
    """Test session persists to disk and reloads"""
def test_auto_title_from_first_message():
    """Test session title from first user message"""
def test_search_results_attached_to_messages():
    """Test Message stores search results"""
```

#### 4. Search Command Tests (`test_cli/test_search.py`)
**Why**: One-shot search is a key user feature

```python
def test_search_command_basic(runner, mock_db):
    """Test search command with query"""
def test_search_with_limit():
    """Test --limit flag"""
def test_search_with_region():
    """Test --region flag"""
def test_search_no_expand():
    """Test --no-expand flag"""
def test_search_no_results():
    """Test empty result handling"""
```

### **MEDIUM PRIORITY**

#### 5. Setup Wizard Tests (`test_unit/test_setup.py`)
```python
def test_setup_wizard_prompts_for_api_key():
    """Test wizard asks for missing credentials"""
def test_setup_creates_config_file():
    """Test setup creates valid config"""
def test_setup_skips_if_config_exists():
    """Test setup detects existing config"""
```

#### 6. History Command Tests (`test_cli/test_history.py`)
```python
def test_history_lists_sessions():
    """Test history shows recent sessions"""
def test_history_with_limit():
    """Test --limit flag"""
def test_history_empty():
    """Test history with no sessions"""
```

#### 7. Config Command Tests (`test_cli/test_config.py`)
```python
def test_config_show():
    """Test displaying current config"""
def test_config_reset():
    """Test resetting to defaults"""
def test_config_set_value():
    """Test --set flag updates config"""
def test_config_edit_opens_editor():
    """Test --edit opens EDITOR"""
```

#### 8. Search Logic Tests (`test_unit/test_search.py`)
```python
def test_query_expansion():
    """Test LLM query expansion"""
def test_search_vector_fallback():
    """Test fallback to text search if vector fails"""
def test_region_filtering():
    """Test region filtering in SQL query"""
```

### **LOWER PRIORITY** (Advanced)

#### 9. TUI Tests (`test_tui/`)
**Why**: TUI testing is complex; focus on critical paths only

```python
def test_tui_initialization():
    """Test app starts without crash"""
def test_message_send():
    """Test sending a message"""
def test_new_chat():
    """Test starting new conversation"""
def test_theme_change():
    """Test theme switching"""
def test_model_change():
    """Test model switching"""
def test_help_modal():
    """Test help screen display"""
```

#### 10. Database Backup Tests (`test_cli/test_db_commands.py`)
```python
def test_db_backup():
    """Test database backup"""
def test_db_restore():
    """Test database restore"""
def test_backup_with_chunking():
    """Test large file chunking"""
```

---

## Test Fixtures Needed (`conftest.py`)

### Core Fixtures
```python
@pytest.fixture
def temp_config_dir(monkeypatch):
    """Isolated config directory for tests"""
@pytest.fixture
def temp_history_dir(monkeypatch):
    """Isolated history directory for tests"""
@pytest.fixture
def mock_config(monkeypatch):
    """Mock Config with test values"""
@pytest.fixture
def mock_postgresql(postgresql):
    """Test PostgreSQL database"""
@pytest.fixture
def mock_llm(mocker):
    """Mock LLM responses"""
@pytest.fixture
def sample_search_results():
    """Sample search results for testing"""
```

---

## Testing Challenges & Solutions

### Challenge 1: Database Dependencies
**Solution**: Use `pytest-postgresql` for isolated test DB
- Run PostgreSQL in Docker or use temporary database
- Populate with sample laws for search tests
- Teardown after each test

### Challenge 2: LLM API Calls
**Solution**: Mock all LLM calls using `pytest-vcr` or `pytest-mock`
- Never call real APIs in tests (slow, costly, non-deterministic)
- Record real responses once, replay in tests
- Test error handling with mocked failures

### Challenge 3: TUI/Async Testing
**Solution**: Test business logic, not rendering
- Test screen composition logic, not visual output
- Use Textual's `app.push_screen()` and `app.pop_screen()`
- Test async methods with `pytest-asyncio`
- Avoid testing widget positions/colors

### Challenge 4: File System I/O
**Solution**: Use `tmp_path` fixture and `monkeypatch`
- Never write to real config/home directories
- Mock environment variables
- Clean up temp files automatically

### Challenge 5: Vector Embeddings
**Solution**: Mock the embedding model
- Don't load real ML models in tests (slow, memory-heavy)
- Return fixed vectors for known inputs
- Test fallback to text search

---

## Test Command Setup

### Add to `pyproject.toml`:
```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pytest-mock>=3.11.0",
    "pytest-asyncio>=0.21.0",
    "pytest-postgresql>=5.0.0",
    "pytest-vcr>=1.0.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "tui: marks tests that test the TUI",
]
```

### Run tests:
```bash
# All tests
pytest

# Unit tests only (fast)
pytest tests/test_unit/ -m "not integration"

# With coverage
pytest --cov=lawbot --cov-report=html

# Single test file
pytest tests/test_unit/test_config.py -v

# Watch mode (dev)
pytest-watch
```

---

## Getting Started Checklist

- [ ] Install test dependencies: `pip install -e ".[dev]"`
- [ ] Create `tests/` directory structure
- [ ] Add `conftest.py` with core fixtures
- [ ] Write first test: `test_unit/test_config.py::test_default_config_creation`
- [ ] Run first test: `pytest tests/test_unit/test_config.py`
- [ ] Aim for 80% coverage on core modules (config, session, search)
- [ ] Add CI integration (GitHub Actions) to run tests on PRs

---

## Test Writing Principles

1. **Isolation**: Each test should be independent (no shared state)
2. **Speed**: Unit tests should run in milliseconds, not seconds
3. **Clarity**: Test names should describe what they test
4. **Reality**: Mock external dependencies but keep internal logic real
5. **Maintenance**: Tests should be easy to update when code changes

---

## Example Test (to get started)

```python
# tests/test_unit/test_config.py
import pytest
from pathlib import Path
from lawbot.cli.config import Config, load_config, save_config, get_config_path

def test_default_config_creation(tmp_path, monkeypatch):
    """Test config is created with defaults if missing"""
    # Isolate config directory
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    # Load config (should create defaults)
    config = load_config()

    # Verify defaults
    assert config["general"]["region"] == "GA"
    assert config["llm"]["provider"] == "azure"
    assert config["llm"]["model"] == "gpt-4o-mini"
    assert config["general"]["auto_search"] is True

def test_config_save_and_load(tmp_path, monkeypatch):
    """Test config persists to disk and reloads"""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    # Create and save custom config
    custom_config = {
        "general": {"region": "GA-GWINNETT", "auto_search": False},
        "llm": {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"},
    }
    save_config(custom_config)

    # Load and verify
    loaded = load_config()
    assert loaded["general"]["region"] == "GA-GWINNETT"
    assert loaded["general"]["auto_search"] is False
    assert loaded["llm"]["provider"] == "anthropic"

def test_config_class_properties(tmp_path, monkeypatch):
    """Test Config class property accessors"""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("LAW_AI_MODEL", "gpt-4o")  # Override model

    config = Config()

    assert config.region == "GA"
    assert config.model == "gpt-4o"  # From env var
    assert config.auto_search is True
    assert config.provider == "azure"
```

---

## Next Steps

1. Review this document and confirm the test strategy
2. Set up the test infrastructure (pytest, fixtures)
3. Start with HIGH PRIORITY tests (fast wins)
4. Iterate to MEDIUM and LOW priority as needed
5. Add coverage reporting to CI/CD pipeline

---

**Generated by**: Supatest AI
**Date**: 2026-01-28
**Project**: LawBot CLI - Georgia Legal Research Assistant
