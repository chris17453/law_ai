"""Full-screen TUI application for LawBot."""

from datetime import datetime
from typing import Optional
import asyncio

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer, Center
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    Static,
    LoadingIndicator,
)
from textual.screen import ModalScreen, Screen

from .config import Config
from .llm import get_llm_client, LLMClient
from .search import search_laws
from .session import Session, list_sessions, delete_session
from .themes import get_theme, list_themes, generate_css, SPLASH_ART, Theme


# Available models per provider
MODELS = {
    "azure": [
        "gpt-4o-mini",
        "gpt-4o", 
        "gpt-4",
        "gpt-4-turbo",
        "gpt-35-turbo",
    ],
    "openai": [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
    ],
    "anthropic": [
        "claude-sonnet-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229",
        "claude-3-haiku-20240307",
    ],
}


class SplashScreen(Screen):
    """Animated splash/intro screen."""
    
    BINDINGS = [
        Binding("enter", "continue", "Continue"),
        Binding("escape", "continue", "Continue"),
        Binding("space", "continue", "Continue"),
    ]
    
    def compose(self) -> ComposeResult:
        with Container(id="splash-container"):
            yield Static(SPLASH_ART, id="splash-logo")
            yield Static("", id="splash-version")
            yield Static("\n[bold]Press ENTER to continue[/]", id="splash-prompt")
    
    def on_mount(self) -> None:
        from lawbot import __version__
        self.query_one("#splash-version", Static).update(f"[dim]Version {__version__}[/]")
    
    def action_continue(self) -> None:
        self.app.pop_screen()
    
    def on_key(self, event) -> None:
        self.app.pop_screen()


class ModelSelectScreen(ModalScreen[str]):
    """Modal for selecting a model."""
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]
    
    def __init__(self, current_model: str, provider: str):
        super().__init__()
        self.current_model = current_model
        self.provider = provider
    
    def compose(self) -> ComposeResult:
        models = MODELS.get(self.provider, MODELS["openai"])
        
        with Container(id="model-dialog"):
            yield Label("🤖 Select Model", id="model-dialog-title")
            yield ListView(
                *[ListItem(Label(m), id=f"model-{m}") for m in models],
                id="model-list",
            )
            yield Label("[dim]Enter to select • Escape to cancel[/]")
    
    def on_mount(self) -> None:
        try:
            list_view = self.query_one("#model-list", ListView)
            models = MODELS.get(self.provider, MODELS["openai"])
            if self.current_model in models:
                idx = models.index(self.current_model)
                list_view.index = idx
        except (NoMatches, ValueError):
            pass
    
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        models = MODELS.get(self.provider, MODELS["openai"])
        if event.list_view.index is not None and event.list_view.index < len(models):
            self.dismiss(models[event.list_view.index])
    
    def action_cancel(self) -> None:
        self.dismiss(None)


class ThemeSelectScreen(ModalScreen[str]):
    """Modal for selecting a theme."""
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]
    
    def __init__(self, current_theme: str):
        super().__init__()
        self.current_theme = current_theme
    
    def compose(self) -> ComposeResult:
        themes = list_themes()
        
        with Container(id="theme-dialog"):
            yield Label("🎨 Select Theme", id="theme-dialog-title")
            yield ListView(
                *[ListItem(Label(f"  {get_theme(t).name}"), id=f"theme-{t}") for t in themes],
                id="theme-list",
            )
            yield Label("[dim]Enter to select • Escape to cancel[/]")
    
    def on_mount(self) -> None:
        try:
            list_view = self.query_one("#theme-list", ListView)
            themes = list_themes()
            if self.current_theme in themes:
                idx = themes.index(self.current_theme)
                list_view.index = idx
        except (NoMatches, ValueError):
            pass
    
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        themes = list_themes()
        if event.list_view.index is not None and event.list_view.index < len(themes):
            self.dismiss(themes[event.list_view.index])
    
    def action_cancel(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen[None]):
    """Help modal."""
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "close", "Close"),
    ]
    
    def compose(self) -> ComposeResult:
        help_text = """
## Commands

**`/help`** - Show this help
**`/new`** - Start new conversation  
**`/model`** - Change AI model
**`/models`** - List available models
**`/theme`** - Change color theme
**`/themes`** - List available themes
**`/search`** - Toggle auto law search
**`/clear`** - Clear current chat
**`/delete`** - Delete current session
**`/quit`** - Exit application

## Keyboard Shortcuts

**`Ctrl+N`** - New conversation
**`Ctrl+T`** - Change theme
**`Ctrl+Q`** - Quit
**`F1`** - Show help
**`Tab`** - Switch focus
"""
        with Container(id="help-dialog"):
            yield Label("⚖️ LawBot Help", id="help-title")
            yield Markdown(help_text)
            yield Label("[dim]Press Escape or Enter to close[/]")
    
    def action_close(self) -> None:
        self.dismiss(None)


