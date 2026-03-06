"""
python/tools/agreement.py
Subject-verb agreement checker for quill.nvim.

Two detection strategies:
  1. _CLEAR_ERRORS: compiled regex table of known agreement mistakes.
  2. Collective-noun inconsistency: flag minority uses of "is" vs "are" for the
     same collective noun within the same text.
"""

import re
from collections import Counter
from typing import Any, Dict, List, Tuple

from .shared import byte_to_line_col, make_flag


# ---------------------------------------------------------------------------
# Clear-error patterns
# ---------------------------------------------------------------------------

_CLEAR_ERRORS: List[Tuple[re.Pattern, str, float]] = [
    # Latin plurals used with singular verb
    (re.compile(r"\bdata\s+is\b",       re.IGNORECASE), "Latin plural: 'data' takes 'are' (formally)", 0.65),
    (re.compile(r"\bcriteria\s+is\b",   re.IGNORECASE), "Latin plural: 'criteria' takes 'are'",        0.70),
    (re.compile(r"\bphenomena\s+is\b",  re.IGNORECASE), "Latin plural: 'phenomena' takes 'are'",       0.70),
    (re.compile(r"\bmedia\s+is\b",      re.IGNORECASE), "Latin plural: 'media' takes 'are' (formally)",0.60),
    (re.compile(r"\bstrata\s+is\b",     re.IGNORECASE), "Latin plural: 'strata' takes 'are'",          0.70),
    (re.compile(r"\bagenda\s+are\b",    re.IGNORECASE), "Latin singular: 'agenda' takes 'is'",         0.70),
    # Indefinite pronouns
    (re.compile(r"\beveryone\s+are\b",  re.IGNORECASE), "Agreement: 'everyone' takes singular verb",   0.75),
    (re.compile(r"\bsomeone\s+are\b",   re.IGNORECASE), "Agreement: 'someone' takes singular verb",    0.75),
    (re.compile(r"\banyone\s+are\b",    re.IGNORECASE), "Agreement: 'anyone' takes singular verb",     0.75),
    (re.compile(r"\bnobody\s+are\b",    re.IGNORECASE), "Agreement: 'nobody' takes singular verb",     0.75),
    (re.compile(r"\beverybody\s+are\b", re.IGNORECASE), "Agreement: 'everybody' takes singular verb",  0.75),
    # Idioms
    (re.compile(r"\bthe\s+number\s+of\s+\w+\s+are\b", re.IGNORECASE),
     "Idiom: 'the number of …' takes 'is'", 0.70),
    (re.compile(r"\ba\s+number\s+of\s+\w+\s+is\b", re.IGNORECASE),
     "Idiom: 'a number of …' takes 'are'", 0.70),
    # Disputed
    (re.compile(r"\bnone\s+of\s+the\s+\w+\s+are\b", re.IGNORECASE),
     "Disputed: 'none of the …' — singular 'is' is traditionally preferred", 0.50),
]

# ---------------------------------------------------------------------------
# Collective nouns
# ---------------------------------------------------------------------------

_COLLECTIVES = [
    "team", "committee", "government", "board", "staff", "faculty",
    "jury", "group", "class", "crowd", "public", "audience",
    "company", "firm",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flag_match(text: str, m: re.Match, severity: float, message: str) -> Dict[str, Any]:
    s_byte = len(text[:m.start()].encode("utf-8"))
    e_byte = len(text[:m.end()].encode("utf-8"))
    sl, sc = byte_to_line_col(text, s_byte)
    _,  ec = byte_to_line_col(text, e_byte)
    return make_flag(sl, sc, ec, severity, message)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    flags: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Pass 1: clear-error patterns
    # ------------------------------------------------------------------
    for pattern, message, severity in _CLEAR_ERRORS:
        for m in pattern.finditer(text):
            flags.append(_flag_match(text, m, severity, message))

    # ------------------------------------------------------------------
    # Pass 2: collective noun inconsistency
    # ------------------------------------------------------------------
    for noun in _COLLECTIVES:
        is_pat  = re.compile(rf"\bthe\s+{noun}\s+is\b",  re.IGNORECASE)
        are_pat = re.compile(rf"\bthe\s+{noun}\s+are\b", re.IGNORECASE)

        is_matches  = list(is_pat.finditer(text))
        are_matches = list(are_pat.finditer(text))

        if not is_matches or not are_matches:
            continue  # consistent (or absent) — no flag

        # The minority usage gets flagged
        if len(is_matches) <= len(are_matches):
            minority, majority_verb = is_matches, "are"
        else:
            minority, majority_verb = are_matches, "is"

        for m in minority:
            msg = (
                f"Inconsistent collective noun: '{noun}' used with both "
                f"'is' and 'are' — dominant form is '{majority_verb}'"
            )
            flags.append(_flag_match(text, m, 0.55, msg))

    return {"flags": flags}
