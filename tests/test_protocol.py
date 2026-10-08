from __future__ import annotations

import pytest

from arena import families, protocol
from arena.core import Call, Option, Question
from arena.seeding import Rng


def question(n: int) -> Question:
    return Question("state", "pick one", tuple(Option(f"k{i}", f"option {i}") for i in range(n)))


class Recorder:
    def __init__(self, prefer: str | None = None) -> None:
        self.shown: list[tuple[str, ...]] = []
        self.prefer = prefer

    def __call__(self, q: Question, stage: str) -> Call:
        self.shown.append(q.keys)
        choice = self.prefer if self.prefer in q.keys else q.keys[0]
        return Call(stage, q.keys, choice, None, 1.0)


@pytest.mark.parametrize(
    ("n", "size", "sizes"), [(34, 8, [7, 7, 7, 7, 6]), (9, 8, [5, 4]), (16, 8, [8, 8]), (3, 8, [3])]
)
def test_split_groups_is_balanced(n: int, size: int, sizes: list[int]) -> None:
    groups = protocol.split_groups([str(i) for i in range(n)], size)
    assert [len(g) for g in groups] == sizes
    assert [k for g in groups for k in g] == [str(i) for i in range(n)]


@pytest.mark.parametrize("n", [2, 3, 8, 9, 17, 34, 70])
def test_decide_never_shows_more_than_the_group_size(n: int) -> None:
    ask = Recorder()
    decision = protocol.decide(question(n), ask, Rng(n), group_size=8)
    assert all(len(keys) <= 8 for keys in ask.shown)
    assert len(ask.shown) == protocol.requests_needed(n, 8)
    assert decision.choice in question(n).keys
    assert len(decision.calls) == len(ask.shown)


def test_a_preferred_option_survives_the_knockout() -> None:
    ask = Recorder(prefer="k21")
    assert protocol.decide(question(34), ask, Rng(1), group_size=8).choice == "k21"


def test_order_is_seeded_and_not_canonical() -> None:
    a, b = Recorder(), Recorder()
    protocol.decide(question(8), a, Rng(5), group_size=8)
    protocol.decide(question(8), b, Rng(5), group_size=8)
    assert a.shown == b.shown
    assert a.shown[0] != question(8).keys


def test_choice_family_payload() -> None:
    q = question(3)
    payload = families.payload("clef", q)
    assert payload["text"] == "state"
    move = payload["schema"]["move"]
    assert move == {
        "type": "choice",
        "instructions": "pick one",
        "criteria": {"k0": "option 0", "k1": "option 1", "k2": "option 2"},
    }
    assert list(move["criteria"]) == ["k0", "k1", "k2"]


def test_enum_family_payload_keeps_the_same_sentences() -> None:
    q = question(2).reordered(["k1", "k0"])
    move = families.payload("nimble", q)["schema"]["move"]
    assert move["type"] == "enum"
    assert move["choices"] == ["k1", "k0"]
    assert move["description"] == "pick one"
    assert move["choice_descriptions"] == {"k1": "option 1", "k0": "option 0"}


def test_unknown_family_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown typed-decision family"):
        families.payload("gpt", question(2))


def test_parse_reads_decision_and_scores() -> None:
    output = {"decision": {"move": "k1"}, "fields": {"move": {"scores": {"k0": 0.25, "k1": 0.75}}}}
    assert families.parse(output, ("k0", "k1")) == ("k1", {"k0": 0.25, "k1": 0.75})
    assert families.parse({"decision": {"move": "k0"}}, ("k0", "k1")) == ("k0", None)


@pytest.mark.parametrize(
    "output",
    [None, [], {"decision": {}}, {"decision": {"move": "k9"}}, {"decision": {"move": 3}}],
)
def test_parse_rejects_unusable_answers(output: object) -> None:
    with pytest.raises(families.ResponseError):
        families.parse(output, ("k0", "k1"))
