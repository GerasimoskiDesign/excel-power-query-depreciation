"""README charts (static PNGs in docs/img) built from the reference schedule."""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

log = logging.getLogger(__name__)

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]


def _style(ax: plt.Axes, title: str, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=TEXT, fontsize=12, fontweight="bold")
    ax.set_ylabel(ylabel, color=TEXT_2)
    ax.tick_params(colors=TEXT_2, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def depreciation_by_category(schedule: pd.DataFrame, path: Path) -> Path:
    """Stacked monthly depreciation by asset category (EUR thousands)."""
    pivot = (
        schedule.pivot_table(
            index="month_start", columns="category", values="depreciation", aggfunc="sum"
        ).fillna(0.0)
        / 1_000
    )
    labels = [m.strftime("%Y-%m") for m in pivot.index]
    x = list(range(len(labels)))
    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=120)
    fig.patch.set_facecolor(SURFACE)
    bottom = [0.0] * len(labels)
    for colour, cat in zip(SERIES, pivot.columns, strict=False):
        ax.bar(
            x,
            pivot[cat],
            bottom=bottom,
            color=colour,
            label=cat,
            width=0.75,
            edgecolor=SURFACE,
            linewidth=1,
        )
        bottom = [b + v for b, v in zip(bottom, pivot[cat], strict=True)]
    _style(ax, "Monthly depreciation by category (synthetic data)", "EUR thousand")
    ax.set_xticks(range(0, len(labels), 3), labels[::3])
    ax.legend(frameon=False, fontsize=8, ncol=4, loc="upper left", bbox_to_anchor=(0, -0.08))
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def balance_rollforward(schedule: pd.DataFrame, path: Path) -> Path:
    """Gross cost, accumulated depreciation and NBV at each month end (EUR million)."""
    totals = (
        schedule.groupby("month_start")[["closing_cost", "closing_acc_dep", "closing_nbv"]].sum()
        / 1_000_000
    )
    labels = [m.strftime("%Y-%m") for m in totals.index]
    x = list(range(len(labels)))
    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=120)
    fig.patch.set_facecolor(SURFACE)
    names = {
        "closing_cost": "Gross cost",
        "closing_acc_dep": "Accumulated depreciation",
        "closing_nbv": "Net book value",
    }
    for colour, (col, name) in zip(SERIES, names.items(), strict=False):
        ax.plot(x, totals[col], color=colour, linewidth=2, label=name)
        ax.annotate(
            f"{name} {totals[col].iloc[-1]:,.1f}",
            (len(labels) - 1, totals[col].iloc[-1]),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=TEXT,
        )
    _style(ax, "Month-end balances (synthetic data)", "EUR million")
    ax.set_xticks(range(0, len(labels), 3), labels[::3])
    ax.set_ylim(bottom=0)
    ax.set_xlim(-0.5, len(labels) + 5)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper left", bbox_to_anchor=(0, -0.08))
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def write_charts(schedule: pd.DataFrame, img_dir: Path) -> list[Path]:
    img_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        depreciation_by_category(schedule, img_dir / "depreciation_by_category.png"),
        balance_rollforward(schedule, img_dir / "balance_rollforward.png"),
    ]
    log.info("Wrote %d charts to %s", len(paths), img_dir)
    return paths
