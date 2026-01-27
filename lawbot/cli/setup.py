"""Interactive setup wizard for LawBot configuration."""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.text import Text

from .config import Config, get_config_path, save_config, DEFAULT_CONFIG
from .themes import SPLASH_ART, list_themes, get_theme


PROVIDERS = {
    "azure": {
        "name": "Azure OpenAI",
        "fields": [
            ("endpoint", "Azure OpenAI Endpoint", "https://your-resource.openai.azure.com/"),
            ("api_key", "Azure OpenAI API Key", ""),
            ("api_version", "API Version", "2024-08-01-preview"),
        ],
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4", "gpt-35-turbo"],
        "env_hint": "AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY",
    },
    "openai": {
        "name": "OpenAI",
        "fields": [
            ("api_key", "OpenAI API Key", ""),
            ("base_url", "Base URL (optional, for proxies)", ""),
        ],
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
        "env_hint": "OPENAI_API_KEY",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "fields": [
            ("api_key", "Anthropic API Key", ""),
        ],
        "models": ["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
        "env_hint": "ANTHROPIC_API_KEY",
    },
}


def run_setup(console: Console | None = None) -> bool:
    """
    Run interactive setup wizard.
    
    Returns True if setup completed successfully.
    """
    console = console or Console()
    
    # Welcome with logo
    console.print()
    console.print(SPLASH_ART)
    console.print(Panel(
        "[bold]Welcome to LawBot Setup[/]\n\n"
        "This wizard will help you configure your LLM provider and database connections.",
        border_style="cyan",
    ))
    console.print()
    
    config = DEFAULT_CONFIG.copy()
    
    # Step 1: Choose provider
    console.print("[bold cyan]Step 1:[/] Choose your LLM provider\n")
    
    provider_table = Table(show_header=False, box=None, padding=(0, 2))
    provider_table.add_column("Key", style="bold green")
    provider_table.add_column("Provider")
    provider_table.add_column("Env Vars", style="dim")
    
    for key, info in PROVIDERS.items():
        provider_table.add_row(f"[{key}]", info["name"], info["env_hint"])
    
    console.print(provider_table)
    console.print()
    
    provider = Prompt.ask(
        "Select provider",
        choices=list(PROVIDERS.keys()),
        default="azure",
    )
    
    config["llm"]["provider"] = provider
    provider_info = PROVIDERS[provider]
    
    # Step 2: Provider credentials
    console.print()
    console.print(f"[bold cyan]Step 2:[/] Configure {provider_info['name']}\n")
    console.print("[dim]Paste your credentials (or press Enter to skip and use env vars later)[/]\n")
    
    for field, label, default in provider_info["fields"]:
        is_secret = "key" in field.lower() or "secret" in field.lower()
        
        if is_secret:
            value = Prompt.ask(f"  {label}", password=True, default=default)
        else:
            value = Prompt.ask(f"  {label}", default=default)
        
        config[provider][field] = value
    
    # Step 3: Choose model
    console.print()
    console.print("[bold cyan]Step 3:[/] Choose default model\n")
    
    models = provider_info["models"]
    for i, model in enumerate(models, 1):
        console.print(f"  [{i}] {model}")
    console.print(f"  [c] Custom model name")
    console.print()
    
    model_choice = Prompt.ask(
        "Select model",
        default="1",
    )
    
    if model_choice.lower() == "c":
        model = Prompt.ask("  Enter model name")
    elif model_choice.isdigit() and 1 <= int(model_choice) <= len(models):
        model = models[int(model_choice) - 1]
    else:
        model = models[0]
    
    config["llm"]["model"] = model
    
    # Step 4: Database configuration
    console.print()
    console.print("[bold cyan]Step 4:[/] Database configuration\n")
    
    if Confirm.ask("Configure Qdrant vector database?", default=True):
        config["database"]["qdrant_host"] = Prompt.ask(
            "  Qdrant host",
            default=config["database"]["qdrant_host"],
        )
        config["database"]["qdrant_port"] = int(Prompt.ask(
            "  Qdrant port",
            default=str(config["database"]["qdrant_port"]),
        ))
    
    config["database"]["sqlite_path"] = Prompt.ask(
        "  SQLite database path",
        default=config["database"]["sqlite_path"],
    )
    
    # Step 5: Preferences
    console.print()
    console.print("[bold cyan]Step 5:[/] Preferences\n")
    
    config["general"]["region"] = Prompt.ask(
        "  Default region",
        default="GA",
    )
    
    config["general"]["auto_search"] = Confirm.ask(
        "  Enable automatic law search?",
        default=True,
    )
    
    config["general"]["search_limit"] = int(Prompt.ask(
        "  Search results limit",
        default="5",
    ))
    
    # Step 6: Theme selection
    console.print()
    console.print("[bold cyan]Step 6:[/] Choose a theme\n")
    
    themes = list_themes()
    for i, t in enumerate(themes, 1):
        theme = get_theme(t)
        console.print(f"  [{i}] {theme.name}")
    console.print()
    
    theme_choice = Prompt.ask("Select theme", default="1")
    if theme_choice.isdigit() and 1 <= int(theme_choice) <= len(themes):
        config["ui"]["theme"] = themes[int(theme_choice) - 1]
    else:
        config["ui"]["theme"] = "dark"
    
    # Save configuration
    console.print()
    config_path = get_config_path()
    
    # Show summary
    summary = Table(title="Configuration Summary", box=None)
    summary.add_column("Setting", style="cyan")
    summary.add_column("Value")
    
    summary.add_row("Provider", config["llm"]["provider"])
    summary.add_row("Model", config["llm"]["model"])
    summary.add_row("Theme", get_theme(config["ui"]["theme"]).name)
    summary.add_row("Region", config["general"]["region"])
    summary.add_row("Auto Search", str(config["general"]["auto_search"]))
    summary.add_row("Qdrant", f"{config['database']['qdrant_host']}:{config['database']['qdrant_port']}")
    summary.add_row("Config Path", str(config_path))
    
    # Show if API keys are set (without revealing them)
    api_configured = any(
        config[provider].get(f[0]) 
        for f in provider_info["fields"] 
        if "key" in f[0].lower()
    )
    summary.add_row("API Key", "[green]configured[/]" if api_configured else "[yellow]use env var[/]")
    
    console.print(summary)
    console.print()
    
    if Confirm.ask("Save this configuration?", default=True):
        save_config(config)
        console.print(f"\n[green]✓[/] Configuration saved to: {config_path}")
        console.print("\n[dim]You can edit this file directly or run 'lawbot setup' again.[/]")
        console.print("[dim]API keys can also be set via environment variables.[/]\n")
        return True
    else:
        console.print("\n[yellow]Setup cancelled.[/]\n")
        return False


def check_and_prompt_setup(console: Console) -> bool:
    """
    Check if setup is needed and prompt user.
    
    Returns True if ready to proceed, False if should exit.
    """
    config_path = get_config_path()
    
    if not config_path.exists():
        console.print("[yellow]No configuration found.[/]\n")
        if Confirm.ask("Would you like to run setup now?", default=True):
            return run_setup(console)
        else:
            console.print("\n[dim]Run 'law-ai setup' later to configure.[/]\n")
            return False
    
    return True
