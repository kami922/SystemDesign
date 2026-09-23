"""Zipfian popularity weighting for seeded short codes.

Frequency is proportional to rank^-s (classic Zipf's law): a handful of
"hot" codes get most of the traffic and a long tail gets very little. This
is what actually exercises cache-aside realistically - uniform random
access to a code pool never produces cache pressure worth measuring.
"""
import numpy as np


def zipf_weights(n: int, s: float) -> list[float]:
    ranks = np.arange(1, n + 1)
    weights = 1.0 / np.power(ranks, s)
    weights = weights / weights.sum()
    return weights.tolist()