class ConfirmDeleteScreen(ModalScreen[bool]):
    """Confirmation dialog for deletion."""
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]
    
    def __init__(self, session_title: str):
        super().__init__()
        self.session_title = session_title
    
    def compose(self) -> ComposeResult:
        with Container(id="confirm-dialog"):
            yield Label("🗑️ Delete conversation?", id="confirm-title")
            yield Label(f"[dim]{self.session_title}[/]")
            with Horizontal(id="confirm-buttons"):
                yield Button("Delete", variant="error", id="confirm-yes")
                yield Button("Cancel", variant="primary", id="confirm-no")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")
    
    def action_cancel(self) -> None:
        self.dismiss(False)


class MessageWidget(Static):
    """A single chat message."""
    
    def __init__(self, role: str, content: str, sources: list = None):
        super().__init__()
        self.role = role
        self.content = content
        self.sources = sources or []
    
    def compose(self) -> ComposeResult:
        is_user = self.role == "user"
        container_class = "user-message" if is_user else "assistant-message"
        label_class = "user-label" if is_user else "assistant-label"
        label_text = "⬤ You" if is_user else "⬤ LawBot"
        
        with Container(classes=f"message-container {container_class}"):
            yield Label(label_text, classes=label_class)
            yield Markdown(self.content)
            
            if self.sources and not is_user:
                with Container(classes="sources-panel"):
                    yield Label("📚 Sources", classes="sources-title")
                    for s in self.sources[:3]:
                        yield Label(f"  • {s['cite']} - {s['title'][:40]}...")


