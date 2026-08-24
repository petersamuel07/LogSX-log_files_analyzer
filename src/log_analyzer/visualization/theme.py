"""Colour themes for the chart figures.

The same figure builders (log_analyzer.visualization.figures) serve two very
different surfaces: PNG files exported to disk, which are viewed on a white
page, and the in-app dashboard, which renders on the GUI's dark panels. A
light chart dropped onto a dark panel reads as a glaring white rectangle, so
each surface gets its own theme rather than one compromise palette.

Both themes come from the same validated, colourblind-safe palette (see the
dataviz skill's references/palette.md): a single sequential blue for
magnitude-only charts, and the reserved status colours (good/warning/serious/
critical) for the log-level and HTTP-status charts, since DEBUG->CRITICAL and
2xx->5xx are genuinely severity scales rather than arbitrary categories. The
dark theme is that palette re-stepped for a dark surface, not an automatic
inversion of the light one.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChartTheme:
    """Every colour a figure needs, resolved for one surface (light or dark)."""

    name: str

    # Chrome.
    surface: str
    ink_primary: str
    ink_secondary: str
    ink_muted: str
    gridline: str
    baseline: str

    # Data marks.
    sequential: str
    """Single hue for magnitude-only charts (volume, counts, latency)."""

    error: str
    """The 'serious' status step, used for error-message magnitude charts."""

    level_colors: dict[str, str] = field(default_factory=dict)
    status_colors: dict[str, str] = field(default_factory=dict)


LIGHT_THEME = ChartTheme(
    name="light",
    surface="#fcfcfb",
    ink_primary="#0b0b0b",
    ink_secondary="#52514e",
    ink_muted="#898781",
    gridline="#e1e0d9",
    baseline="#c3c2b7",
    sequential="#2a78d6",
    error="#ec835a",
    level_colors={
        "DEBUG": "#898781",
        "INFO": "#2a78d6",
        "WARNING": "#fab219",
        "ERROR": "#ec835a",
        "CRITICAL": "#d03b3b",
    },
    status_colors={"2xx": "#0ca30c", "3xx": "#2a78d6", "4xx": "#fab219", "5xx": "#d03b3b"},
)

# Surface matches the GUI's card colour (gui.app.Palette.surface) so an embedded
# figure sits flush in its panel with no visible plate around it. Every mark
# colour below clears 3:1 against that surface.
DARK_THEME = ChartTheme(
    name="dark",
    surface="#1a1d26",
    ink_primary="#e8eaf0",
    ink_secondary="#a9b0c2",
    ink_muted="#8b93a7",
    gridline="#2b3040",
    baseline="#3a4055",
    sequential="#3987e5",
    error="#ec835a",
    level_colors={
        "DEBUG": "#8b93a7",
        "INFO": "#3987e5",
        "WARNING": "#fab219",
        "ERROR": "#ec835a",
        "CRITICAL": "#d03b3b",
    },
    status_colors={"2xx": "#0ca30c", "3xx": "#3987e5", "4xx": "#fab219", "5xx": "#d03b3b"},
)
