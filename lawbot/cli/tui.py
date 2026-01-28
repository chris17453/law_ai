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
    """Modal for selecting a model with live preview."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, current_model: str, provider: str, app_instance):
        super().__init__()
        self.current_model = current_model
        self.original_model = current_model
        self.provider = provider
        self.app_instance = app_instance

    def compose(self) -> ComposeResult:
        models = MODELS.get(self.provider, MODELS["openai"])

        with Container(id="model-dialog"):
            yield Label("🤖 Select Model", id="model-dialog-title")
            yield ListView(
                *[ListItem(Label(m), id=f"model-{m}") for m in models],
                id="model-list",
            )
            yield Label("[dim]↑↓ Navigate • Enter to select • Escape to cancel[/]")

    def on_mount(self) -> None:
        try:
            list_view = self.query_one("#model-list", ListView)
            models = MODELS.get(self.provider, MODELS["openai"])
            if self.current_model in models:
                idx = models.index(self.current_model)
                list_view.index = idx
        except (NoMatches, ValueError):
            pass

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Preview model as user navigates."""
        models = MODELS.get(self.provider, MODELS["openai"])
        if event.list_view.index is not None and event.list_view.index < len(models):
            selected_model = models[event.list_view.index]
            self._apply_model_preview(selected_model)

    def _apply_model_preview(self, model_name: str) -> None:
        """Apply model preview to status bar."""
        self.app_instance.config.set("llm", "model", model_name)
        self.app_instance.update_status()
        self.current_model = model_name

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Confirm model selection."""
        models = MODELS.get(self.provider, MODELS["openai"])
        if event.list_view.index is not None and event.list_view.index < len(models):
            self.dismiss(models[event.list_view.index])

    def action_cancel(self) -> None:
        """Cancel and revert to original model."""
        if self.current_model != self.original_model:
            self._apply_model_preview(self.original_model)
        self.dismiss(None)


class ThemeSelectScreen(ModalScreen[str]):
    """Modal for selecting a theme with live preview."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, current_theme: str, app_instance):
        super().__init__()
        self.current_theme = current_theme
        self.original_theme = current_theme
        self.app_instance = app_instance

    def compose(self) -> ComposeResult:
        themes = list_themes()

        with Container(id="theme-dialog"):
            yield Label("🎨 Select Theme", id="theme-dialog-title")
            yield ListView(
                *[ListItem(Label(f"  {get_theme(t).name}"), id=f"theme-{t}") for t in themes],
                id="theme-list",
            )
            yield Label("[dim]↑↓ Navigate (live preview) • Enter to save • Escape to cancel[/]")

    def on_mount(self) -> None:
        try:
            list_view = self.query_one("#theme-list", ListView)
            themes = list_themes()
            if self.current_theme in themes:
                idx = themes.index(self.current_theme)
                list_view.index = idx
                # Show current theme name in title
                theme = get_theme(self.current_theme)
                title_label = self.query_one("#theme-dialog-title", Label)
                title_label.update(f"🎨 Select Theme - {theme.name}")
        except (NoMatches, ValueError):
            pass

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Preview theme as user navigates."""
        themes = list_themes()
        if event.list_view.index is not None and event.list_view.index < len(themes):
            selected_theme = themes[event.list_view.index]
            self._apply_theme_preview(selected_theme)

    def _apply_theme_preview(self, theme_name: str) -> None:
        """Apply theme immediately by updating widget styles."""
        theme = get_theme(theme_name)
        self.current_theme = theme_name
        app = self.app_instance

        # Update app theme reference
        app.app_theme = theme

        # Update title to show selected theme
        title_label = self.query_one("#theme-dialog-title", Label)
        title_label.update(f"🎨 Select Theme - {theme.name}")

        # Apply theme colors to all widgets directly
        try:
            # Update app-grid (main container)
            app_grid = app.query_one("#app-grid")
            app_grid.styles.background = theme.background
            app_grid.refresh()

            # Update sidebar
            sidebar = app.query_one("#sidebar")
            sidebar.styles.background = theme.surface
            sidebar.styles.border = ("solid", theme.primary)
            sidebar.refresh()

            # Update sidebar header
            sidebar_header = app.query_one("#sidebar-header")
            sidebar_header.styles.background = theme.primary
            sidebar_header.styles.color = theme.text
            sidebar_header.refresh()

            # Update main panel
            main_panel = app.query_one("#main-panel")
            main_panel.styles.background = theme.background
            main_panel.refresh()

            # Update chat container
            chat_container = app.query_one("#chat-container")
            chat_container.styles.background = theme.background
            chat_container.refresh()

            # Update status bar
            status_bar = app.query_one("#status-bar")
            status_bar.styles.background = theme.surface
            status_bar.refresh()

            # Update input area
            input_area = app.query_one("#input-area")
            input_area.styles.background = theme.surface
            input_area.styles.border = ("solid", theme.primary)
            input_area.refresh()

            # Update message input
            message_input = app.query_one("#message-input")
            message_input.styles.background = theme.background
            message_input.styles.border = ("solid", theme.accent)
            message_input.refresh()

            # Update Header and Footer
            try:
                header = app.query_one("Header")
                header.styles.background = theme.primary
                header.styles.color = theme.text
                header.refresh()
            except:
                pass

            try:
                footer = app.query_one("Footer")
                footer.styles.background = theme.surface
                footer.styles.color = theme.text
                footer.refresh()
            except:
                pass

            # Force refresh of all screens
            app.screen.refresh(repaint=True)
            app.update_status()

        except Exception as e:
            pass  # Silently handle if widgets don't exist yet

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Confirm theme selection."""
        themes = list_themes()
        if event.list_view.index is not None and event.list_view.index < len(themes):
            self.dismiss(themes[event.list_view.index])

    def action_cancel(self) -> None:
        """Cancel and revert to original theme."""
        if self.current_theme != self.original_theme:
            self._apply_theme_preview(self.original_theme)
        self.dismiss(None)


