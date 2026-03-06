"""
python/tools/redundancy.py
Redundancy checker for quill.nvim.

Detects words that are semantically similar (by Levenshtein ratio) within a
rolling window, with frequency-dampening and distance decay.

Each pair produces TWO flag entries sharing the same `group` id, one for each
word in the pair. This lets the Lua cursor handler blue-highlight both members
when the user hovers over either one.
"""

import math
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Dict, List

from .shared import build_positions, make_flag


# ---------------------------------------------------------------------------
# Defaults (overridable via config dict)
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "frequency_sensitivity": 50.0,
    "decay_rate":            2.0,
    "similarity_threshold":  0.82,
    "min_severity":          0.03,
    "window":                300,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _decay(distance: int, rate: float) -> float:
    return 1.0 / math.log(math.e + distance * rate)


def _freq_weight(word: str, counter: Counter, total: int, sensitivity: float) -> float:
    return 1.0 / (1.0 + sensitivity * (counter[word] / total))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    cfg = {**_DEFAULTS, **config}

    freq_sens  = float(cfg["frequency_sensitivity"])
    decay_rate = float(cfg["decay_rate"])
    sim_thresh = float(cfg["similarity_threshold"])
    min_sev    = float(cfg["min_severity"])
    window     = int(cfg["window"])

    positions = build_positions(text)
    if not positions:
        return {"flags": [], "tokens": []}

    norms   = [p["word"] for p in positions]
    total   = len(norms)
    counter = Counter(norms)

    flags: List[Dict[str, Any]] = []
    seen:  set = set()
    group_id   = 0

    for i in range(len(positions)):
        for j in range(i + 1, min(i + window, len(positions))):
            key = (i, j)
            if key in seen:
                continue
            seen.add(key)

            wa   = positions[i]["word"]
            wb   = positions[j]["word"]
            dist = j - i

            sim = _similarity(wa, wb)
            if sim < sim_thresh:
                continue

            fwa = _freq_weight(wa, counter, total, freq_sens)
            fwb = _freq_weight(wb, counter, total, freq_sens)
            dec = _decay(dist, decay_rate)
            sev = sim * fwa * fwb * dec

            if sev < min_sev:
                continue

            # Flag for word A
            pa = positions[i]
            flags.append(make_flag(
                pa["s_line"], pa["s_col"], pa["e_col"],
                sev,
                f"Similar to '{wb}' ({dist} words away, {sim:.0%} match)",
                group=group_id,
            ))

            # Flag for word B
            pb = positions[j]
            flags.append(make_flag(
                pb["s_line"], pb["s_col"], pb["e_col"],
                sev,
                f"Similar to '{wa}' ({dist} words away, {sim:.0%} match)",
                group=group_id,
            ))

            group_id += 1

    return {"flags": flags, "tokens": []}
