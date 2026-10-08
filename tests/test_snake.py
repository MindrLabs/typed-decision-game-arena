from __future__ import annotations

from collections import deque

from arena.games import snake as S
from arena.seeding import Rng


def test_start_and_outcomes() -> None:
    game = S.Snake(seed=1)
    assert list(game.body) == [(4, 4), (5, 4), (6, 4)]
    assert S.HEADINGS[game.heading] == "up"
    assert game.target("left")[1] == (4, 3)
    assert game.target("straight")[1] == (3, 4)
    assert game.target("right")[1] == (4, 5)


def test_walls_and_body_kill() -> None:
    game = S.Snake(seed=1)
    game.body = deque([(0, 0), (1, 0), (2, 0)])
    game.heading = 0
    game.food = (9, 9)
    assert game.outcome("straight") == "wall"
    assert game.outcome("left") == "wall"
    game.body = deque([(5, 5), (5, 6), (6, 6), (6, 5), (6, 4)])
    game.heading = 2  # down, so straight leads into (6, 5)
    assert game.outcome("straight") == "body"


def test_the_tail_moves_out_of_the_way() -> None:
    game = S.Snake(seed=1)
    game.body = deque([(5, 5), (5, 6), (6, 6), (6, 5)])  # tail right below the head
    game.heading = 3  # left
    game.food = (0, 0)
    assert game.outcome("left") == "empty"  # turning left (south) enters the cell the tail leaves


def test_eating_grows_and_moves_food() -> None:
    game = S.Snake(seed=1)
    game.food = (3, 4)
    game.step("straight")
    assert game.eaten == 1
    assert len(game.body) == 4
    assert game.food not in game.body


def test_food_sequence_depends_on_seed_and_count_only() -> None:
    a, b = S.Snake(seed=5), S.Snake(seed=5)
    assert a.food == b.food
    b.step("left")
    b.step("left")
    assert a.food == b.food  # moving without eating keeps the same food
    assert S.Snake(seed=6).food != a.food or S.Snake(seed=7).food != a.food


def test_caps_end_the_episode() -> None:
    task = S.SnakeTask(step_cap=1000, starve_cap=3)
    task.reset(1)
    task.state.food = (9, 9)
    for move in ("left", "right", "right"):
        assert not task.done
        task.apply(move)
    assert task.done
    assert task.metrics()["starved"] is True


def test_options_state_facts() -> None:
    task = S.SnakeTask()
    task.reset(3)
    options = {o.key: o.text for o in task.decision_point().question.options}
    assert set(options) == {"left", "straight", "right"}
    assert options["straight"].startswith("go straight: the head moves north to row 4, column 5")


def test_reference_beats_random() -> None:
    def play(seed: int, reference: bool) -> float:
        task = S.SnakeTask()
        task.reset(seed)
        rng = Rng(seed)
        while not task.done:
            point = task.decision_point()
            task.apply(S.reference_move(point.view.game) if reference else rng.choice(point.question.keys))
        return task.score()

    assert sum(play(s, True) for s in (1, 2, 3)) / 3 > 40
    assert sum(play(s, False) for s in (1, 2, 3)) / 3 < 2


def test_a_wall_move_names_no_cell_outside_the_grid() -> None:
    game = S.Snake(seed=1)
    game.body = deque([(0, 5), (1, 5), (2, 5)])
    game.heading = 0
    assert (
        S.option_text(game, "straight") == "go straight: the head would leave the grid to the north, so the game ends"
    )
