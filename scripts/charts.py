"""The README's figures in English, Korean and Chinese, from the files under results/.

    uv run --extra report python scripts/charts.py

Writes docs/images/<lang>/{board-index,realtime,game-k,options,duel-elo}.png. Captions live in the READMEs; the
images carry only axes, panel titles and legends, and every figure has a table in the README with its numbers.
A model's colour is its family's (Clef blue, Laya orange, Nimble aqua, Kev yellow); the rows name the models.
options.png reads every decision of the Snake and direct games, as Table 8 does (see scripts/stats.py).
"""

from __future__ import annotations

import argparse
from functools import cache
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import stats as S  # noqa: N812  (scripts/stats.py)
from matplotlib.colors import LinearSegmentedColormap, to_rgb

ROOT = Path(__file__).resolve().parents[1]
# Chart chrome, and four categorical colours checked for colour-blind separation and contrast on this surface.
PAPER, INK, MUTED, GRID, AXIS, NONE = "#ffffff", "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7", "#f0efec"
FAMILY_COLORS = {"clef": "#2a78d6", "laya": "#eb6834", "nimble": "#1baf7a", "kev": "#eda100"}
FAMILIES = ("clef", "laya", "nimble", "kev")
FAMILY_NAMES = {"clef": "Clef", "laya": "Laya", "nimble": "Nimble", "kev": "Kev"}
LIGHT_BLUE, BLUE = "#86b6ef", "#2a78d6"
RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281", "#0d366b"]

TEXT: dict[str, dict[str, Any]] = {
    "en": {
        "font": "Noto Sans CJK JP",
        "boards": {"macro": "Macro", "frame": "Frame", "realtime": "Real-time"},
        "index": "Index (random 0, reference 100)",
        "frame_point": "Frame board: the game waits",
        "realtime_point": "Real-time board: the game runs on",
        "late": "{} steps late",
        "late_one": "1 step late",
        "games": {
            "tetris": "Tetris",
            "snake": "Snake",
            "connect4": "Connect Four",
            "pong": "Pong",
            "breakout": "Breakout",
        },
        "k": "Way from random to the reference (k × 100)",
        "below": "Random or below",
        "panels": (
            "Same pick with the options reversed (%)",
            "Snake: chose a move that ends the game\nwhile a safe one was on offer (%)",
            "Connect Four: took a win on offer (%)",
            "Connect Four: let the opponent complete four\nwhen another move did not (%)",
        ),
        "random": "random",
        "elo": "Elo (geometric mean 1500)",
    },
    "ko": {
        "font": "Noto Sans CJK KR",
        "boards": {"macro": "Macro", "frame": "Frame", "realtime": "Real-time"},
        "index": "지수 (무작위 0, 기준 플레이어 100)",
        "frame_point": "Frame 보드: 게임이 기다린다",
        "realtime_point": "Real-time 보드: 게임이 계속 흐른다",
        "late": "{} 스텝 늦음",
        "late_one": "1 스텝 늦음",
        "games": {
            "tetris": "Tetris",
            "snake": "Snake",
            "connect4": "Connect Four",
            "pong": "Pong",
            "breakout": "Breakout",
        },
        "k": "무작위에서 기준 플레이어까지 간 정도 (k × 100)",
        "below": "무작위 이하",
        "panels": (
            "선택지 순서를 뒤집어도 같은 선택 (%)",
            "Snake: 안전한 수가 있는데\n게임이 끝나는 수를 고름 (%)",
            "Connect Four: 제시된 승리를 잡음 (%)",
            "Connect Four: 다른 수로는 막을 수 있었는데\n상대에게 4목을 내줌 (%)",
        ),
        "random": "무작위",
        "elo": "Elo (기하평균 1500)",
    },
    "zh-cn": {
        "font": "Noto Sans CJK SC",
        "boards": {"macro": "Macro", "frame": "Frame", "realtime": "Real-time"},
        "index": "指数（随机 0，参考玩家 100）",
        "frame_point": "Frame 榜单：游戏等待模型",
        "realtime_point": "Real-time 榜单：游戏不停",
        "late": "慢 {} 步",
        "late_one": "慢 1 步",
        "games": {
            "tetris": "Tetris",
            "snake": "Snake",
            "connect4": "Connect Four",
            "pong": "Pong",
            "breakout": "Breakout",
        },
        "k": "从随机到参考玩家走了多远（k × 100）",
        "below": "不高于随机",
        "panels": (
            "选项顺序反转后仍选同一项 (%)",
            "Snake：有安全的走法时\n仍选了会结束游戏的走法 (%)",
            "Connect Four：抓住了送到眼前的胜利 (%)",
            "Connect Four：本可避免时\n仍让对手下一步连成四子 (%)",
        ),
        "random": "随机",
        "elo": "Elo（几何平均 1500）",
    },
}


