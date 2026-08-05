"""Professional static charts for financial reports and presentations."""

import os
import tempfile
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "kapexai-matplotlib"),
)

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter


PathLike = Union[str, Path]
Number = Union[int, float]

NAVY = "#15253D"
BLUE = "#2878B5"
TEAL = "#2A9D8F"
GREEN = "#28A47B"
RED = "#D1495B"
GOLD = "#E9B44C"
LIGHT_BLUE = "#76B7E5"
SLATE = "#64748B"
GRID = "#DDE3EA"
BACKGROUND = "#F7F9FC"
TEXT = "#172033"
PALETTE = (BLUE, TEAL, GOLD, RED, LIGHT_BLUE, SLATE)


def _validate_lengths(labels: Sequence[str], series: Mapping[str, Sequence[Number]]) -> None:
    if not labels:
        raise ValueError("labels cannot be empty")
    for name, values in series.items():
        if len(values) != len(labels):
            raise ValueError(
                f"series '{name}' has {len(values)} values; expected {len(labels)}"
            )


def _value_formatter(style: str) -> FuncFormatter:
    def format_value(value: float, _position: int) -> str:
        if style == "currency":
            absolute = abs(value)
            if absolute >= 1_000_000_000:
                return f"${value / 1_000_000_000:.1f}B"
            if absolute >= 1_000_000:
                return f"${value / 1_000_000:.1f}M"
            if absolute >= 1_000:
                return f"${value / 1_000:.1f}K"
            return f"${value:,.0f}"
        if style == "percent":
            return f"{value:.1f}%"
        return f"{value:,.0f}"

    if style not in {"currency", "number", "percent"}:
        raise ValueError("value_style must be 'currency', 'number', or 'percent'")
    return FuncFormatter(format_value)


def _figure(title: str, subtitle: Optional[str], size: tuple[float, float]) -> tuple[Figure, Axes]:
    figure, axis = plt.subplots(figsize=size, facecolor=BACKGROUND)
    axis.set_facecolor(BACKGROUND)
    figure.suptitle(
        title,
        x=0.08,
        y=0.96,
        ha="left",
        color=TEXT,
        fontsize=18,
        fontweight="bold",
    )
    if subtitle:
        figure.text(0.08, 0.895, subtitle, color=SLATE, fontsize=10, ha="left")
    figure.subplots_adjust(left=0.08, right=0.96, bottom=0.14, top=0.82)
    return figure, axis


def _style_axis(axis: Axes, value_style: str, grid_axis: str = "y") -> None:
    axis.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)
    axis.tick_params(colors=SLATE, labelsize=9, length=0)
    axis.yaxis.set_major_formatter(_value_formatter(value_style))
    for spine in axis.spines.values():
        spine.set_visible(False)


def _save(figure: Figure, output_path: PathLike) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=200,
        facecolor=figure.get_facecolor(),
        bbox_inches="tight",
    )
    plt.close(figure)
    return str(path)


def create_line_chart(
    labels: Sequence[str],
    series: Mapping[str, Sequence[Number]],
    output_path: PathLike,
    *,
    title: str,
    subtitle: Optional[str] = None,
    value_style: str = "currency",
) -> str:
    """Create a multi-series trend chart with endpoint labels."""
    _validate_lengths(labels, series)
    figure, axis = _figure(title, subtitle, (10.8, 6.0))
    x_values = list(range(len(labels)))

    for index, (name, values) in enumerate(series.items()):
        color = PALETTE[index % len(PALETTE)]
        axis.plot(
            x_values,
            values,
            color=color,
            linewidth=2.6,
            marker="o",
            markersize=5,
            markerfacecolor=BACKGROUND,
            markeredgewidth=2,
            label=name,
        )
        axis.annotate(
            name,
            (x_values[-1], values[-1]),
            xytext=(8, 0),
            textcoords="offset points",
            color=color,
            fontsize=9,
            fontweight="bold",
            va="center",
        )

    axis.set_xticks(x_values, labels)
    axis.margins(x=0.08, y=0.16)
    _style_axis(axis, value_style)
    return _save(figure, output_path)


def create_bar_chart(
    labels: Sequence[str],
    series: Mapping[str, Sequence[Number]],
    output_path: PathLike,
    *,
    title: str,
    subtitle: Optional[str] = None,
    value_style: str = "currency",
    stacked: bool = False,
) -> str:
    """Create a grouped or stacked financial comparison chart."""
    _validate_lengths(labels, series)
    figure, axis = _figure(title, subtitle, (10.8, 6.0))
    x_values = list(range(len(labels)))
    series_items = list(series.items())
    width = 0.72 if stacked else 0.72 / max(len(series_items), 1)
    positive_bottom = [0.0] * len(labels)
    negative_bottom = [0.0] * len(labels)

    for index, (name, values) in enumerate(series_items):
        color = PALETTE[index % len(PALETTE)]
        if stacked:
            bottoms = [
                positive_bottom[i] if value >= 0 else negative_bottom[i]
                for i, value in enumerate(values)
            ]
            axis.bar(
                x_values,
                values,
                width=width,
                bottom=bottoms,
                color=color,
                label=name,
            )
            for i, value in enumerate(values):
                if value >= 0:
                    positive_bottom[i] += value
                else:
                    negative_bottom[i] += value
        else:
            offset = (index - (len(series_items) - 1) / 2) * width
            positions = [value + offset for value in x_values]
            axis.bar(positions, values, width=width * 0.88, color=color, label=name)

    axis.axhline(0, color=SLATE, linewidth=0.8)
    axis.set_xticks(x_values, labels)
    axis.legend(
        frameon=False,
        ncol=max(1, min(len(series_items), 4)),
        loc="upper left",
        labelcolor=TEXT,
    )
    axis.margins(x=0.04, y=0.14)
    _style_axis(axis, value_style)
    return _save(figure, output_path)