class LawDetailScreen(Screen):
    """Full-screen viewer for a single law."""

    BINDINGS = [
        Binding("escape", "close", "Back"),
        Binding("o", "open_browser", "Open in Browser"),
    ]

    def __init__(self, law_data: dict, config: Config):
        super().__init__()
        self.law_data = law_data
        self.config = config

    def compose(self) -> ComposeResult:
        yield Header()

        with Container(id="law-detail-container"):
            # Law header info
            yield Label(f"📜 {self.law_data.get('cite', 'N/A')}", id="law-detail-cite")
            yield Label(f"{self.law_data.get('title', 'Untitled')}", id="law-detail-title")
            yield Label(
                f"Source: {self.law_data.get('source', 'Unknown')} | "
                f"Jurisdiction: {self.law_data.get('jurisdiction', 'Unknown')}",
                id="law-detail-source"
            )

            # Full text in scrollable area
            with ScrollableContainer(id="law-detail-text-container"):
                full_text = self.law_data.get('full_text', 'No content available')
                yield Markdown(full_text, id="law-detail-text")

            # Action buttons
            with Horizontal(id="law-detail-actions"):
                if self.law_data.get('url'):
                    yield Button("Open in Browser (O)", id="open-browser-btn", variant="primary")
                yield Button("Back (Esc)", id="back-btn", variant="default")

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "open-browser-btn":
            self.action_open_browser()
        elif event.button.id == "back-btn":
            self.action_close()

    def action_open_browser(self) -> None:
        """Open law in browser."""
        url = self.law_data.get('url')
        if url:
            import webbrowser
            webbrowser.open(url)
            self.notify(f"Opening {self.law_data.get('cite', 'law')} in browser...", timeout=2)
        else:
            self.notify("No URL available", severity="warning", timeout=2)

    def action_close(self) -> None:
        """Close detail screen and return to browse."""
        self.app.pop_screen()


