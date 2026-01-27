"""CLI entry point for LawBot."""

import sys
import click
from pathlib import Path

from dotenv import load_dotenv

# Load .env from current directory and parents
load_dotenv()

from .config import Config, get_config_path, save_config, DEFAULT_CONFIG
from .chat import ChatUI
from .setup import run_setup, check_and_prompt_setup


@click.group(invoke_without_command=True)
@click.option("--version", "-v", is_flag=True, help="Show version")
@click.pass_context
def cli(ctx, version):
    """LawBot - AI-powered Georgia legal research assistant."""
    if version:
        from lawbot import __version__
        click.echo(f"lawbot version {__version__}")
        return
    
    # If no subcommand, run chat
    if ctx.invoked_subcommand is None:
        ctx.invoke(chat)


@cli.command()
@click.option("--model", "-m", help="Override the LLM model")
@click.option("--region", "-r", help="Region filter (GA, GA-GWINNETT, etc.)")
@click.option("--theme", "-t", help="Color theme (dark, light, hacker, dracula, nord, monokai, solarized, gruvbox)")
@click.option("--no-search", is_flag=True, help="Disable automatic law search")
@click.option("--no-splash", is_flag=True, help="Skip the splash screen")
@click.option("--simple", is_flag=True, help="Use simple prompt-based interface instead of TUI")
def chat(model, region, theme, no_search, no_splash, simple):
    """Start an interactive chat session."""
    from rich.console import Console
    console = Console()
    
    # Check if setup needed
    if not get_config_path().exists():
        if not check_and_prompt_setup(console):
            return
    
    config = Config()
    
    # Apply overrides
    if model:
        config.set("llm", "model", model)
    if region:
        config.set("general", "region", region)
    if theme:
        config.set("ui", "theme", theme)
    if no_search:
        config.set("general", "auto_search", False)
    
    if simple:
        # Use simple Rich-based chat
        ui = ChatUI(config)
        ui.run()
    else:
        # Use full TUI
        from .tui import run_tui
        run_tui(config, show_splash=not no_splash)


@cli.command()
def setup():
    """Run interactive setup wizard."""
    from rich.console import Console
    run_setup(Console())


@cli.command("config")
@click.option("--edit", "-e", is_flag=True, help="Open config in editor")
@click.option("--reset", is_flag=True, help="Reset to default configuration")
@click.option("--set", "set_value", nargs=2, multiple=True, 
              metavar="KEY VALUE", help="Set a config value (e.g., --set llm.model gpt-4)")
def config_cmd(edit, reset, set_value):
    """View or edit configuration."""
    config_path = get_config_path()
    
    if reset:
        save_config(DEFAULT_CONFIG)
        click.echo(f"Configuration reset to defaults: {config_path}")
        return
    
    if set_value:
        cfg = Config()
        for key, value in set_value:
            parts = key.split(".")
            if len(parts) == 2:
                section, name = parts
                # Try to preserve type
                if value.lower() in ("true", "false"):
                    value = value.lower() == "true"
                elif value.isdigit():
                    value = int(value)
                elif value.replace(".", "").isdigit():
                    value = float(value)
                cfg.set(section, name, value)
                click.echo(f"Set {key} = {value}")
            else:
                click.echo(f"Invalid key format: {key} (use section.name)")
        cfg.save()
        return
    
    if edit:
        import os
        editor = os.environ.get("EDITOR", "nano")
        os.system(f"{editor} {config_path}")
        return
    
    # Show current config
    click.echo(f"Configuration file: {config_path}\n")
    
    if config_path.exists():
        click.echo(config_path.read_text())
    else:
        click.echo("No configuration file found. Run 'lawbot setup' to create one.")


@cli.command()
@click.option("--limit", "-n", default=10, help="Number of sessions to show")
def history(limit):
    """List recent chat sessions."""
    from .session import list_sessions
    from rich.console import Console
    from rich.table import Table
    
    sessions = list_sessions(limit=limit)
    
    if not sessions:
        click.echo("No chat sessions found.")
        return
    
    console = Console()
    table = Table(title="Chat History")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Messages", justify="right")
    table.add_column("Last Updated", style="dim")
    
    for s in sessions:
        table.add_row(
            s["session_id"],
            s["title"][:50] + ("..." if len(s["title"]) > 50 else ""),
            str(s["message_count"]),
            s["updated_at"][:16].replace("T", " "),
        )
    
    console.print(table)


@cli.command()
@click.argument("query", nargs=-1, required=True)
@click.option("--limit", "-n", default=5, help="Number of results")
@click.option("--region", "-r", default="GA", help="Region filter")
def search(query, limit, region):
    """Search Georgia laws (one-shot, non-interactive)."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.markdown import Markdown
    
    query_text = " ".join(query)
    config = Config()
    config.set("general", "region", region)
    config.set("general", "search_limit", limit)
    
    console = Console()
    
    with console.status("Searching..."):
        from .search import search_laws
        results = search_laws(query_text, config, limit=limit)
    
    if not results:
        console.print("[yellow]No results found. Is the database populated?[/]")
        return
    
    console.print(f"\n[bold]Found {len(results)} results for:[/] {query_text}\n")
    
    for i, r in enumerate(results, 1):
        panel_content = f"**{r['title']}**\n\n{r['text'][:500]}..."
        console.print(Panel(
            Markdown(panel_content),
            title=f"[cyan]{r['cite']}[/] ({r['source']})",
            subtitle=f"Score: {r['score']}",
            border_style="dim",
        ))


@cli.command()
def themes():
    """List available color themes."""
    from rich.console import Console
    from rich.table import Table
    from .themes import THEMES, get_theme
    
    console = Console()
    table = Table(title="Available Themes")
    table.add_column("Name", style="cyan")
    table.add_column("Primary", style="bold")
    table.add_column("Secondary")
    table.add_column("Background")
    
    for name, theme in THEMES.items():
        table.add_row(
            theme.name,
            f"[{theme.primary}]████[/]",
            f"[{theme.secondary}]████[/]",
            f"[on {theme.background}]    [/]",
        )
    
    console.print(table)
    console.print("\n[dim]Set theme with: lawbot config --set ui.theme <name>[/]")


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
