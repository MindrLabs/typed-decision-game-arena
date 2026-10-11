"""`arena`: run, verify, score and publish the typed-decision game arena.

arena list                                    boards, games and players
arena show   --board macro --game tetris      print exactly what a model is asked
arena smoke  --player kev-0.8b                one request per game against the model server
arena run    --board macro --game tetris --player kev-0.8b --seeds dev
arena board  --board macro --player kev-0.8b --seeds test       every game of a board
arena verify                                  replay every logged episode
arena score  --seed-set test                  normalised scores, intervals, pairwise tests
arena export --seed-set test                  site data into webui/data
arena latency --player kev-0.8b               latency on fixed probe questions
arena bias    --player kev-0.8b               option-order (position) bias
arena campaign --seed-set test                every run in order, unattended and resumable
arena status   --seed-set test                what is complete, per player and board
arena dataset  --seed-set test                decision logs and results to a Hugging Face dataset
arena laya-cuts                               how much of each question Laya reads
arena suite show|freeze|check                 the frozen protocol
arena duel run|verify|score|status --seed-set test     models against each other (Connect Four, duel suite)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from arena import __version__
from arena.client import DEFAULT_SERVER, ModelClient
from arena.logs import RESULTS, write_json
from arena.registry import BASELINES, contestants
from arena.suite import SEED_SETS, Suite, freeze, load_suite, lock_differences, parse_seeds


def _seeds(suite: Suite, board: str, game: str, value: str, seed_set: str | None) -> tuple[list[int], str]:
    if value in SEED_SETS:
        return suite.game(board, game).seeds[value], value
    if seed_set is None:
        raise SystemExit("an explicit seed list needs --seed-set dev|test")
    allowed = set(suite.game(board, game).seeds[seed_set])
    seeds = parse_seeds(value)
    outside = sorted(set(seeds) - allowed)
    if outside:
        raise SystemExit(f"seeds {outside} are not {seed_set} seeds of {board}/{game}")
    return seeds, seed_set


def cmd_list(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    for board in sorted(suite.boards.values(), key=lambda b: b.order):
        print(f"{board.id}: {board.title}. {board.summary}")
        for game, spec in board.games.items():
            seeds = ", ".join(f"{name} {len(values)}" for name, values in spec.seeds.items())
            print(f"  {game:<9} {spec.params or ''} seeds: {seeds}")
    print("players:")
    for name in BASELINES:
        print(f"  {name:<18} baseline")
    for c in contestants().values():
        print(f"  {c.id:<18} {c.family:<7} {c.repository}@{(c.revision or 'unpinned')[:12]}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    from arena.episode import decision_rng, realtime_note
    from arena.players import ReferencePlayer
    from arena.tasks import make_task

    suite = load_suite(args.suite)
    spec = suite.game(args.board, args.game)
    task = make_task(suite, args.board, args.game)
    reference = ReferencePlayer(args.game, spec.track, dict(spec.reference))
    task.reset(args.seed)
    reference.start(args.seed)
    try:
        for index in range(args.skip + args.decisions):
            if task.done:
                break
            point = task.decision_point()
            rng = decision_rng(suite.id, args.board, args.game, args.seed, index)
            if index >= args.skip:
                q = point.question
                state = q.state
                if suite.board(args.board).step_ms is not None:
                    state += "\n" + realtime_note(1, task.default_key)
                print(f"--- decision {index} (step {task.steps}) ---")
                print(state)
                print(f"\nInstructions: {q.instructions}")
                for option in q.options:
                    print(f"  [{option.key}] {option.text}")
                print()
            task.apply(reference.decide(point, rng).choice)
    finally:
        task.close()
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    from arena.core import PlayerError
    from arena.players import TextPlayer
    from arena.probe import smoke

    suite = load_suite(args.suite)
    contestant = contestants()[args.player]
    player = TextPlayer(contestant, ModelClient(args.server, retries=0), suite.group_size)
    failures = 0
    try:
        for board, game, answer in smoke(suite, player):
            if isinstance(answer, PlayerError):
                failures += 1
                print(f"FAIL  {board}/{game}: {answer}")
                continue
            top = max((answer.probabilities or {}).items(), key=lambda kv: kv[1], default=(None, None))
            print(f"ok    {board}/{game}: {answer.choice} ({answer.latency_ms:.0f} ms, top p {top[1]})")
    finally:
        player.close()
    return 1 if failures else 0


def _run_one(args: argparse.Namespace, suite: Suite, board: str, game: str) -> int:
    from arena.runner import run

    seeds, seed_set = _seeds(suite, board, game, args.seeds, args.seed_set)
    summary = run(
        suite,
        board,
        game,
        args.player,
        seeds,
        seed_set=seed_set,
        server=args.server,
        workers=args.workers,
        results=Path(args.results),
    )
    print(
        f"{board}/{game} {args.player}: {len(summary.finished)} finished, {summary.skipped} already done, "
        f"{len(summary.failed)} failed",
        file=sys.stderr,
    )
    return 1 if summary.failed else 0


def cmd_run(args: argparse.Namespace) -> int:
    return _run_one(args, load_suite(args.suite), args.board, args.game)


def cmd_board(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    status = 0
    for game in suite.board(args.board).games:
        status |= _run_one(args, suite, args.board, game)
    return status


def cmd_verify(args: argparse.Namespace) -> int:
    from arena.replay import verify

    suite = load_suite(args.suite)
    checked = failed = 0
    for item in verify(
        suite, args.seed_set, boards=args.board, games=args.game, players=args.player, results=Path(args.results)
    ):
        checked += 1
        if item.problem:
            failed += 1
            print(f"MISMATCH {item.board}/{item.game} {item.player} seed {item.seed}: {item.problem}")
        elif args.verbose:
            print(f"ok {item.board}/{item.game} {item.player} seed {item.seed} ({item.decisions} decisions)")
    print(f"{checked} episodes replayed, {failed} mismatches", file=sys.stderr)
    return 1 if failed else 0


def cmd_score(args: argparse.Namespace) -> int:
    from arena.score import score

    suite = load_suite(args.suite)
    report = score(suite, args.seed_set, Path(args.results))
    out = Path(args.out) if args.out else Path(args.results) / suite.id / f"scores-{args.seed_set}.json"
    write_json(out, report)
    for board, data in report["boards"].items():
        print(f"{board}:")
        if data["missing_anchors"]:
            print(f"  anchors missing for {', '.join(data['missing_anchors'])}")
        for player in data["ranking"]:
            info = data["players"][player]
            low, high = info.get("index_ci") or (float("nan"), float("nan"))
            print(f"  {info['rank']:>2}. {player:<18} {info['index']:6.1f}  [{low:.1f}, {high:.1f}]")
        unranked = [p for p in data["players"] if p not in data["ranking"]]
        if unranked:
            print(f"  incomplete: {', '.join(unranked)}")
    print(f"wrote {out}", file=sys.stderr)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from arena.export import WEBUI_DATA, export

    suite = load_suite(args.suite)
    out = Path(args.out) if args.out else WEBUI_DATA
    path = export(suite, args.seed_set, out=out, results=Path(args.results), replays_per_player=args.replays)
    print(f"wrote {path}", file=sys.stderr)
    return 0


def cmd_latency(args: argparse.Namespace) -> int:
    from arena.latency import measure

    suite = load_suite(args.suite)
    path = measure(suite, args.player, server=args.server, sample=args.sample, results=Path(args.results))
    print(f"wrote {path}", file=sys.stderr)
    return 0


def cmd_bias(args: argparse.Namespace) -> int:
    from arena.bias import measure

    suite = load_suite(args.suite)
    path = measure(suite, args.player, server=args.server, sample=args.sample, results=Path(args.results))
    print(f"wrote {path}", file=sys.stderr)
    return 0


def cmd_campaign(args: argparse.Namespace) -> int:
    from arena.campaign import Campaign, ServerUnavailableError

    models = [m for m in args.models.split(",") if m] if args.models else list(contestants())
    campaign = Campaign(
        load_suite(args.suite),
        args.seed_set,
        server=args.server,
        results=Path(args.results),
        anchor_workers=args.anchor_workers,
        attempts=args.attempts,
        server_wait=args.server_wait,
        gpu_wait=args.gpu_wait,
        latency_sample=args.latency_sample,
        bias_sample=args.bias_sample,
    )
    try:
        report = campaign.run(models, anchors=not args.no_anchors)
    except ServerUnavailableError as error:
        print(f"campaign stopped: {error}; run the same command again once the server is up", file=sys.stderr)
        return 2
    return 1 if report.failed else 0


def cmd_dataset(args: argparse.Namespace) -> int:
    from arena.dataset import publish

    suite = load_suite(args.suite)
    publish(suite, args.seed_set, args.repo, results=Path(args.results), private=not args.public)
    print(f"uploaded {suite.id} {args.seed_set} to https://huggingface.co/datasets/{args.repo}", file=sys.stderr)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from arena.campaign import format_status, status

    print(format_status(status(load_suite(args.suite), args.seed_set, Path(args.results))))
    return 0


def cmd_duel(args: argparse.Namespace) -> int:
    from arena import duel

    suite = load_suite(args.duel_suite)
    results_dir = Path(args.results)
    if args.action == "run":
        models = [m for m in args.models.split(",") if m] if args.models else list(contestants())
        pairs = [p for p in args.pairs.split(",") if p] if args.pairs else duel.schedule(models)
        late = {m for m in (args.last or "").split(",") if m}
        pairs = sorted(pairs, key=lambda pair: bool(late & set(duel.split_pair(pair))))
        seeds = parse_seeds(args.seeds) if args.seeds else None
        summary = duel.run_duels(
            suite,
            args.seed_set,
            pairs,
            seeds=seeds,
            server=args.server,
            results=results_dir,
            room=lambda pair: _warm_pair(suite, pair, args.server),
        )
        print(
            f"{len(summary.finished)} games played, {summary.skipped} already done, {len(summary.failed)} failed",
            file=sys.stderr,
        )
        return 1 if summary.failed else 0
    if args.action == "verify":
        checked = failed = 0
        for item in duel.verify(suite, args.seed_set, results=results_dir):
            checked += 1
            if item.problem:
                failed += 1
                print(f"MISMATCH {item.pair} seed {item.seed} game {item.game_no}: {item.problem}")
        print(f"{checked} games replayed, {failed} mismatches", file=sys.stderr)
        return 1 if failed else 0
    if args.action == "score":
        report = duel.score(suite, args.seed_set, results=results_dir)
        out = results_dir / suite.id / f"scores-{args.seed_set}.json"
        write_json(out, report)
        ranked = sorted(report["ratings"].items(), key=lambda kv: -kv[1]["elo"])
        for rank, (player, info) in enumerate(ranked, 1):
            low, high = info["interval"] or (float("nan"), float("nan"))
            points = f"{info['points']:g}/{info['games']}"
            print(f"{rank:>2}. {player:<18} {info['elo']:7.1f}  [{low:.1f}, {high:.1f}]  {points}")
        print(f"{report['games']} games; wrote {out}", file=sys.stderr)
        return 0
    models = list(contestants())
    total = len(suite.game(duel.BOARD, duel.GAME).seeds[args.seed_set]) * 2
    for pair in duel.schedule(models):
        done = len(duel.read_games(duel.pair_dir(suite.id, args.seed_set, pair, results=results_dir)))
        print(f"{pair:<36} {done:>3}/{total}")
    return 0


def _warm_pair(suite: Suite, pair: str, server: str, *, timeout: float = 3600.0) -> None:
    """Before a pair plays: wait until no other model holds the GPU (two models share it during a game, and a third
    could exhaust the GB10's unified memory), then load the pair's models one at a time with one untimed request
    each, so that two never load at once and no game request waits on a load. model-compose unloads a model after
    two idle minutes and a load can take a quarter of an hour, so a background thread keeps every model of the pair
    that is already loaded warm with a request every half minute until the games start."""
    import threading
    import time

    from arena import duel
    from arena.core import PlayerError
    from arena.gpu import gpu_processes
    from arena.players import TextPlayer

    members = duel.split_pair(pair)
    task = duel.Connect4Duel()
    task.reset(1)
    question = task.decision_point().question
    known = contestants()

    def untimed(player_id: str) -> TextPlayer:
        return TextPlayer(known[player_id], ModelClient(server, timeout=5400, retries=0), suite.group_size)

    players = {pid: untimed(pid) for pid in members}
    keepers = {pid: untimed(pid) for pid in members}
    warm: set[str] = set()
    stop = threading.Event()

    def keep_warm() -> None:
        while not stop.wait(30):
            for pid in sorted(warm):
                try:
                    keepers[pid].ask(question, "keep-alive")
                except PlayerError as error:
                    print(f"keep-alive {pid}: {error}", file=sys.stderr, flush=True)

    thread = threading.Thread(target=keep_warm, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + timeout
        while True:
            loaded = {p.runtime for p in gpu_processes() if p.runtime and p.busy}
            warm.update(pid for pid in members if pid in loaded)
            others = sorted(name for name in loaded if name and name not in members)
            if not others:
                break
            if time.monotonic() > deadline:
                raise TimeoutError(f"models {others} stayed loaded for {timeout:.0f}s; stop them before {pair}")
            print(f"waiting for {', '.join(others)} to unload before {pair}", file=sys.stderr, flush=True)
            time.sleep(30)
        for pid in members:
            started = time.perf_counter()
            players[pid].ask(question, "warm-up")
            warm.add(pid)
            print(f"{pid} ready ({time.perf_counter() - started:.0f}s)", file=sys.stderr, flush=True)
    finally:
        stop.set()
        thread.join(timeout=120)
        for player in [*players.values(), *keepers.values()]:
            player.close()


def cmd_laya_cuts(args: argparse.Namespace) -> int:
    from arena.laya_cuts import measure

    suite = load_suite(args.suite)
    report = measure(suite, sample=args.sample)
    out = RESULTS / suite.id / "laya-cuts.json"
    write_json(out, report)
    print(f"wrote {out}", file=sys.stderr)
    return 0


def cmd_env(args: argparse.Namespace) -> int:
    from arena.environment import describe

    suite = load_suite(args.suite)
    out = Path(args.results) / suite.id / "environment.json"
    write_json(out, describe())
    print(f"wrote {out}", file=sys.stderr)
    return 0


def cmd_suite(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    if args.action == "show":
        from arena.suite import manifest

        print(json.dumps(manifest(suite), indent=2, sort_keys=True))
        return 0
    if args.action == "freeze":
        print(f"wrote {freeze(suite)}")
        return 0
    problems = lock_differences(suite)
    for line in problems:
        print(line)
    print("lock matches" if not problems else f"{len(problems)} differences", file=sys.stderr)
    return 1 if problems else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arena", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--version", action="version", version=f"arena {__version__}")
    parser.add_argument("--suite", default="v0.1", help="suite id (suites/<id>.toml)")
    sub = parser.add_subparsers(dest="command", required=True)

    def server(p: argparse.ArgumentParser) -> None:
        p.add_argument("--server", default=DEFAULT_SERVER, help=f"model-compose API base (default {DEFAULT_SERVER})")

    def results(p: argparse.ArgumentParser) -> None:
        p.add_argument("--results", default=str(RESULTS), help="results directory")

    sub.add_parser("list", help="boards, games and players").set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="print the questions a model sees")
    p.add_argument("--board", required=True)
    p.add_argument("--game", required=True)
    p.add_argument("--seed", type=int, default=1001)
    p.add_argument("--skip", type=int, default=0, help="decisions to play (as the reference) before printing")
    p.add_argument("--decisions", type=int, default=1)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("smoke", help="one request per game against the model server")
    p.add_argument("--player", required=True)
    server(p)
    p.set_defaults(func=cmd_smoke)

    for name, func, helptext in (("run", cmd_run, "run one game"), ("board", cmd_board, "run every game of a board")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--board", required=True)
        if name == "run":
            p.add_argument("--game", required=True)
        p.add_argument("--player", required=True)
        p.add_argument("--seeds", required=True, help="dev, test, or a list like 1-5,8 (with --seed-set)")
        p.add_argument("--seed-set", choices=SEED_SETS)
        p.add_argument("--workers", type=int, default=1, help="parallel episodes (baselines: CPU cores)")
        server(p)
        results(p)
        p.set_defaults(func=func)

    p = sub.add_parser("verify", help="replay logged episodes and compare")
    p.add_argument("--seed-set", choices=SEED_SETS, default="test")
    p.add_argument("--board", action="append")
    p.add_argument("--game", action="append")
    p.add_argument("--player", action="append")
    p.add_argument("--verbose", action="store_true")
    results(p)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("score", help="normalised scores and intervals")
    p.add_argument("--seed-set", choices=SEED_SETS, default="test")
    p.add_argument("--out")
    results(p)
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("export", help="write site data into webui/data")
    p.add_argument("--seed-set", choices=SEED_SETS, default="test")
    p.add_argument("--out")
    p.add_argument("--replays", type=int, default=2, help="replays per (board, game, player)")
    results(p)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("latency", help="latency on fixed probe questions (run the model alone on the GPU)")
    p.add_argument("--player", required=True)
    p.add_argument("--sample", type=int, default=200)
    server(p)
    results(p)
    p.set_defaults(func=cmd_latency)

    p = sub.add_parser("bias", help="option-order bias on fixed probe questions")
    p.add_argument("--player", required=True)
    p.add_argument("--sample", type=int, default=40)
    server(p)
    results(p)
    p.set_defaults(func=cmd_bias)

    p = sub.add_parser("campaign", help="every run of a seed set in order: anchors, then each model (resumable)")
    p.add_argument("--seed-set", choices=SEED_SETS, required=True)
    p.add_argument("--models", help="comma-separated, in running order (default: every model in model-compose.yml)")
    p.add_argument("--no-anchors", action="store_true", help="leave out the random and reference runs")
    p.add_argument("--anchor-workers", type=int, default=8, help="parallel episodes of the anchors (CPU only)")
    p.add_argument("--attempts", type=int, default=3, help="runs of one game until its failed episodes pass")
    p.add_argument("--server-wait", type=float, default=3600, help="seconds to wait for an absent model server")
    p.add_argument("--gpu-wait", type=float, default=1800, help="seconds a latency measurement waits for the GPU")
    p.add_argument("--latency-sample", type=int, default=200)
    p.add_argument("--bias-sample", type=int, default=40)
    server(p)
    results(p)
    p.set_defaults(func=cmd_campaign)

    p = sub.add_parser("dataset", help="publish decision logs and results as a Hugging Face dataset")
    p.add_argument("--seed-set", choices=SEED_SETS, default="test")
    p.add_argument("--repo", default="MindrLabs/typed-decision-game-arena", help="dataset repository id")
    p.add_argument("--public", action="store_true", help="create it public (an existing one keeps its visibility)")
    results(p)
    p.set_defaults(func=cmd_dataset)

    p = sub.add_parser("status", help="what is complete, per player and board")
    p.add_argument("--seed-set", choices=SEED_SETS, default="test")
    results(p)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("laya-cuts", help="token budgets of the Laya players against the probe questions")
    p.add_argument("--sample", type=int, default=100)
    p.set_defaults(func=cmd_laya_cuts)

    p = sub.add_parser("env", help="record software and hardware next to the results")
    results(p)
    p.set_defaults(func=cmd_env)

    p = sub.add_parser("duel", help="models against each other (Connect Four, suite of kind duel)")
    p.add_argument("action", choices=("run", "verify", "score", "status"))
    p.add_argument("--duel-suite", default="duel-v0.1", help="the duel suite (suites/<id>.toml)")
    p.add_argument("--seed-set", choices=SEED_SETS, required=True)
    p.add_argument("--models", help="comma-separated models for run (default: every model in model-compose.yml)")
    p.add_argument("--pairs", help="comma-separated pairs a~b for run, in running order")
    p.add_argument("--seeds", help="seed list for run, e.g. 1-5 (default: the suite's seeds of the seed set)")
    p.add_argument("--last", help="comma-separated models whose pairs run last (the largest, to load with most room)")
    server(p)
    results(p)
    p.set_defaults(func=cmd_duel)

    p = sub.add_parser("suite", help="show, freeze or check the suite lock")
    p.add_argument("action", choices=("show", "freeze", "check"))
    p.set_defaults(func=cmd_suite)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    status: int = args.func(args)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