def setup(font: str) -> None:
    plt.rcParams.update(
        {
            "font.family": [font, "DejaVu Sans"],
            "font.size": 12,
            "axes.edgecolor": AXIS,
            "axes.labelcolor": MUTED,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "figure.facecolor": PAPER,
            "axes.facecolor": PAPER,
            "savefig.facecolor": PAPER,
        }
    )


@cache
def family(pid: str) -> str:
    return S.contestants()[pid].family


def tidy(ax: Any, grid: bool = True) -> None:
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0, labelcolor=INK)
    ax.tick_params(axis="x", length=0)
    if grid:
        ax.grid(axis="x", color=GRID, lw=1)
        ax.set_axisbelow(True)


def family_legend(fig: Any, families: list[str], y: float = 0.995) -> None:
    handles = [
        plt.Line2D([], [], marker="o", ls="", ms=9, color=FAMILY_COLORS[f], markeredgecolor=PAPER) for f in families
    ]
    fig.legend(
        handles,
        [FAMILY_NAMES[f] for f in families],
        loc="upper center",
        bbox_to_anchor=(0.5, y),
        ncol=len(families),
        frameon=False,
        fontsize=11,
        handletextpad=0.3,
        columnspacing=1.4,
        labelcolor=INK,
    )


def dot_rows(ax: Any, rows: list[tuple[str, float, list[float], str]]) -> None:
    """rows: (label, value, [low, high], colour), drawn top to bottom."""
    for i, (_, value, (lo, hi), color) in enumerate(reversed(rows)):
        ax.plot([lo, hi], [i, i], color=color, lw=2, solid_capstyle="round", zorder=2)
        ax.plot(value, i, "o", ms=9, color=color, markeredgecolor=PAPER, markeredgewidth=2, zorder=3)
    ax.set_yticks(range(len(rows)), [r[0] for r in reversed(rows)])
    ax.set_ylim(-0.6, len(rows) - 0.4)


def board_index(results: S.Results, t: dict[str, Any], out: Path) -> None:
    boards = S.scores(results)["boards"]
    order = S.ranked(boards["macro"])
    fig, axes = plt.subplots(1, 3, figsize=(10, 5.2), dpi=160, sharey=True)
    fig.subplots_adjust(left=0.2, right=0.98, top=0.84, bottom=0.12, wspace=0.08)
    for ax, board in zip(axes, S.BOARDS, strict=True):
        players = boards[board]["players"]
        dot_rows(
            ax,
            [(S.title(p), players[p]["index"], players[p]["index_ci"], FAMILY_COLORS[family(p)]) for p in order],
        )
        ax.set_xlim(-1, 32)
        ax.set_xticks([0, 10, 20, 30])
        ax.set_title(t["boards"][board], color=INK, fontsize=13, loc="left")
        tidy(ax)
    fig.supxlabel(t["index"], color=MUTED, fontsize=12, x=0.59, y=0.015)
    family_legend(fig, list(FAMILIES))
    fig.savefig(out / "board-index.png")
    plt.close(fig)


