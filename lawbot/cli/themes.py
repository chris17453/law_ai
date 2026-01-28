"""Theme definitions for LawBot TUI."""

from dataclasses import dataclass
from typing import Dict


@dataclass
class Theme:
    """Color theme definition."""
    name: str
    primary: str
    secondary: str
    accent: str
    background: str
    surface: str
    surface_light: str
    text: str
    text_muted: str
    error: str
    warning: str
    success: str


# Available themes
THEMES: Dict[str, Theme] = {
    "dark": Theme(
        name="Dark",
        primary="#00d787",
        secondary="#0087ff",
        accent="#ff79c6",
        background="#1a1a2e",
        surface="#16213e",
        surface_light="#1f3460",
        text="#f8f8f2",
        text_muted="#6272a4",
        error="#ff5555",
        warning="#f1fa8c",
        success="#50fa7b",
    ),
    "light": Theme(
        name="Light",
        primary="#0d7377",
        secondary="#14919b",
        accent="#7c3aed",
        background="#f5f5f5",
        surface="#ffffff",
        surface_light="#e5e5e5",
        text="#1f2937",
        text_muted="#6b7280",
        error="#dc2626",
        warning="#d97706",
        success="#059669",
    ),
    "hacker": Theme(
        name="Hacker",
        primary="#00ff00",
        secondary="#00cc00",
        accent="#ffff00",
        background="#0a0a0a",
        surface="#0d0d0d",
        surface_light="#1a1a1a",
        text="#00ff00",
        text_muted="#006600",
        error="#ff0000",
        warning="#ffff00",
        success="#00ff00",
    ),
    "dracula": Theme(
        name="Dracula",
        primary="#bd93f9",
        secondary="#8be9fd",
        accent="#ff79c6",
        background="#282a36",
        surface="#44475a",
        surface_light="#6272a4",
        text="#f8f8f2",
        text_muted="#6272a4",
        error="#ff5555",
        warning="#f1fa8c",
        success="#50fa7b",
    ),
    "nord": Theme(
        name="Nord",
        primary="#88c0d0",
        secondary="#81a1c1",
        accent="#b48ead",
        background="#2e3440",
        surface="#3b4252",
        surface_light="#434c5e",
        text="#eceff4",
        text_muted="#4c566a",
        error="#bf616a",
        warning="#ebcb8b",
        success="#a3be8c",
    ),
    "monokai": Theme(
        name="Monokai",
        primary="#a6e22e",
        secondary="#66d9ef",
        accent="#f92672",
        background="#272822",
        surface="#3e3d32",
        surface_light="#49483e",
        text="#f8f8f2",
        text_muted="#75715e",
        error="#f92672",
        warning="#e6db74",
        success="#a6e22e",
    ),
    "solarized": Theme(
        name="Solarized Dark",
        primary="#2aa198",
        secondary="#268bd2",
        accent="#d33682",
        background="#002b36",
        surface="#073642",
        surface_light="#586e75",
        text="#839496",
        text_muted="#657b83",
        error="#dc322f",
        warning="#b58900",
        success="#859900",
    ),
    "gruvbox": Theme(
        name="Gruvbox",
        primary="#b8bb26",
        secondary="#83a598",
        accent="#d3869b",
        background="#282828",
        surface="#3c3836",
        surface_light="#504945",
        text="#ebdbb2",
        text_muted="#928374",
        error="#fb4934",
        warning="#fabd2f",
        success="#b8bb26",
    ),
}


def get_theme(name: str) -> Theme:
    """Get a theme by name, defaulting to dark."""
    return THEMES.get(name.lower(), THEMES["dark"])


def list_themes() -> list[str]:
    """List available theme names."""
    return list(THEMES.keys())