class LawBotApp(App):
    """Main TUI application."""
    
    TITLE = "LawBot"
    SUB_TITLE = "Georgia Legal Assistant"
    
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+n", "new_chat", "New Chat", show=True),
        Binding("ctrl+t", "change_theme", "Theme", show=True),
        Binding("f1", "help", "Help", show=True),
    ]
    
    # Reactive state
    current_session: reactive[Optional[Session]] = reactive(None)
    is_loading: reactive[bool] = reactive(False)
    auto_search: reactive[bool] = reactive(True)
    
    def __init__(self, config: Config, show_splash: bool = True):
        super().__init__()
        self.config = config
        self.llm: Optional[LLMClient] = None
        self.auto_search = config.auto_search
        self.show_splash = show_splash
        self.app_theme = get_theme(config.theme)
        
        # Set CSS from theme
        self.CSS = generate_css(self.app_theme)
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        with Horizontal(id="app-grid"):
            # Sidebar
            with Vertical(id="sidebar"):
                yield Static("📜 History", id="sidebar-header")
                yield ListView(id="session-list")
                with Container(id="sidebar-footer"):
                    yield Button("+ New Chat", id="new-chat-btn", variant="primary")
            
            # Main chat panel
            with Vertical(id="main-panel"):
                # Status bar
                with Horizontal(id="status-bar"):
                    yield Static("", id="model-status", classes="status-item")
                    yield Static("", id="search-status", classes="status-item")
                    yield Static("", id="theme-status", classes="status-item")
                
                # Chat messages
                yield ScrollableContainer(id="chat-container")
                
                # Loading indicator
                with Container(id="loading-container"):
                    yield LoadingIndicator()
                    yield Label("Thinking...", id="loading-label")
                
                # Input area
                with Container(id="input-area"):
                    yield Input(
                        placeholder="Ask about Georgia law... (/help for commands)",
                        id="message-input",
                    )
        
        yield Footer()
    
    async def on_mount(self) -> None:
        """Initialize on mount."""
        # Show splash screen
        if self.show_splash:
            await self.push_screen(SplashScreen())
        
        # Initialize LLM
        try:
            self.llm = get_llm_client(self.config)
        except ValueError as e:
            self.notify(str(e), severity="error", timeout=10)
        
        # Load sessions
        await self.refresh_session_list()
        
        # Start new session
        self.action_new_chat()
        
        # Update status
        self.update_status()
        
        # Focus input
        self.query_one("#message-input", Input).focus()
    
    async def refresh_session_list(self) -> None:
        """Refresh the session list in sidebar."""
        sessions = list_sessions(limit=20)
        list_view = self.query_one("#session-list", ListView)
        
        await list_view.clear()
        
        for s in sessions:
            title = s["title"][:22] + "..." if len(s["title"]) > 22 else s["title"]
            meta = f"{s['message_count']} msgs"
            
            item = ListItem(
                Static(f"{title}\n[dim]{meta}[/]", classes="session-title"),
                id=f"session-{s['session_id']}",
            )
            await list_view.append(item)
    
    def update_status(self) -> None:
        """Update the status bar."""
        model_status = self.query_one("#model-status", Static)
        search_status = self.query_one("#search-status", Static)
        theme_status = self.query_one("#theme-status", Static)
        
        model_status.update(f"[dim]Model:[/] [bold]{self.config.model}[/]")
        
        search_state = "[green]ON[/]" if self.auto_search else "[dim]OFF[/]"
        search_status.update(f"[dim]Search:[/] {search_state}")
        
        theme_status.update(f"[dim]Theme:[/] {self.app_theme.name}")
    
    def watch_is_loading(self, loading: bool) -> None:
        """React to loading state changes."""
        container = self.query_one("#loading-container")
        if loading:
            container.add_class("visible")
        else:
            container.remove_class("visible")
    
    def action_new_chat(self) -> None:
        """Start a new chat session."""
        if self.current_session and self.current_session.messages:
            self.current_session.save()
        
        self.current_session = Session()
        
        # Clear chat display
        chat_container = self.query_one("#chat-container", ScrollableContainer)
        chat_container.remove_children()
        
        # Add welcome message
        welcome = MessageWidget(
            "assistant",
            "**Welcome to LawBot!** 🏛️\n\n"
            "I'm your Georgia legal research assistant. I can help you with:\n\n"
            "• **Georgia Statutes** (O.C.G.A.)\n"
            "• **Case Law** from GA Supreme Court & Court of Appeals\n"
            "• **Local Ordinances** from counties and cities\n\n"
            "Ask me anything about Georgia law. Type `/help` for commands.",
        )
        chat_container.mount(welcome)
        
        self.update_status()
        self.notify("Started new conversation", timeout=2)
    
    def action_help(self) -> None:
        """Show help modal."""
        self.push_screen(HelpScreen())
    
    async def action_change_theme(self) -> None:
        """Show theme selection modal."""
        result = await self.push_screen_wait(
            ThemeSelectScreen(self.config.theme)
        )
        if result:
            self.config.set("ui", "theme", result)
            self.config.save()
            self.app_theme = get_theme(result)
            
            # Need to restart to apply new theme CSS
            self.notify(f"Theme changed to {self.app_theme.name}. Restart to apply.", timeout=3)
            self.update_status()
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "new-chat-btn":
            self.action_new_chat()
            await self.refresh_session_list()
    
    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle session selection from sidebar."""
        if event.item and event.item.id and event.item.id.startswith("session-"):
            session_id = event.item.id.replace("session-", "")
            await self.load_session(session_id)
    
    async def load_session(self, session_id: str) -> None:
        """Load a session by ID."""
        session = Session.load(session_id)
        if not session:
            self.notify(f"Session not found: {session_id}", severity="error")
            return
        
        # Save current if needed
        if self.current_session and self.current_session.messages:
            self.current_session.save()
        
        self.current_session = session
        
        # Rebuild chat display
        chat_container = self.query_one("#chat-container", ScrollableContainer)
        chat_container.remove_children()
        
        for msg in session.messages:
            widget = MessageWidget(
                msg.role,
                msg.content,
                sources=msg.search_results,
            )
            chat_container.mount(widget)
        
        chat_container.scroll_end(animate=False)
        self.update_status()
        self.notify(f"Loaded: {session.title or session.session_id}", timeout=2)
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle message submission."""
        message = event.value.strip()
        if not message:
            return
        
        # Clear input
        event.input.value = ""
        
        # Handle commands
        if message.startswith("/"):
            await self.handle_command(message)
            return
        
        # Regular chat message
        await self.send_message(message)
    
    async def handle_command(self, cmd: str) -> None:
        """Handle slash commands."""
        parts = cmd.lower().split(maxsplit=1)
        command = parts[0]
        arg = parts[1] if len(parts) > 1 else ""
        
        if command in ("/quit", "/exit", "/q"):
            self.exit()
        
        elif command == "/help":
            self.action_help()
        
        elif command == "/new":
            self.action_new_chat()
            await self.refresh_session_list()
        
        elif command == "/model":
            result = await self.push_screen_wait(
                ModelSelectScreen(self.config.model, self.config.provider)
            )
            if result:
                self.config.set("llm", "model", result)
                self.config.save()
                try:
                    self.llm = get_llm_client(self.config)
                    self.update_status()
                    self.notify(f"Switched to {result}", timeout=2)
                except ValueError as e:
                    self.notify(str(e), severity="error")
        
        elif command == "/models":
            models = MODELS.get(self.config.provider, [])
            current = self.config.model
            model_list = "\n".join(
                f"{'→ ' if m == current else '  '}{m}" for m in models
            )
            self.notify(f"Available models:\n{model_list}", timeout=5)
        
        elif command == "/theme":
            await self.action_change_theme()
        
        elif command == "/themes":
            themes = list_themes()
            current = self.config.theme
            theme_list = "\n".join(
                f"{'→ ' if t == current else '  '}{get_theme(t).name}" for t in themes
            )
            self.notify(f"Available themes:\n{theme_list}", timeout=5)
        
        elif command == "/search":
            self.auto_search = not self.auto_search
            state = "enabled" if self.auto_search else "disabled"
            self.update_status()
            self.notify(f"Auto search {state}", timeout=2)
        
        elif command == "/clear":
            chat_container = self.query_one("#chat-container", ScrollableContainer)
            chat_container.remove_children()
        
        elif command == "/delete":
            if self.current_session:
                result = await self.push_screen_wait(
                    ConfirmDeleteScreen(self.current_session.title or "Untitled")
                )
                if result:
                    delete_session(self.current_session.session_id)
                    self.action_new_chat()
                    await self.refresh_session_list()
                    self.notify("Session deleted", timeout=2)
        
        else:
            self.notify(f"Unknown command: {command}", severity="warning", timeout=3)
    
    @work(exclusive=True)
    async def send_message(self, message: str) -> None:
        """Send a message and get response."""
        if not self.llm:
            self.notify("LLM not configured. Run 'lawbot setup'", severity="error")
            return
        
        chat_container = self.query_one("#chat-container", ScrollableContainer)
        
        # Search for relevant laws
        search_results = []
        if self.auto_search:
            self.is_loading = True
            self.query_one("#loading-label", Label).update("Searching laws...")
            
            search_results = await asyncio.to_thread(
                search_laws, message, self.config
            )
        
        # Add user message
        self.current_session.add_message("user", message, search_results=search_results)
        user_widget = MessageWidget("user", message)
        chat_container.mount(user_widget)
        chat_container.scroll_end()
        
        # Get AI response
        self.is_loading = True
        self.query_one("#loading-label", Label).update("Thinking...")
        
        try:
            messages = self.current_session.get_api_messages()
            
            # Stream response
            full_response = ""
            response_widget = MessageWidget("assistant", "▌", sources=search_results)
            chat_container.mount(response_widget)
            
            stream = await asyncio.to_thread(
                lambda: self.llm.chat(messages, stream=True)
            )
            
            for chunk in stream:
                full_response += chunk
                response_widget.content = full_response + "▌"
                md = response_widget.query_one(Markdown)
                await md.update(full_response + "▌")
                chat_container.scroll_end()
            
            # Final update
            response_widget.content = full_response
            md = response_widget.query_one(Markdown)
            await md.update(full_response)
            
            # Save to session
            self.current_session.add_message("assistant", full_response)
            self.current_session.save()
            
            await self.refresh_session_list()
            
        except Exception as e:
            self.notify(f"Error: {e}", severity="error", timeout=5)
        
        finally:
            self.is_loading = False
            chat_container.scroll_end()


def run_tui(config: Config, show_splash: bool = True) -> None:
    """Run the TUI application."""
    app = LawBotApp(config, show_splash=show_splash)
    app.run()