def realtime(results: S.Results, t: dict[str, Any], out: Path) -> None:
    boards = S.scores(results)["boards"]
    order = S.ranked(boards["frame"])
    delays = S.delays(results)
    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=160)
    fig.subplots_adjust(left=0.2, right=0.8, top=0.86, bottom=0.12)
    for i, p in enumerate(reversed(order)):
        frame, live = boards["frame"]["players"][p]["index"], boards["realtime"]["players"][p]["index"]
        ax.plot([frame, live], [i, i], color=AXIS, lw=1.5, zorder=1)
        ax.plot(frame, i, "o", ms=10, color=LIGHT_BLUE, markeredgecolor=PAPER, markeredgewidth=2, zorder=2)
        ax.plot(live, i, "o", ms=10, color=BLUE, markeredgecolor=PAPER, markeredgewidth=2, zorder=3)
        ax.text(
            1.02,
            i,
            t["late_one"] if delays[p] == [1] else t["late"].format(S.span(delays[p])),
            transform=ax.get_yaxis_transform(),
            va="center",
            color=MUTED,
            fontsize=11,
        )
    ax.set_yticks(range(len(order)), [S.title(p) for p in reversed(order)])
    ax.set_ylim(-0.6, len(order) - 0.4)
    ax.set_xlim(-1, 30)
    ax.set_xlabel(t["index"])
    tidy(ax)
    handles = [plt.Line2D([], [], marker="o", ls="", ms=10, color=c, markeredgecolor=PAPER) for c in (LIGHT_BLUE, BLUE)]
    fig.legend(
        handles,
        [t["frame_point"], t["realtime_point"]],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.995),
        ncol=2,
        frameon=False,
        fontsize=11,
        labelcolor=INK,
        columnspacing=1.6,
    )
    fig.savefig(out / "realtime.png")
    plt.close(fig)


def game_k(results: S.Results, t: dict[str, Any], out: Path) -> None:
    boards = S.scores(results)["boards"]
    order = S.ranked(boards["macro"])
    columns = [(b, g) for b in S.BOARDS for g in boards[b]["games"]]
    cmap = LinearSegmentedColormap.from_list("blue", RAMP)
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=160)
    fig.subplots_adjust(left=0.2, right=0.99, top=0.8, bottom=0.17)
    gap = 0.35  # extra space between the boards' column groups
    xs, x = [], 0.0
    for j, (board, _) in enumerate(columns):
        if j and columns[j - 1][0] != board:
            x += gap
        xs.append(x)
        x += 1
    for i, p in enumerate(order):
        y = len(order) - 1 - i
        for x0, (board, game) in zip(xs, columns, strict=True):
            k = boards[board]["players"][p]["games"][game]["k"]
            color = NONE if k <= 0 else cmap(k)
            ax.add_patch(plt.Rectangle((x0 + 0.03, y - 0.47), 0.94, 0.94, color=color, lw=0))
            if k >= 0.05:
                r, g_, b = to_rgb(color)
                light = 0.2126 * r + 0.7152 * g_ + 0.0722 * b > 0.5
                ax.text(
                    x0 + 0.5,
                    y,
                    S.num(100 * k, 0),
                    ha="center",
                    va="center",
                    fontsize=11,
                    color=INK if light else PAPER,
                )
    ax.set_xlim(-0.1, xs[-1] + 1.1)
    ax.set_ylim(-0.6, len(order) - 0.4)
    ax.set_yticks(range(len(order)), [S.title(p) for p in reversed(order)])
    ax.set_xticks(
        [x0 + 0.5 for x0 in xs],
        [t["games"][g] for _, g in columns],
        rotation=35,
        ha="right",
        rotation_mode="anchor",
        fontsize=11,
        color=INK,
    )
    for board in S.BOARDS:
        group = [x0 for x0, (b, _) in zip(xs, columns, strict=True) if b == board]
        ax.text(
            (group[0] + group[-1] + 1) / 2,
            len(order) - 0.25,
            t["boards"][board],
            ha="center",
            va="bottom",
            color=INK,
            fontsize=13,
        )
    ax.spines[:].set_visible(False)
    ax.tick_params(length=0)
    ax.tick_params(axis="y", labelcolor=INK)
    swatches = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (NONE, cmap(0.25), cmap(0.5), cmap(1.0))]
    fig.legend(
        swatches,
        [t["below"], "25", "50", "100"],
        title=t["k"],
        title_fontsize=11,
        loc="upper center",
        bbox_to_anchor=(0.59, 0.995),
        ncol=4,
        frameon=False,
        fontsize=11,
        labelcolor=INK,
        handlelength=1.2,
        columnspacing=1.4,
    )
    fig.savefig(out / "game-k.png")
    plt.close(fig)


