"""Configuration management for LawBot CLI."""

import os
from pathlib import Path
from typing import Optional
import tomllib
import tomli_w

DEFAULT_CONFIG = {
    "general": {
        "region": "GA",
        "auto_search": True,
        "search_limit": 5,
        "show_splash": True,
    },
    "llm": {
        "provider": "azure",  # azure, openai, anthropic
        "model": "gpt-4o-mini",
        "temperature": 0.7,
        "max_tokens": 4000,
    },
    "azure": {
        "endpoint": "",
        "api_key": "",
        "api_version": "2024-08-01-preview",
    },
    "openai": {
        "api_key": "",
        "base_url": "",
    },
    "anthropic": {
        "api_key": "",
    },
    "database": {
        "sqlite_path": "law_ai.db",
        "postgres_host": "localhost",
        "postgres_port": 5432,
        "postgres_db": "law_ai",
        "postgres_user": "law_ai_user",
        "postgres_password": "law_ai_password",
    },
    "ui": {
        "theme": "dark",
        "show_sources": True,
        "show_thinking": True,
        "markdown_code_theme": "monokai",
    },
}


def get_config_dir() -> Path:
    """Get the configuration directory."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    
    config_dir = base / "lawbot"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_config_dir() / "config.toml"


def get_history_dir() -> Path:
    """Get the history directory."""
    history_dir = get_config_dir() / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir


def load_config() -> dict:
    """Load configuration from file, creating default if needed."""
    config_path = get_config_path()
    
    if not config_path.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    
    with open(config_path, "rb") as f:
        user_config = tomllib.load(f)
    
    # Merge with defaults
    config = DEFAULT_CONFIG.copy()
    for section, values in user_config.items():
        if section in config and isinstance(config[section], dict):
            config[section].update(values)
        else:
            config[section] = values
    
    return config


def save_config(config: dict) -> None:
    """Save configuration to file."""
    config_path = get_config_path()
    
    with open(config_path, "wb") as f:
        tomli_w.dump(config, f)


def get_value(config: dict, section: str, key: str, env_var: Optional[str] = None):
    """Get a config value with optional environment variable override."""
    if env_var and os.environ.get(env_var):
        return os.environ[env_var]
    
    return config.get(section, {}).get(key)


class Config:
    """Configuration wrapper with easy access."""
    
    def __init__(self):
        self._config = load_config()
    
    def reload(self):
        """Reload configuration from file."""
        self._config = load_config()
    
    def save(self):
        """Save current configuration."""
        save_config(self._config)
    
    @property
    def raw(self) -> dict:
        """Get raw config dict."""
        return self._config
    
    # General settings
    @property
    def region(self) -> str:
        return self._config["general"]["region"]
    
    @property
    def auto_search(self) -> bool:
        return self._config["general"]["auto_search"]
    
    @property
    def search_limit(self) -> int:
        return self._config["general"]["search_limit"]
    
    # LLM settings
    @property
    def provider(self) -> str:
        return self._config["llm"]["provider"]
    
    @property
    def model(self) -> str:
        return get_value(self._config, "llm", "model", "LAW_AI_MODEL")
    
    @property
    def temperature(self) -> float:
        return self._config["llm"]["temperature"]
    
    @property
    def max_tokens(self) -> int:
        return self._config["llm"]["max_tokens"]
    
    # Azure settings
    @property
    def azure_endpoint(self) -> str:
        return get_value(self._config, "azure", "endpoint", "AZURE_OPENAI_ENDPOINT")
    
    @property
    def azure_api_key(self) -> str:
        return get_value(self._config, "azure", "api_key", "AZURE_OPENAI_KEY")
    
    @property
    def azure_api_version(self) -> str:
        return get_value(self._config, "azure", "api_version", "AZURE_OPENAI_API_VERSION")
    
    # OpenAI settings
    @property
    def openai_api_key(self) -> str:
        return get_value(self._config, "openai", "api_key", "OPENAI_API_KEY")
    
    @property
    def openai_base_url(self) -> Optional[str]:
        return get_value(self._config, "openai", "base_url", "OPENAI_BASE_URL")
    
    # Anthropic settings
    @property
    def anthropic_api_key(self) -> str:
        return get_value(self._config, "anthropic", "api_key", "ANTHROPIC_API_KEY")
    
    # Database settings
    @property
    def sqlite_path(self) -> str:
        return self._config["database"]["sqlite_path"]
    
    @property
    def postgres_host(self) -> str:
        return get_value(self._config, "database", "postgres_host", "POSTGRES_HOST") or "localhost"
    
    @property
    def postgres_port(self) -> int:
        val = get_value(self._config, "database", "postgres_port", "POSTGRES_PORT")
        return int(val) if val else 5432
    
    @property
    def postgres_db(self) -> str:
        return get_value(self._config, "database", "postgres_db", "POSTGRES_DB") or "law_ai"
    
    @property
    def postgres_user(self) -> str:
        return get_value(self._config, "database", "postgres_user", "POSTGRES_USER") or "law_ai_user"
    
    @property
    def postgres_password(self) -> str:
        return get_value(self._config, "database", "postgres_password", "POSTGRES_PASSWORD") or "law_ai_password"
    
    # UI settings
    @property
    def theme(self) -> str:
        return self._config["ui"]["theme"]
    
    @property
    def show_sources(self) -> bool:
        return self._config["ui"]["show_sources"]
    
    @property
    def show_thinking(self) -> bool:
        return self._config["ui"]["show_thinking"]
    
    @property
    def code_theme(self) -> str:
        return self._config["ui"]["markdown_code_theme"]
    
    def set(self, section: str, key: str, value) -> None:
        """Set a configuration value."""
        if section not in self._config:
            self._config[section] = {}
        self._config[section][key] = value
