"""Small, dependency-free statistics: proportions with Wilson intervals and an exact McNemar test."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Rate:
    """k successes out of n, with a Wilson 95% confidence interval (in percent)."""

    k: int
    n: int

    @property
    def pct(self) -> float:
        return 100 * self.k / self.n if self.n else float("nan")

    @property
    def ci(self) -> tuple[float, float]:
        return wilson(self.k, self.n)

    def to_dict(self) -> dict[str, float | None]:
        """JSON-safe: an empty rate (n = 0) has no percentage or interval, so those are None."""
        if not self.n:
            return {**asdict(self), "pct": None, "lo": None, "hi": None}
        lo, hi = self.ci
        return {**asdict(self), "pct": round(self.pct, 1), "lo": round(lo, 1), "hi": round(hi, 1)}

    def __str__(self) -> str:
        if not self.n:
            return "-"
        lo, hi = self.ci
        return f"{self.k}/{self.n} = {self.pct:.0f}% ({lo:.0f}-{hi:.0f})"


def rate(flags: Iterable[bool]) -> Rate:
    flags = list(flags)
    return Rate(sum(map(bool, flags)), len(flags))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for k/n, in percent. Better behaved than the normal interval near 0% and 100%."""
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return 100 * max(0.0, centre - half), 100 * min(1.0, centre + half)


def mcnemar_exact(a: Iterable[bool], b: Iterable[bool]) -> dict[str, float]:
    """Exact two-sided McNemar test for paired yes/no outcomes (e.g. two checkers on the same cases).

    Only discordant pairs carry information: b01 = only `b` said yes, b10 = only `a` said yes.
    """
    pairs = list(zip(a, b, strict=True))
    b10 = sum(1 for x, y in pairs if x and not y)
    b01 = sum(1 for x, y in pairs if y and not x)
    n = b10 + b01
    if n == 0:
        return {"only_a": 0, "only_b": 0, "p_value": 1.0}
    tail = sum(math.comb(n, i) for i in range(min(b10, b01) + 1)) / 2**n
    return {"only_a": b10, "only_b": b01, "p_value": round(min(1.0, 2 * tail), 4)}
