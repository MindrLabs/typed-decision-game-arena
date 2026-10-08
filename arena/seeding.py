"""Seeds and random streams that reproduce across Python and NumPy versions.

Every random draw in the arena (Tetris bags, Snake food, opponents, option orders, tie-breaks) comes from
`Rng`, a SplitMix64 stream with its own sampling rules, so a seed means the same game on every machine.
`random.Random` and NumPy generators are avoided on purpose: their sampling methods are not part of any
stability promise.
"""

from __future__ import annotations

import hashlib
from collections.abc import MutableSequence, Sequence

_MASK64 = (1 << 64) - 1


def derive_seed(*parts: str | int) -> int:
    """A 64-bit seed from labelled parts, e.g. `derive_seed("v0.1", "tetris", "bag", 7)`."""
    text = "\x1f".join(str(part) for part in parts)
    return int.from_bytes(hashlib.blake2b(text.encode(), digest_size=8).digest(), "big")


class Rng:
    """SplitMix64 (Steele, Lea and Flood 2014) with unbiased integer sampling."""

    __slots__ = ("_state",)

    def __init__(self, seed: int) -> None:
        self._state = seed & _MASK64

    @classmethod
    def derive(cls, *parts: str | int) -> Rng:
        return cls(derive_seed(*parts))

    def next_u64(self) -> int:
        self._state = (self._state + 0x9E3779B97F4A7C15) & _MASK64
        z = self._state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
        return z ^ (z >> 31)

    def below(self, n: int) -> int:
        """Uniform integer in [0, n) by rejection sampling (no modulo bias)."""
        if n <= 0:
            raise ValueError(f"below() needs a positive bound, got {n}")
        limit = (1 << 64) - ((1 << 64) % n)
        while True:
            value = self.next_u64()
            if value < limit:
                return value % n

    def random(self) -> float:
        """Uniform float in [0, 1) with 53 random bits."""
        return (self.next_u64() >> 11) / float(1 << 53)

    def choice[T](self, items: Sequence[T]) -> T:
        return items[self.below(len(items))]

    def shuffle[T](self, items: MutableSequence[T]) -> None:
        """Fisher-Yates in place."""
        for i in range(len(items) - 1, 0, -1):
            j = self.below(i + 1)
            items[i], items[j] = items[j], items[i]

    def shuffled[T](self, items: Sequence[T]) -> list[T]:
        out = list(items)
        self.shuffle(out)
        return out