def create_waterfall_chart(
    labels: Sequence[str],
    changes: Sequence[Number],
    output_path: PathLike,
    *,
    title: str,
    subtitle: Optional[str] = None,
    value_style: str = "currency",
    total_label: str = "Ending value",
) -> str:
    """Create a bridge chart showing positive and negative value drivers."""
    if not labels or len(labels) != len(changes):
        raise ValueError("labels and changes must be non-empty and have equal lengths")

    running_total = 0.0
    bottoms = []
    colors = []
    for change in changes:
        next_total = running_total + change
        bottoms.append(min(running_total, next_total))
        colors.append(GREEN if change >= 0 else RED)
        running_total = next_total

    chart_labels = [*labels, total_label]
    chart_values = [abs(value) for value in changes] + [running_total]
    chart_bottoms = [*bottoms, 0]
    colors.append(NAVY)

    figure, axis = _figure(title, subtitle, (11.2, 6.0))
    x_values = list(range(len(chart_labels)))
    axis.bar(
        x_values,
        chart_values,
        bottom=chart_bottoms,
        width=0.68,
        color=colors,
    )

    cumulative = 0.0
    for index, change in enumerate(changes):
        cumulative += change
        axis.plot(
            [index + 0.34, index + 0.66],
            [cumulative, cumulative],
            color=SLATE,
            linewidth=1,
            linestyle="--",
        )

    axis.axhline(0, color=SLATE, linewidth=0.8)
    axis.set_xticks(x_values, chart_labels)
    axis.margins(x=0.04, y=0.16)
    _style_axis(axis, value_style)
    return _save(figure, output_path)


def create_donut_chart(
    labels: Sequence[str],
    values: Sequence[Number],
    output_path: PathLike,
    *,
    title: str,
    subtitle: Optional[str] = None,
    center_label: str = "Allocation",
) -> str:
    """Create a portfolio allocation donut with an external legend."""
    if not labels or len(labels) != len(values):
        raise ValueError("labels and values must be non-empty and have equal lengths")
    if any(value < 0 for value in values) or sum(values) <= 0:
        raise ValueError("donut values must be non-negative and total more than zero")

    figure, axis = _figure(title, subtitle, (10.8, 6.0))
    colors = [PALETTE[index % len(PALETTE)] for index in range(len(values))]
    wedges, _, _ = axis.pie(
        values,
        colors=colors,
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.36, "edgecolor": BACKGROUND, "linewidth": 2},
        autopct=lambda percent: f"{percent:.1f}%" if percent >= 4 else "",
        pctdistance=0.8,
        textprops={"color": TEXT, "fontsize": 9, "fontweight": "bold"},
    )
    axis.text(
        0,
        0,
        center_label,
        ha="center",
        va="center",
        color=TEXT,
        fontsize=12,
        fontweight="bold",
    )
    axis.legend(
        wedges,
        labels,
        loc="center left",
        bbox_to_anchor=(1.0, 0.5),
        frameon=False,
        labelcolor=TEXT,
    )
    axis.set_aspect("equal")
    return _save(figure, output_path)


def create_candlestick_chart(
    labels: Sequence[str],
    opens: Sequence[Number],
    highs: Sequence[Number],
    lows: Sequence[Number],
    closes: Sequence[Number],
    output_path: PathLike,
    *,
    title: str,
    subtitle: Optional[str] = None,
) -> str:
    """Create an OHLC candlestick chart for market-price reporting."""
    lengths = {len(labels), len(opens), len(highs), len(lows), len(closes)}
    if not labels or len(lengths) != 1:
        raise ValueError("OHLC inputs must be non-empty and have equal lengths")

    figure, axis = _figure(title, subtitle, (11.2, 6.2))
    candle_width = 0.58

    for index, (open_value, high, low, close) in enumerate(
        zip(opens, highs, lows, closes)
    ):
        if high < max(open_value, close) or low > min(open_value, close):
            raise ValueError(f"invalid OHLC range at index {index}")
        color = GREEN if close >= open_value else RED
        axis.vlines(index, low, high, color=color, linewidth=1.4)
        body_bottom = min(open_value, close)
        body_height = max(abs(close - open_value), 0.001)
        axis.add_patch(
            Rectangle(
                (index - candle_width / 2, body_bottom),
                candle_width,
                body_height,
                facecolor=color,
                edgecolor=color,
                linewidth=1,
            )
        )

    tick_step = max(1, len(labels) // 10)
    tick_positions = list(range(0, len(labels), tick_step))
    axis.set_xticks(tick_positions, [labels[index] for index in tick_positions])
    axis.set_xlim(-0.8, len(labels) - 0.2)
    axis.margins(y=0.12)
    _style_axis(axis, "currency", grid_axis="both")
    return _save(figure, output_path)