class BrowseLawsScreen(Screen):
    """Full-screen for browsing and searching all laws."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.current_results = []
        self.current_query = ""
        self.db_offset = 0
        self.batch_size = 50
        self.total_count = 0
        self.loading = False

    def compose(self) -> ComposeResult:
        yield Header()

        with Container(id="browse-container"):
            yield Label("📖 Browse Georgia Laws", id="browse-title")

            # Search input
            with Horizontal(id="browse-search-bar"):
                yield Input(placeholder="Search by citation or title...", id="browse-search-input")
                yield Button("Search", id="browse-search-btn", variant="primary")
                yield Button("Load All", id="browse-all-btn", variant="default")

            # Results list
            yield ListView(id="browse-results-list")

            yield Label("", id="browse-status")
            yield Label("↑↓ Navigate • Enter to view • O to open in browser • Escape to go back", id="browse-help")

        yield Footer()

    def on_mount(self) -> None:
        """Load initial results."""
        self.load_all_laws()

    def load_all_laws(self, query: str = "", reset: bool = True) -> None:
        """Load laws from database with lazy loading."""
        if self.loading:
            return

        self.loading = True

        with open("/tmp/lawbot_browse.log", "a") as f:
            f.write(f"\n=== load_all_laws called: query='{query}', reset={reset} ===\n")

        try:
            import psycopg2

            # Reset if new query
            if reset:
                self.current_query = query
                self.db_offset = 0
                self.current_results = []
                list_view = self.query_one("#browse-results-list", ListView)
                list_view.clear()
                with open("/tmp/lawbot_browse.log", "a") as f:
                    f.write(f"Reset: cleared list view\n")

            conn = psycopg2.connect(
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                database=self.config.postgres_db,
                user=self.config.postgres_user,
                password=self.config.postgres_password
            )
            cur = conn.cursor()

            # Get total count
            if reset:
                if query:
                    count_sql = """
                        SELECT COUNT(*) FROM documents
                        WHERE cite ILIKE %s OR title ILIKE %s OR full_text ILIKE %s
                    """
                    cur.execute(count_sql, (f"%{query}%", f"%{query}%", f"%{query}%"))
                else:
                    count_sql = "SELECT COUNT(*) FROM documents"
                    cur.execute(count_sql)

                self.total_count = cur.fetchone()[0]

            # Load batch
            if query:
                sql = """
                    SELECT cite, title, source, COALESCE(metadata->>'source_url', '') as source_url
                    FROM documents
                    WHERE cite ILIKE %s OR title ILIKE %s OR full_text ILIKE %s
                    ORDER BY cite
                    LIMIT %s OFFSET %s
                """
                cur.execute(sql, (f"%{query}%", f"%{query}%", f"%{query}%", self.batch_size, self.db_offset))
            else:
                sql = """
                    SELECT cite, title, source, COALESCE(metadata->>'source_url', '') as source_url
                    FROM documents
                    ORDER BY cite
                    LIMIT %s OFFSET %s
                """
                cur.execute(sql, (self.batch_size, self.db_offset))

            results = cur.fetchall()
            cur.close()
            conn.close()

            with open("/tmp/lawbot_browse.log", "a") as f:
                f.write(f"Query returned {len(results)} rows\n")

            # Append results
            list_view = self.query_one("#browse-results-list", ListView)
            for cite, title, source, url in results:
                self.current_results.append({
                    'cite': cite,
                    'title': title,
                    'source': source,
                    'url': url
                })

                # Show full title, cite, and source
                label = f"[bold]{cite or 'N/A'}[/bold] - {title or 'Untitled'}\n[dim]{source}[/dim]"
                list_view.append(ListItem(Static(label)))

            with open("/tmp/lawbot_browse.log", "a") as f:
                f.write(f"Added {len(results)} items to list_view\n")
                f.write(f"Total current_results: {len(self.current_results)}\n")

            self.db_offset += self.batch_size

            # Update status
            status_label = self.query_one("#browse-status", Label)
            status_label.update(
                f"Showing {len(self.current_results)} of {self.total_count} laws"
            )

            with open("/tmp/lawbot_browse.log", "a") as f:
                f.write(f"Status updated: {len(self.current_results)} of {self.total_count}\n")

            # Notify user about search results
            if reset and query:
                self.notify(f"Found {self.total_count} laws matching '{query}'", timeout=3)

        except Exception as e:
            with open("/tmp/lawbot_browse.log", "a") as f:
                f.write(f"ERROR: {e}\n")
                import traceback
                traceback.print_exc(file=f)
            self.notify(f"Error loading laws: {e}", severity="error", timeout=5)
        finally:
            self.loading = False
            with open("/tmp/lawbot_browse.log", "a") as f:
                f.write(f"Loading complete, loading={self.loading}\n")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "browse-search-btn":
            search_input = self.query_one("#browse-search-input", Input)
            query = search_input.value.strip()
            self.load_all_laws(query, reset=True)
        elif event.button.id == "browse-all-btn":
            self.load_all_laws("", reset=True)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input enter."""
        if event.input.id == "browse-search-input":
            query = event.value.strip()
            self.load_all_laws(query, reset=True)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Load more when scrolling near the bottom."""
        list_view = event.list_view
        # Load more when within 10 items of the end
        if (list_view.index is not None and
            list_view.index >= len(self.current_results) - 10 and
            len(self.current_results) < self.total_count):
            self.load_all_laws(self.current_query, reset=False)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """View selected law in detail screen."""
        if event.list_view.index is not None:
            law = self.current_results[event.list_view.index]
            cite = law.get('cite', 'Unknown')

            # Load full document from database
            try:
                import psycopg2

                conn = psycopg2.connect(
                    host=self.config.postgres_host,
                    port=self.config.postgres_port,
                    database=self.config.postgres_db,
                    user=self.config.postgres_user,
                    password=self.config.postgres_password
                )
                cur = conn.cursor()

                # Get full document with jurisdiction info
                sql = """
                    SELECT cite, title, full_text, source,
                           COALESCE(metadata->>'source_url', '') as source_url,
                           jurisdiction
                    FROM documents
                    WHERE cite = %s
                """
                cur.execute(sql, (cite,))
                result = cur.fetchone()

                cur.close()
                conn.close()

                if result:
                    cite_val, title, full_text, source, source_url, jurisdiction = result

                    law_data = {
                        'cite': cite_val,
                        'title': title,
                        'full_text': full_text or '',
                        'source': source or 'Unknown',
                        'url': source_url or '',
                        'jurisdiction': jurisdiction or 'GA'
                    }

                    # Push detail screen
                    self.app.push_screen(LawDetailScreen(law_data, self.config))
                else:
                    self.notify(f"Could not load full text for {cite}", severity="error", timeout=3)

            except Exception as e:
                self.notify(f"Error loading law: {e}", severity="error", timeout=5)

    def action_close(self) -> None:
        """Close browse screen and return to main."""
        self.app.pop_screen()

    def action_quit(self) -> None:
        """Quit the app."""
        self.app.exit()


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
**`/browse`** - Browse and search all Georgia laws
**`/model`** - Change AI model (with preview)
**`/models`** - List available models
**`/theme`** - Change color theme (with preview)
**`/themes`** - List available themes
**`/config`** - Show current configuration
**`/search`** - Toggle auto law search
**`/clear`** - Clear current chat
**`/delete`** - Delete current session
**`/quit`** - Exit application

## Keyboard Shortcuts

**`Ctrl+N`** - New conversation
**`Ctrl+B`** - Browse laws
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


class MessageWidget(Container):
    """A single chat message."""

    def __init__(self, role: str, content: str, sources: list = None):
        super().__init__()
        self.role = role
        self.content = content
        self.sources = sources or []

        # Debug logging
        if self.sources and role == "assistant":
            with open("/tmp/lawbot_widget.log", "a") as f:
                f.write(f"\n=== MessageWidget created with {len(self.sources)} sources ===\n")
                for idx, s in enumerate(self.sources):
                    f.write(f"  {idx}: {s.get('cite')} - {s.get('title', '')[:40]}\n")

    def compose(self) -> ComposeResult:
        is_user = self.role == "user"
        label_text = "⬤ You" if is_user else "⬤ LawBot"
        label_class = "user-label" if is_user else "assistant-label"
        msg_class = "user-message" if is_user else "assistant-message"

        # Debug logging
        with open("/tmp/lawbot_compose.log", "a") as f:
            f.write(f"compose() called - role={self.role}, sources={len(self.sources)}\n")

        yield Label(label_text, classes=label_class)

        # Show sources at the TOP for assistant messages BEFORE the response
        if self.sources and not is_user:
            with open("/tmp/lawbot_compose.log", "a") as f:
                f.write(f"  -> Rendering {len(self.sources)} source links\n")

            try:
                with Vertical(classes="sources-panel-top"):
                    yield Static(f"📚 Referenced Statutes ({len(self.sources)}):", classes="sources-title")

                    # Use Horizontal container for flowing links
                    with Horizontal(classes="sources-links-container"):
                        for idx, s in enumerate(self.sources):
                            cite = s.get('cite', 'N/A')
                            title = s.get('title', 'Untitled')
                            url = s.get('url', '')

                            with open("/tmp/lawbot_compose.log", "a") as f:
                                f.write(f"    Creating link widget for: {cite}\n")

                            # Create clickable statute link (compact) as Button for easier clicking
                            btn = Button(
                                cite,
                                id=f"statute-btn-{idx}-{id(self)}",
                                classes="statute-link",
                                variant="default"
                            )
                            btn.statute_url = url
                            btn.statute_cite = cite
                            btn.statute_title = title
                            yield btn
            except Exception as e:
                # Log error but don't crash the widget
                with open("/tmp/lawbot_compose_error.log", "a") as f:
                    f.write(f"Error composing sources panel: {e}\n")
                    import traceback
                    traceback.print_exc(file=f)

        yield Markdown(self.content, classes=msg_class)


class LawBotApp(App):
    """Main TUI application."""
    
    TITLE = "LawBot"
    SUB_TITLE = "Georgia Legal Assistant"
    
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+n", "new_chat", "New Chat", show=True),
        Binding("ctrl+b", "browse_laws", "Browse Laws", show=True),
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

        # Start new session (suppress notification on boot)
        self.action_new_chat(show_notification=False)

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
    
    def action_new_chat(self, show_notification: bool = True) -> None:
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
        if show_notification:
            self.notify("Started new conversation", timeout=2)
    
    def action_help(self) -> None:
        """Show help modal."""
        self.push_screen(HelpScreen())

    def action_browse_laws(self) -> None:
        """Open browse laws screen."""
        self.push_screen(BrowseLawsScreen(self.config))

    async def open_statute_detail(self, cite: str) -> None:
        """Open a statute detail view by citation."""
        try:
            import psycopg2

            conn = psycopg2.connect(
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                database=self.config.postgres_db,
                user=self.config.postgres_user,
                password=self.config.postgres_password
            )
            cur = conn.cursor()

            # Get full document
            sql = """
                SELECT cite, title, full_text, source,
                       COALESCE(metadata->>'source_url', '') as source_url,
                       jurisdiction
                FROM documents
                WHERE cite = %s
            """
            cur.execute(sql, (cite,))
            result = cur.fetchone()

            cur.close()
            conn.close()

            if result:
                cite_val, title, full_text, source, source_url, jurisdiction = result

                law_data = {
                    'cite': cite_val,
                    'title': title,
                    'full_text': full_text or '',
                    'source': source or 'Unknown',
                    'url': source_url or '',
                    'jurisdiction': jurisdiction or 'GA'
                }

                # Push detail screen
                self.push_screen(LawDetailScreen(law_data, self.config))
            else:
                self.notify(f"Could not load {cite}", severity="error", timeout=3)

        except Exception as e:
            self.notify(f"Error loading statute: {e}", severity="error", timeout=5)

    def action_change_theme(self) -> None:
        """Show theme selection modal with live preview."""
        def handle_theme_result(result: str | None) -> None:
            if result:
                self.config.set("ui", "theme", result)
                self.config.save()
                theme_name = get_theme(result).name
                self.notify(f"Theme saved: {theme_name}", timeout=2)

        self.push_screen(ThemeSelectScreen(self.config.theme, self), handle_theme_result)
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        # Handle statute button clicks
        if event.button.id and "statute-btn-" in event.button.id:
            cite = getattr(event.button, 'statute_cite', None)
            with open("/tmp/lawbot_click.log", "a") as f:
                f.write(f"Statute button clicked: {event.button.id}, cite: {cite}\n")
            if cite:
                await self.open_statute_detail(cite)
            return

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
            # Debug: check if search_results are present
            if msg.search_results:
                self.notify(f"Loading {len(msg.search_results)} statutes for {msg.role} msg", timeout=1)

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

        # Clear input immediately to prevent double submission
        event.input.value = ""

        # Prevent processing if already loading
        if self.is_loading:
            return

        # Handle commands
        if message.startswith("/"):
            self.handle_command(message)
            return

        # Regular chat message
        self.send_message(message)

    @work(exclusive=False)
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

        elif command == "/browse":
            self.push_screen(BrowseLawsScreen(self.config))

        elif command == "/model":
            def handle_model_result(result: str | None) -> None:
                if result:
                    self.config.set("llm", "model", result)
                    self.config.save()
                    try:
                        self.llm = get_llm_client(self.config)
                        self.notify(f"Switched to {result}", timeout=2)
                    except ValueError as e:
                        self.notify(str(e), severity="error")

            self.push_screen(
                ModelSelectScreen(self.config.model, self.config.provider, self),
                handle_model_result
            )
        
        elif command == "/models":
            models = MODELS.get(self.config.provider, [])
            current = self.config.model
            model_list = "\n".join(
                f"{'→ ' if m == current else '  '}{m}" for m in models
            )
            self.notify(f"Available models:\n{model_list}", timeout=5)
        
        elif command == "/theme":
            self.action_change_theme()
        
        elif command == "/themes":
            themes = list_themes()
            current = self.config.theme
            theme_list = "\n".join(
                f"{'→ ' if t == current else '  '}{get_theme(t).name}" for t in themes
            )
            self.notify(f"Available themes:\n{theme_list}", timeout=5)

        elif command == "/config":
            from .config import get_config_path
            config_info = f"""**Current Configuration:**

