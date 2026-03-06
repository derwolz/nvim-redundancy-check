"""
python/tools/tense.py
Tense consistency checker for quill.nvim.

Classifies each sentence as past/present/future, determines the dominant tense,
and flags sentences that deviate. Severity is boosted when a deviating sentence
is surrounded by opposite-tense neighbours.
"""

import re
from collections import Counter
from typing import Any, Dict, List, Optional

from .shared import byte_to_line_col, make_flag


# ---------------------------------------------------------------------------
# Tense detection regexes
# ---------------------------------------------------------------------------

_PAST = re.compile(
    r"\b(?:was|were|had|did|would|could|should|might|used\s+to|\w+ed)\b",
    re.IGNORECASE,
)
_PRESENT = re.compile(
    r"\b(?:is|are|am|has|have|do|does|will|shall|can|may|must|\w+s)\b",
    re.IGNORECASE,
)
_FUTURE = re.compile(
    r"\b(?:will|shall|going\s+to|about\s+to|is\s+to|are\s+to)\b",
    re.IGNORECASE,
)


def _classify_sentence(sent_text: str) -> str:
    future_score  = len(_FUTURE.findall(sent_text)) * 2
    past_score    = len(_PAST.findall(sent_text))
    present_score = len(_PRESENT.findall(sent_text))

    if future_score == 0 and past_score == 0 and present_score == 0:
        return "unknown"

    best = max(
        ("past",    past_score),
        ("present", present_score),
        ("future",  future_score),
        key=lambda x: x[1],
    )
    return best[0]


# ---------------------------------------------------------------------------
# Sentence splitting (local copy — no cross-tool import)
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> List[Dict[str, Any]]:
    sentences = []
    for m in re.finditer(r"[^.!?]+[.!?]+", text):
        raw    = m.group()
        s_byte = len(text[:m.start()].encode("utf-8"))
        e_byte = len(text[:m.end()].encode("utf-8"))
        sl, sc = byte_to_line_col(text, s_byte)
        el, ec = byte_to_line_col(text, e_byte)
        sentences.append({
            "text":   raw,
            "s_byte": s_byte,
            "e_byte": e_byte,
            "s_line": sl,
            "s_col":  sc,
            "e_line": el,
            "e_col":  ec,
        })
    return sentences


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    expected_tense = config.get("expected_tense", "auto")
    base_severity  = float(config.get("base_severity", 0.6))

    sentences = _split_sentences(text)
    if not sentences:
        return {"flags": [], "meta": {"dominant_tense": "unknown"}}

    tenses = [_classify_sentence(s["text"]) for s in sentences]

    # Determine dominant tense
    known = [t for t in tenses if t != "unknown"]
    if not known:
        return {"flags": [], "meta": {"dominant_tense": "unknown"}}

    if expected_tense == "auto":
        dominant = Counter(known).most_common(1)[0][0]
    else:
        dominant = expected_tense

    flags: List[Dict[str, Any]] = []
    n = len(sentences)

    for idx, (s, t) in enumerate(zip(sentences, tenses)):
        if t == "unknown" or t == dominant:
            continue

        sev = base_severity

        # Boost if surrounded by opposite-tense neighbours
        prev_t = tenses[idx - 1] if idx > 0 else None
        next_t = tenses[idx + 1] if idx < n - 1 else None
        if (prev_t == dominant or prev_t is None) and (next_t == dominant or next_t is None):
            sev = min(1.0, sev + 0.2)

        msg = (
            f"Tense shift: sentence appears {t} "
            f"(dominant tense is {dominant})"
        )
        flags.append(make_flag(s["s_line"], s["s_col"], s["e_col"], sev, msg))

    return {
        "flags": flags,
        "meta":  {"dominant_tense": dominant},
    }
