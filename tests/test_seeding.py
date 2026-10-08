from __future__ import annotations

from collections import Counter

from arena.seeding import Rng, derive_seed


def test_stream_is_pinned() -> None:
    # SplitMix64 reference values for seed 0: any change here changes every game of every suite.
    rng = Rng(0)
    assert [rng.next_u64() for _ in range(3)] == [
        0xE220A8397B1DCDAF,
        0x6E789E6AA1B965F4,
        0x06C45D188009454F,
    ]


def test_derive_seed_is_pinned() -> None:
    assert derive_seed("v0.1", "tetris", 7) == derive_seed("v0.1", "tetris", 7)
    assert derive_seed("v0.1", "tetris", 7) != derive_seed("v0.1", "tetris", 8)
    assert derive_seed("a", "bc") != derive_seed("ab", "c")  # parts are separated, not concatenated


def test_below_is_uniform_and_in_range() -> None:
    rng = Rng(42)
    counts = Counter(rng.below(6) for _ in range(60_000))
    assert set(counts) == set(range(6))
    assert all(abs(n - 10_000) < 500 for n in counts.values())


def test_shuffle_is_a_permutation_and_reproducible() -> None:
    items = list(range(20))
    a, b = Rng(3).shuffled(items), Rng(3).shuffled(items)
    assert a == b
    assert sorted(a) == items
    assert a != items


def test_random_float_range() -> None:
    rng = Rng(9)
    values = [rng.random() for _ in range(10_000)]
    assert min(values) >= 0.0
    assert max(values) < 1.0