**LLM Provider:** {self.config.provider}
**Model:** {self.config.model}
**Temperature:** {self.config.temperature}
**Max Tokens:** {self.config.max_tokens}

**Region:** {self.config.region}
**Auto Search:** {'Enabled' if self.config.auto_search else 'Disabled'}
**Query Expansion:** {'Enabled' if self.config.query_expansion else 'Disabled'}
**Search Limit:** {self.config.search_limit}

**Theme:** {self.app_theme.name}

**Config File:** {get_config_path()}

Use `lawbot config --edit` to edit the config file."""
            self.notify(config_info, timeout=10)

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
                async def handle_delete_result(result: bool) -> None:
                    if result:
                        delete_session(self.current_session.session_id)
                        self.action_new_chat()
                        await self.refresh_session_list()
                        self.notify("Session deleted", timeout=2)

                self.push_screen(
                    ConfirmDeleteScreen(self.current_session.title or "Untitled"),
                    handle_delete_result
                )
        
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
                search_laws, message, self.config, None, self.config.query_expansion
            )

            # Debug: show how many sources found
            if search_results:
                self.notify(f"Found {len(search_results)} relevant statutes", timeout=2)

        # Add user message (don't attach search results to user messages)
        self.current_session.add_message("user", message)
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

            # Create assistant message widget with statute sources
            with open("/tmp/lawbot_send.log", "a") as f:
                f.write(f"\n=== Creating response widget with {len(search_results)} sources ===\n")
                for idx, s in enumerate(search_results):
                    f.write(f"  {idx}: {s.get('cite')} - {s.get('title', '')[:40]}\n")

            response_widget = MessageWidget("assistant", "▌", sources=search_results)
            chat_container.mount(response_widget)

            with open("/tmp/lawbot_send.log", "a") as f:
                f.write(f"Widget mounted, widget.sources count: {len(response_widget.sources)}\n")
            
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
            
            # Save to session WITH search results so they persist
            self.current_session.add_message("assistant", full_response, search_results=search_results)
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
