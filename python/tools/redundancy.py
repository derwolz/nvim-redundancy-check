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
    "frequency_sensitivity":          50.0,
    "decay_rate":                     2.0,
    "similarity_threshold":           0.82,
    "min_severity":                   0.03,
    "window":                         300,
    "stopword_sensitivity_multiplier": 10.0,
}

# Common function words — expected to repeat constantly; apply sharper dropoff
_FUNCTION_WORDS = {
    "the", "and", "of", "to", "in", "for", "on", "with", "at", "by",
    "from", "or", "but", "as", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "not", "no", "so",
    "if", "then", "than", "that", "this", "these", "those", "it", "its",
    "he", "she", "they", "we", "you", "me", "him", "her", "them", "us",
    "my", "your", "his", "our", "their", "an", "up", "out", "about",
    "into", "through", "over", "after", "before", "between", "each",
    "also", "just", "more", "when", "which", "who", "what", "how",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _decay(distance: int, rate: float) -> float:
    return 1.0 / math.log(math.e + distance * rate)


def _freq_weight(word: str, counter: Counter, total: int, sensitivity: float,
                 stopword_multiplier: float) -> float:
    eff = sensitivity * (stopword_multiplier if word in _FUNCTION_WORDS else 1.0)
    return 1.0 / (1.0 + eff * (counter[word] / total))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    cfg = {**_DEFAULTS, **config}

    freq_sens        = float(cfg["frequency_sensitivity"])
    decay_rate       = float(cfg["decay_rate"])
    sim_thresh       = float(cfg["similarity_threshold"])
    min_sev          = float(cfg["min_severity"])
    window           = int(cfg["window"])
    stopword_mult    = float(cfg["stopword_sensitivity_multiplier"])

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

            fwa = _freq_weight(wa, counter, total, freq_sens, stopword_mult)
            fwb = _freq_weight(wb, counter, total, freq_sens, stopword_mult)
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
