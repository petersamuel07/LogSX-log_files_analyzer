"""The GUI colour palette, shared by the main window and the dashboard views.

Kept in its own module so ``gui.app`` and ``gui.dashboard`` can both import it
without importing each other — the window builds the dashboard views, so the
dependency has to run one way only.
"""

from __future__ import annotations


class Palette:
    """Single source of truth for every colour used in the window."""

    bg = "#12141a"          # window background
    surface = "#1a1d26"     # cards / panels
    surface_alt = "#20242f"  # nested panels (tiles inside a card)
    border = "#2b3040"
    header = "#0d0f14"

    text = "#e8eaf0"
    text_muted = "#8b93a7"
    text_dim = "#5f6779"

    accent = "#4f8cff"
    accent_hover = "#6b9dff"
    accent_press = "#3c73dd"

    success = "#3ecf8e"
    warning = "#f5a623"
    error = "#ff6b6b"

    console_bg = "#0e1015"
