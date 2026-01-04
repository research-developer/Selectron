"""
Selectron App-Specific Page Objects

Pre-built Page Object Models for common Electron applications.
"""

from .claude import ClaudePage, ChatInputComponent, ConversationComponent, MessageComponent
from .obsidian import (
    ObsidianPage,
    RibbonActionComponent,
    TabHeaderComponent,
    QuickSwitcherComponent,
    CommandPaletteComponent as ObsidianCommandPaletteComponent,
    FileExplorerComponent as ObsidianFileExplorerComponent,
    EditorComponent as ObsidianEditorComponent,
)
from .cursor import (
    CursorPage,
    EditorTabComponent,
    FileExplorerComponent as CursorFileExplorerComponent,
    TerminalComponent,
    AIChatComponent,
    NotebookCellComponent,
    CommandCenterComponent,
    StatusBarComponent,
)

__all__ = [
    # Claude
    'ClaudePage',
    'ChatInputComponent',
    'ConversationComponent',
    'MessageComponent',
    # Obsidian
    'ObsidianPage',
    'RibbonActionComponent',
    'TabHeaderComponent',
    'QuickSwitcherComponent',
    'ObsidianCommandPaletteComponent',
    'ObsidianFileExplorerComponent',
    'ObsidianEditorComponent',
    # Cursor
    'CursorPage',
    'EditorTabComponent',
    'CursorFileExplorerComponent',
    'TerminalComponent',
    'AIChatComponent',
    'NotebookCellComponent',
    'CommandCenterComponent',
    'StatusBarComponent',
]
