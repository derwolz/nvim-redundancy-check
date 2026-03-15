"""
python/tools/redundancy.py
Redundancy checker for quill.nvim.

Detects words that are semantically similar (by SequenceMatcher ratio) within a
rolling window, with frequency-dampening and distance decay.

Each pair produces TWO flag entries sharing the same `group` id, one for each
word in the pair. This lets the Lua cursor handler cyan-highlight both members
when the user hovers over either one.

Performance notes
-----------------
Three cheap pre-filters are applied before the expensive similarity call:
  1. Length-ratio reject  – if the ratio of lengths can't possibly reach the
     threshold, skip (O(1)).
  2. Trigram disjoint check – words with zero shared character trigrams are
     nearly guaranteed to be below threshold; checked with a frozenset
     (O(word_len), not O(word_len²)).
  3. rapidfuzz (optional)  – if installed (`pip install rapidfuzz`), the
     similarity call is done in C++ with an early-exit score_cutoff, giving
     10-100× speedup over pure-Python SequenceMatcher.
"""

import math
from collections import Counter
from typing import Any, Dict, List

from .shared import build_positions, make_flag


# ---------------------------------------------------------------------------
# Fast similarity backend — rapidfuzz when available, difflib fallback
# ---------------------------------------------------------------------------

try:
    from rapidfuzz import fuzz as _rf

    def _similarity(a: str, b: str, cutoff: float = 0.0) -> float:
        # score_cutoff causes early exit if the score can't reach the threshold;
        # returns 0.0 in that case.  Divide by 100 to match difflib's 0–1 range.
        return _rf.ratio(a, b, score_cutoff=cutoff * 100) / 100.0

except ImportError:
    from difflib import SequenceMatcher as _SM  # type: ignore

    def _similarity(a: str, b: str, cutoff: float = 0.0) -> float:  # noqa: F811
        return _SM(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Defaults (overridable via config dict)
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "frequency_sensitivity":           50.0,
    "decay_rate":                      2.0,
    "similarity_threshold":            0.82,
    "min_severity":                    0.03,
    "window":                          200,
    "fuzzy_sentence_window":           20,   # max word-distance for non-exact matches
    "fuzzy_decay_multiplier":          3.0,  # steeper dropoff for fuzzy pairs
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

def _trigrams(word: str) -> frozenset:
    """Character trigrams of a word; falls back to the word itself if short."""
    if len(word) < 3:
        return frozenset([word])
    return frozenset(word[i:i + 3] for i in range(len(word) - 2))


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
    fuzzy_win        = int(cfg["fuzzy_sentence_window"])
    fuzzy_decay_mult = float(cfg["fuzzy_decay_multiplier"])
    stopword_mult    = float(cfg["stopword_sensitivity_multiplier"])

    positions = build_positions(text)
    if not positions:
        return {"flags": [], "tokens": []}

    norms   = [p["word"] for p in positions]
    total   = len(norms)
    counter = Counter(norms)

    # Pre-compute trigram sets once — O(n * word_len)
    tri_sets = [_trigrams(w) for w in norms]

    flags: List[Dict[str, Any]] = []
    group_id = 0

    for i in range(len(positions)):
        wa    = norms[i]
        len_a = len(wa)
        tris_a = tri_sets[i]

        for j in range(i + 1, min(i + window, len(positions))):
            wb    = norms[j]
            len_b = len(wb)

            # --- Pre-filter 1: length ratio (O(1)) ----------------------------
            # SequenceMatcher ratio ≤ 2*min_len / (len_a + len_b).
            # If that ceiling is already below the threshold, skip.
            if 2.0 * min(len_a, len_b) / (len_a + len_b) < sim_thresh:
                continue

            # --- Pre-filter 2: trigram disjoint check (O(word_len)) -----------
            # Words that share no character trigram almost never reach the
            # threshold; eliminate them without calling the similarity function.
            if tris_a.isdisjoint(tri_sets[j]):
                continue

            # --- Full similarity (now called on a small fraction of pairs) ----
            sim = _similarity(wa, wb, cutoff=sim_thresh)
            if sim < sim_thresh:
                continue

            dist     = j - i
            is_exact = (wa == wb)

            # Issue #1: fuzzy (non-exact) matches only matter within ~1 sentence
            if not is_exact and dist > fuzzy_win:
                continue

            fwa  = _freq_weight(wa, counter, total, freq_sens, stopword_mult)
            fwb  = _freq_weight(wb, counter, total, freq_sens, stopword_mult)
            # Apply steeper decay for fuzzy pairs
            eff_rate = decay_rate if is_exact else decay_rate * fuzzy_decay_mult
            dec  = _decay(dist, eff_rate)
            sev  = sim * fwa * fwb * dec

            if sev < min_sev:
                continue

            pa = positions[i]
            flags.append(make_flag(
                pa["s_line"], pa["s_col"], pa["e_col"],
                sev,
                f"Similar to '{wb}' ({dist} words away, {sim:.0%} match)",
                group=group_id,
            ))

            pb = positions[j]
            flags.append(make_flag(
                pb["s_line"], pb["s_col"], pb["e_col"],
                sev,
                f"Similar to '{wa}' ({dist} words away, {sim:.0%} match)",
                group=group_id,
            ))

            group_id += 1

    return {"flags": flags, "tokens": []}