def generate_css(theme: Theme) -> str:
    """Generate Textual CSS from a theme."""
    return f"""
$primary: {theme.primary};
$secondary: {theme.secondary};
$accent: {theme.accent};
$background: {theme.background};
$surface: {theme.surface};
$surface-light: {theme.surface_light};
$text: {theme.text};
$text-muted: {theme.text_muted};
$error: {theme.error};
$warning: {theme.warning};
$success: {theme.success};

Screen {{
    background: $background;
    color: $text;
}}

#app-grid {{
    layout: grid;
    grid-size: 2;
    grid-columns: 1fr 4fr;
    grid-rows: 1fr;
    height: 100%;
}}

#sidebar {{
    width: 100%;
    height: 100%;
    background: $surface;
    border-right: solid $surface-light;
}}

#sidebar-header {{
    height: 3;
    background: $surface-light;
    content-align: center middle;
    text-style: bold;
    color: $primary;
}}

#session-list {{
    height: 1fr;
    scrollbar-gutter: stable;
}}

#session-list > ListItem {{
    padding: 0 1;
    height: 3;
}}

#session-list > ListItem:hover {{
    background: $surface-light;
}}

#session-list > ListItem.-active {{
    background: $secondary 30%;
}}

.session-title {{
    width: 100%;
}}

.session-meta {{
    color: $text-muted;
    text-style: italic;
}}

#sidebar-footer {{
    height: auto;
    padding: 1;
    background: $surface-light;
}}

#new-chat-btn {{
    width: 100%;
    margin: 0;
}}

#main-panel {{
    height: 100%;
}}

#chat-container {{
    height: 1fr;
    padding: 1 2;
    scrollbar-gutter: stable;
}}

MessageWidget {{
    width: 100%;
    height: auto;
    layout: vertical;
    margin-bottom: 2;
}}

.user-message {{
    padding: 0;
    margin: 0 0 1 2;
    width: 100%;
    height: auto;
}}

.user-label {{
    color: $secondary;
    text-style: bold;
    margin-bottom: 1;
    width: auto;
    height: 1;
}}

.assistant-message {{
    padding: 0;
    margin: 0 0 1 0;
    width: 100%;
    height: auto;
}}

.assistant-label {{
    color: $primary;
    text-style: bold;
    margin-bottom: 1;
    width: auto;
    height: 1;
}}

.sources-panel {{
    background: $surface-light;
    border: dashed $warning;
    padding: 1;
    margin: 1 0;
    height: auto;
}}

.sources-panel-top {{
    background: $accent 20%;
    border: thick $accent;
    padding: 1 2;
    margin: 0 0 2 0;
    height: auto;
    width: 100%;
}}

.sources-title {{
    color: $accent;
    text-style: bold;
    margin-bottom: 1;
    height: 1;
}}

.sources-links-container {{
    width: 100%;
    height: auto;
}}

.statute-link {{
    width: auto;
    min-width: 8;
    height: 1;
    margin: 0 1 0 0;
    padding: 0 1;
    text-align: center;
    background: $primary 30%;
    border: none;
    color: $text;
}}

.statute-link:hover {{
    background: $accent 40%;
    text-style: bold;
}}

.statute-link:focus {{
    background: $secondary 50%;
    text-style: bold;
}}

BrowseLawsScreen {{
    background: $background;
}}

#browse-container {{
    width: 100%;
    height: 100%;
    background: $background;
    padding: 2;
    layout: vertical;
}}

#browse-title {{
    color: $primary;
    text-style: bold;
    margin-bottom: 1;
    width: 100%;
    height: auto;
}}

#browse-search-bar {{
    width: 100%;
    height: auto;
    margin-bottom: 1;
}}

#browse-search-input {{
    width: 1fr;
}}

#browse-search-btn {{
    width: auto;
    margin-left: 1;
}}

#browse-all-btn {{
    width: auto;
    margin-left: 1;
}}

#browse-results-list {{
    width: 100%;
    height: 1fr;
    border: solid $accent;
    margin-bottom: 1;
    background: $surface;
}}

#browse-status {{
    color: $accent;
    text-align: center;
    width: 100%;
    height: auto;
    margin-bottom: 1;
}}

#browse-help {{
    color: $text 50%;
    text-align: center;
    width: 100%;
    height: auto;
}}

LawDetailScreen {{
    background: $background;
}}

#law-detail-container {{
    width: 100%;
    height: 100%;
    background: $background;
    padding: 2;
    layout: vertical;
}}

#law-detail-cite {{
    color: $primary;
    text-style: bold;
    width: 100%;
    height: auto;
    margin-bottom: 1;
}}

#law-detail-title {{
    color: $accent;
    text-style: bold;
    width: 100%;
    height: auto;
    margin-bottom: 1;
}}

#law-detail-source {{
    color: $text 70%;
    width: 100%;
    height: auto;
    margin-bottom: 2;
}}

#law-detail-text-container {{
    width: 100%;
    height: 1fr;
    background: $surface;
    border: solid $accent;
    padding: 2;
    margin-bottom: 1;
}}

#law-detail-text {{
    width: 100%;
    height: auto;
}}

#law-detail-actions {{
    width: 100%;
    height: auto;
}}

#input-area {{
    height: auto;
    padding: 1 2;
    background: $surface;
    border-top: solid $surface-light;
}}

#message-input {{
    width: 100%;
}}

#status-bar {{
    height: 1;
    background: $surface-light;
    padding: 0 2;
}}

.status-item {{
    margin-right: 2;
}}

.status-label {{
    color: $text-muted;
}}

.status-value {{
    color: $primary;
    text-style: bold;
}}

#loading-container {{
    height: 3;
    align: center middle;
    display: none;
}}

#loading-container.visible {{
    display: block;
}}

/* Splash screen */
#splash-container {{
    width: 100%;
    height: 100%;
    align: center middle;
    background: $background;
}}

#splash-logo {{
    text-align: center;
    color: $primary;
    padding: 2;
}}

#splash-subtitle {{
    text-align: center;
    color: $text-muted;
    margin-top: 1;
}}

#splash-prompt {{
    text-align: center;
    color: $secondary;
    margin-top: 2;
    text-style: bold;
}}

/* Modal styles */
ModelSelectScreen {{
    align: center middle;
}}

#model-dialog {{
    width: 60;
    height: auto;
    max-height: 80%;
    background: $surface;
    border: solid $primary;
    padding: 1 2;
}}

#model-dialog-title {{
    text-align: center;
    text-style: bold;
    margin-bottom: 1;
    color: $primary;
}}

#model-list {{
    height: auto;
    max-height: 20;
    margin-bottom: 1;
}}

#model-list > ListItem {{
    padding: 0 1;
}}

#model-list > ListItem:hover {{
    background: $surface-light;
}}

#model-list > ListItem.-selected {{
    background: $primary 30%;
}}

ThemeSelectScreen {{
    align: center middle;
}}

#theme-dialog {{
    width: 50;
    height: auto;
    max-height: 80%;
    background: $surface;
    border: solid $accent;
    padding: 1 2;
}}

#theme-dialog-title {{
    text-align: center;
    text-style: bold;
    margin-bottom: 1;
    color: $accent;
}}

#theme-list {{
    height: auto;
    max-height: 15;
    margin-bottom: 1;
}}

#theme-list > ListItem {{
    padding: 0 1;
}}

#theme-list > ListItem:hover {{
    background: $surface-light;
}}

HelpScreen {{
    align: center middle;
}}

#help-dialog {{
    width: 70;
    height: auto;
    background: $surface;
    border: solid $primary;
    padding: 2;
}}

#help-title {{
    text-align: center;
    text-style: bold;
    margin-bottom: 1;
    color: $primary;
}}

.help-section {{
    margin-bottom: 1;
}}

.help-cmd {{
    color: $primary;
    text-style: bold;
}}

ConfirmDeleteScreen {{
    align: center middle;
}}

#confirm-dialog {{
    width: 50;
    height: auto;
    background: $surface;
    border: solid $error;
    padding: 2;
}}

#confirm-buttons {{
    margin-top: 1;
    align: center middle;
}}

#confirm-buttons Button {{
    margin: 0 1;
}}
"""


