"""Rich terminal UI for Law AI chat."""

import sys
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.spinner import Spinner
from rich.columns import Columns

from .config import Config, get_config_dir
from .llm import get_llm_client, LLMClient
from .search import search_laws
from .session import Session, list_sessions, delete_session

# Custom theme
THEME = Theme({
    "info": "cyan",
    "warning": "yellow", 
    "error": "red bold",
    "success": "green",
    "user": "bold blue",
    "assistant": "bold green",
    "dim": "dim",
    "citation": "bold cyan",
})

# Prompt toolkit style
PROMPT_STYLE = Style.from_dict({
    "prompt": "bold ansiblue",
})


class ChatUI:
    """Rich-based chat interface."""
    
    def __init__(self, config: Config):
        self.config = config
        self.console = Console(theme=THEME)
        self.session: Optional[Session] = None
        self.llm: Optional[LLMClient] = None
        self.auto_search = config.auto_search
        
        # Prompt with history
        history_file = get_config_dir() / "prompt_history"
        self.prompt_session = PromptSession(
            history=FileHistory(str(history_file)),
            auto_suggest=AutoSuggestFromHistory(),
            style=PROMPT_STYLE,
        )
    
    def print_banner(self) -> None:
        """Print welcome banner."""
        banner = Text()
        banner.append("╭─────────────────────────────────────────────────────────────╮\n", style="cyan")
        banner.append("│", style="cyan")
        banner.append("              ⚖️  Georgia Legal AI Assistant                  ", style="bold white")
        banner.append("│\n", style="cyan")
        banner.append("│", style="cyan")
        banner.append("                    Powered by ", style="dim")
        banner.append(f"{self.config.model}", style="bold cyan")
        banner.append("                    ".ljust(20), style="dim")
        banner.append("│\n", style="cyan")
        banner.append("╰─────────────────────────────────────────────────────────────╯", style="cyan")
        
        self.console.print(banner)
        self.console.print()
    
    def print_help(self) -> None:
        """Print help information."""
        help_table = Table(show_header=False, box=None, padding=(0, 2))
        help_table.add_column("Command", style="bold green")
        help_table.add_column("Description", style="dim")
        
        commands = [
            ("/help", "Show this help message"),
            ("/new", "Start a new conversation"),
            ("/history", "Show recent conversations"),
            ("/load <id>", "Load a previous conversation"),
            ("/delete <id>", "Delete a conversation"),
            ("/search", "Toggle automatic law search"),
            ("/model <name>", "Switch LLM model"),
            ("/config", "Show current configuration"),
            ("/clear", "Clear screen"),
            ("/quit", "Exit (Ctrl+D also works)"),
        ]
        
        for cmd, desc in commands:
            help_table.add_row(cmd, desc)
        
        self.console.print(Panel(
            help_table,
            title="[bold]Commands[/bold]",
            border_style="cyan",
            padding=(1, 2),
        ))
        self.console.print()
    
    def print_status(self) -> None:
        """Print current status bar."""
        status_parts = []
        
        # Model
        status_parts.append(f"[bold cyan]Model:[/] {self.config.model}")
        
        # Region
        status_parts.append(f"[bold cyan]Region:[/] {self.config.region}")
        
        # Auto-search
        search_status = "[green]ON[/]" if self.auto_search else "[dim]OFF[/]"
        status_parts.append(f"[bold cyan]Search:[/] {search_status}")
        
        # Session
        if self.session:
            status_parts.append(f"[bold cyan]Session:[/] {self.session.session_id}")
        
        self.console.print(" │ ".join(status_parts), style="dim")
        self.console.print()
    
    def print_history(self) -> None:
        """Print recent sessions."""
        sessions = list_sessions(limit=10)
        
        if not sessions:
            self.console.print("[dim]No previous conversations found.[/]")
            return
        
        table = Table(title="Recent Conversations", box=None)
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Messages", justify="right")
        table.add_column("Updated", style="dim")
        
        for s in sessions:
            table.add_row(
                s["session_id"],
                s["title"][:40] + ("..." if len(s["title"]) > 40 else ""),
                str(s["message_count"]),
                s["updated_at"][:16].replace("T", " "),
            )
        
        self.console.print(table)
        self.console.print()
    
    def print_config(self) -> None:
        """Print current configuration."""
        table = Table(title="Configuration", box=None)
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="white")
        
        table.add_row("Provider", self.config.provider)
        table.add_row("Model", self.config.model)
        table.add_row("Region", self.config.region)
        table.add_row("Auto Search", str(self.auto_search))
        table.add_row("Search Limit", str(self.config.search_limit))
        table.add_row("Temperature", str(self.config.temperature))
        table.add_row("Config Path", str(get_config_dir() / "config.toml"))
        
        self.console.print(table)
        self.console.print()
    
    def print_sources(self, results: list) -> None:
        """Print search results as sources."""
        if not results or not self.config.show_sources:
            return
        
        self.console.print()
        sources_table = Table(
            title="[dim]Sources Found[/]",
            box=None,
            show_header=False,
            padding=(0, 1),
        )
        sources_table.add_column("Num", style="dim", width=3)
        sources_table.add_column("Citation", style="cyan")
        sources_table.add_column("Title", style="dim")
        sources_table.add_column("Score", style="dim", justify="right")
        
        for i, r in enumerate(results, 1):
            sources_table.add_row(
                f"[{i}]",
                r["cite"],
                r["title"][:35] + ("..." if len(r["title"]) > 35 else ""),
                f"{r['score']:.2f}",
            )
        
        self.console.print(sources_table)
    
    def stream_response(self, messages: list) -> str:
        """Stream LLM response with live display."""
        full_response = ""
        
        try:
            stream = self.llm.chat(messages, stream=True)
            
            with Live(console=self.console, refresh_per_second=15) as live:
                for chunk in stream:
                    full_response += chunk
                    # Render as markdown
                    md = Markdown(full_response)
                    panel = Panel(
                        md,
                        title="[bold green]Assistant[/]",
                        border_style="green",
                        padding=(1, 2),
                    )
                    live.update(panel)
        
        except Exception as e:
            self.console.print(f"[error]Error: {e}[/]")
            return ""
        
        return full_response
    
    def handle_command(self, cmd: str) -> bool:
        """Handle a slash command. Returns True if should continue loop."""
        parts = cmd.strip().split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        
        if command in ("/quit", "/exit", "/q"):
            if self.session and self.session.messages:
                self.session.save()
                self.console.print("[dim]Session saved.[/]")
            return False
        
        elif command == "/help":
            self.print_help()
        
        elif command == "/new":
            if self.session and self.session.messages:
                self.session.save()
            self.session = Session()
            self.console.print(f"[success]Started new session: {self.session.session_id}[/]")
        
        elif command == "/history":
            self.print_history()
        
        elif command == "/load":
            if not arg:
                self.console.print("[error]Usage: /load <session_id>[/]")
            else:
                loaded = Session.load(arg)
                if loaded:
                    if self.session and self.session.messages:
                        self.session.save()
                    self.session = loaded
                    self.console.print(f"[success]Loaded session: {self.session.title or self.session.session_id}[/]")
                    # Show recent messages
                    for msg in self.session.messages[-4:]:
                        role_style = "user" if msg.role == "user" else "assistant"
                        self.console.print(f"[{role_style}]{msg.role.title()}:[/] {msg.content[:100]}...")
                else:
                    self.console.print(f"[error]Session '{arg}' not found.[/]")
        
        elif command == "/delete":
            if not arg:
                self.console.print("[error]Usage: /delete <session_id>[/]")
            elif delete_session(arg):
                self.console.print(f"[success]Deleted session: {arg}[/]")
            else:
                self.console.print(f"[error]Session '{arg}' not found.[/]")
        
        elif command == "/search":
            self.auto_search = not self.auto_search
            status = "[green]enabled[/]" if self.auto_search else "[dim]disabled[/]"
            self.console.print(f"Automatic law search: {status}")
        
        elif command == "/model":
            if not arg:
                self.console.print(f"Current model: [cyan]{self.config.model}[/]")
            else:
                self.config.set("llm", "model", arg)
                self.config.save()
                # Reinitialize LLM client
                self.llm = get_llm_client(self.config)
                self.console.print(f"[success]Switched to model: {arg}[/]")
        
        elif command == "/config":
            self.print_config()
        
        elif command == "/clear":
            self.console.clear()
            self.print_banner()
        
        else:
            self.console.print(f"[error]Unknown command: {command}. Type /help for available commands.[/]")
        
        return True
    
    def run(self) -> None:
        """Run the chat interface."""
        # Initialize
        self.console.clear()
        self.print_banner()
        
        try:
            self.llm = get_llm_client(self.config)
        except ValueError as e:
            self.console.print(f"[error]{e}[/]")
            self.console.print("\n[dim]Edit the config file at:[/]")
            self.console.print(f"  {get_config_dir() / 'config.toml'}")
            self.console.print("\n[dim]Or set environment variables:[/]")
            self.console.print("  AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY")
            return
        
        self.session = Session()
        self.print_status()
        self.console.print("[dim]Type /help for commands, or just start chatting.[/]\n")
        
        while True:
            try:
                # Get input
                user_input = self.prompt_session.prompt(
                    [("class:prompt", "❯ ")],
                ).strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.startswith("/"):
                    if not self.handle_command(user_input):
                        break
                    continue
                
                # Search for relevant laws
                search_results = []
                if self.auto_search:
                    with self.console.status("[dim]Searching laws...[/]", spinner="dots"):
                        search_results = search_laws(user_input, self.config)
                    
                    if search_results:
                        self.print_sources(search_results)
                
                # Add user message
                self.session.add_message("user", user_input, search_results=search_results)
                
                # Get and stream response
                self.console.print()
                messages = self.session.get_api_messages()
                response = self.stream_response(messages)
                
                if response:
                    self.session.add_message("assistant", response)
                
                self.console.print()
                
            except KeyboardInterrupt:
                self.console.print("\n[dim]Use /quit to exit or Ctrl+D[/]")
                continue
            
            except EOFError:
                if self.session and self.session.messages:
                    self.session.save()
                    self.console.print("\n[dim]Session saved. Goodbye![/]")
                break
        
        self.console.print()