def options(results: S.Results, t: dict[str, Any], out: Path) -> bool:
    order = S.ranked(S.scores(results)["boards"]["macro"])
    c4 = S.connect4_choices(results)
    fatal = {p: n for p in [*order, "random"] if (n := S.snake_choices(results, p)) is not None}
    if c4 is None or any(p not in fatal for p in order):
        return False
    agreement = {p: 100 * S.load(results.suite() / "bias" / f"{p}.json")["overall"]["agreement"] for p in order}
    random = 100 * fatal["random"][0] / fatal["random"][1] if "random" in fatal else None
    panels = [
        (agreement, None),
        ({p: 100 * fatal[p][0] / fatal[p][1] for p in order}, random),
        ({p: 100 * c4[p][0] / c4[p][1] for p in order}, None),
        ({p: 100 * c4[p][2] / c4[p][3] for p in order}, None),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10, 9), dpi=160, sharey=True)
    fig.subplots_adjust(left=0.2, right=0.97, top=0.9, bottom=0.04, wspace=0.12, hspace=0.28)
    for ax, (values, reference), title in zip(axes.flat, panels, t["panels"], strict=True):
        for i, p in enumerate(reversed(order)):
            v = values[p]
            ax.barh(i, v, height=0.62, color=FAMILY_COLORS[family(p)])
            ax.text(
                v + 1.5,
                i,
                S.share(v),
                va="center",
                fontsize=11,
                color=INK,
                zorder=3,
                bbox={"facecolor": PAPER, "edgecolor": "none", "pad": 0.5},
            )
        if reference is not None:
            ax.axvline(reference, color=MUTED, lw=1, zorder=1)
            ax.text(
                reference + 1,
                len(order) - 0.5,
                f"{t['random']} {S.num(reference, 0)}",
                color=MUTED,
                fontsize=10,
                va="bottom",
            )
        ax.set_yticks(range(len(order)), [S.title(p) for p in reversed(order)])
        ax.set_ylim(-0.6, len(order) - 0.1)
        ax.set_xlim(0, 112)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_title(title, color=INK, fontsize=12, loc="left")
        tidy(ax)
    family_legend(fig, list(FAMILIES))
    fig.savefig(out / "options.png")
    plt.close(fig)
    return True


def duel_elo(results: S.Results, t: dict[str, Any], out: Path) -> None:
    ratings = S.duel_scores(results)["ratings"]
    order = sorted(ratings, key=lambda p: -ratings[p]["elo"])
    fig, ax = plt.subplots(figsize=(10, 4.8), dpi=160)
    fig.subplots_adjust(left=0.2, right=0.97, top=0.88, bottom=0.13)
    ax.axvline(1500, color=AXIS, lw=1, zorder=1)
    dot_rows(
        ax,
        [(S.title(p), ratings[p]["elo"], ratings[p]["interval"], FAMILY_COLORS[family(p)]) for p in order],
    )
    ax.set_xlim(1150, 1990)
    ax.set_xlabel(t["elo"])
    tidy(ax)
    family_legend(fig, list(FAMILIES))
    fig.savefig(out / "duel-elo.png")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", type=Path, default=ROOT / "results", help="the results directory")
    args = parser.parse_args()
    results = S.Results(args.results)
    for lang, t in TEXT.items():
        setup(t["font"])
        out = ROOT / "docs" / "images" / lang
        out.mkdir(parents=True, exist_ok=True)
        board_index(results, t, out)
        realtime(results, t, out)
        game_k(results, t, out)
        if not options(results, t, out):
            print("options.png skipped: neither decision logs nor replays for every game")
        duel_elo(results, t, out)
        print(out)


if __name__ == "__main__":
    main()