# ASCII Art Logo
LOGO = r"""
    __                    ____        __ 
   / /   ____ __      __ / __ ) ____  / /_
  / /   / __ `/ | /| / // __  |/ __ \/ __/
 / /___/ /_/ /| |/ |/ // /_/ // /_/ / /_  
/_____/\__,_/ |__/|__//_____/ \____/\__/  
"""

LOGO_SMALL = r"""
 _                ___      _   
| |   __ ___ __ _| _ ) ___| |_ 
| |__/ _` \ V  V / _ \/ _ \  _|
|____\__,_|\_/\_/|___/\___/\__|
"""

SCALES_ART = r"""
        ___
    .-'   `-.
   /  .-=-.  \
  | (  @ @  ) |
   \  `---'  /
    `-.___.-'
       |||
      _|||_
     /     \
    |  |||  |
    |  |||  |
   _|  |||  |_
  (___________)
    |       |
    |  ===  |
    |       |
   /|       |\
  (_|_______|_)
"""

GAVEL_ART = r"""
      _____
     /     \
    |  ===  |
     \_____/
        |
        |
   _____|_____
  |           |
  |   LAWBOT  |
  |___________|
"""

SPLASH_ART = r"""
[bold cyan]
    __                    ____        __ 
   / /   ____ __      __ / __ ) ____  / /_
  / /   / __ `/ | /| / // __  |/ __ \/ __/
 / /___/ /_/ /| |/ |/ // /_/ // /_/ / /_  
/_____/\__,_/ |__/|__//_____/ \____/\__/  
[/]
[dim]═══════════════════════════════════════════[/]

[bold white]⚖️  Georgia Legal Research Assistant ⚖️[/]

[dim]Powered by AI • Statutes • Case Law • Ordinances[/]
"""
