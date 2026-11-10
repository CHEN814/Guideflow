from __future__ import annotations

from math import comb


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return (max(0.0, center - half), min(1.0, center + half))


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value for discordant counts b, c."""
    n = b + c
    if n == 0:
        return 1.0
    tail = min(b, c)
    p = sum(comb(n, k) for k in range(0, tail + 1)) / (2**n)
    return min(1.0, 2 * p)


def bootstrap_ci(values: list[float], n_boot: int = 2000, z_seed: int = 7) -> tuple[float | None, float | None]:
    """Percentile 95% CI. Deterministic LCG so we do not depend on numpy."""
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return (None, None)
    if len(vals) == 1:
        return (vals[0], vals[0])
    state = z_seed
    n = len(vals)
    samples: list[float] = []
    for _ in range(n_boot):
        acc = 0.0
        for _i in range(n):
            state = (1664525 * state + 1013904223) % (2**32)
            acc += vals[state % n]
        samples.append(acc / n)
    samples.sort()
    lo = samples[int(0.025 * (n_boot - 1))]
    hi = samples[int(0.975 * (n_boot - 1))]
    return (round(lo, 4), round(hi, 4))


def cohen_kappa(a_labels: list, b_labels: list) -> float:
    if len(a_labels) != len(b_labels) or not a_labels:
        return 0.0
    n = len(a_labels)
    agree = sum(x == y for x, y in zip(a_labels, b_labels)) / n
    labels = sorted(set(a_labels) | set(b_labels))
    pe = 0.0
    for lab in labels:
        pe += (a_labels.count(lab) / n) * (b_labels.count(lab) / n)
    if pe >= 1:
        return 1.0
    return (agree - pe) / (1 - pe)
