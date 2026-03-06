"""
python/tools/punctuation.py
Punctuation consistency checker for quill.nvim.

Checks:
  1. Em/en dash consistency  (—  –  or spaced hyphen)
  2. Quote style consistency  (smart vs straight)
  3. Oxford comma consistency
  4. Double spaces
"""

import re
from typing import Any, Dict, List

from .shared import byte_to_line_col, make_flag


# ---------------------------------------------------------------------------
# Helper: flag all occurrences of a pattern at a fixed severity
# ---------------------------------------------------------------------------

def _flag_pattern(text: str, pattern: re.Pattern, severity: float,
                  message: str) -> List[Dict[str, Any]]:
    flags = []
    for m in pattern.finditer(text):
        s_byte = len(text[:m.start()].encode("utf-8"))
        e_byte = len(text[:m.end()].encode("utf-8"))
        sl, sc = byte_to_line_col(text, s_byte)
        _el, ec = byte_to_line_col(text, e_byte)
        flags.append(make_flag(sl, sc, ec, severity, message))
    return flags


# ---------------------------------------------------------------------------
# 1. Em/en dash consistency
# ---------------------------------------------------------------------------

_EM_DASH     = re.compile(r"—")
_EN_DASH     = re.compile(r"–")
_SPACED_HYP  = re.compile(r" - ")   # spaced hyphen as dash


def _dash_flags(text: str) -> List[Dict[str, Any]]:
    em_matches   = list(_EM_DASH.finditer(text))
    en_matches   = list(_EN_DASH.finditer(text))
    hyp_matches  = list(_SPACED_HYP.finditer(text))

    counts = {
        "em":  (len(em_matches),  em_matches),
        "en":  (len(en_matches),  en_matches),
        "hyp": (len(hyp_matches), hyp_matches),
    }

    # Majority style = highest count; any others are minority
    majority_style = max(counts, key=lambda k: counts[k][0])
    majority_count = counts[majority_style][0]
    total = sum(c for c, _ in counts.values())

    if total == 0 or majority_count == total:
        return []   # homogeneous — no issue

    flags = []
    for style, (count, matches) in counts.items():
        if style == majority_style or count == 0:
            continue
        sev = round(0.6 * (count / total), 5)
        label = {"em": "em dash (—)", "en": "en dash (–)", "hyp": "spaced hyphen ( - )"}[style]
        msg   = f"Inconsistent dash style: '{label}' mixed with '{majority_style}' style"
        for m in matches:
            s_byte = len(text[:m.start()].encode("utf-8"))
            e_byte = len(text[:m.end()].encode("utf-8"))
            sl, sc = byte_to_line_col(text, s_byte)
            _el, ec = byte_to_line_col(text, e_byte)
            flags.append(make_flag(sl, sc, ec, sev, msg))

    return flags


# ---------------------------------------------------------------------------
# 2. Quote style consistency
# ---------------------------------------------------------------------------

_SMART_DOUBLE = re.compile(r'[\u201c\u201d]')   # " "
_SMART_SINGLE = re.compile(r'[\u2018\u2019]')   # ' '
_STRAIGHT_DBL = re.compile(r'"')                # "
_STRAIGHT_SGL = re.compile(r"'")


def _quote_flags(text: str) -> List[Dict[str, Any]]:
    flags = []

    # Double quotes
    smart_d = list(_SMART_DOUBLE.finditer(text))
    # Exclude the curly-quote chars already counted as smart
    straight_d = [m for m in _STRAIGHT_DBL.finditer(text)]
    _emit_quote_inconsistency(text, smart_d, straight_d, "double", flags)

    # Single quotes (apostrophes are common — only flag if both styles clearly used)
    smart_s    = [m for m in _SMART_SINGLE.finditer(text)
                  if m.group() in ("\u2018", "\u2019")]
    straight_s = list(_STRAIGHT_SGL.finditer(text))
    _emit_quote_inconsistency(text, smart_s, straight_s, "single", flags)

    return flags


def _emit_quote_inconsistency(text: str, smart_matches, straight_matches,
                               quote_type: str, flags: List) -> None:
    n_smart    = len(smart_matches)
    n_straight = len(straight_matches)
    total      = n_smart + n_straight

    if total == 0 or n_smart == 0 or n_straight == 0:
        return

    minority_matches = smart_matches if n_smart <= n_straight else straight_matches
    minority_label   = "smart" if n_smart <= n_straight else "straight"

    msg = f"Inconsistent {quote_type} quote style: {minority_label} quotes mixed with majority style"
    for m in minority_matches:
        s_byte = len(text[:m.start()].encode("utf-8"))
        e_byte = len(text[:m.end()].encode("utf-8"))
        sl, sc = byte_to_line_col(text, s_byte)
        _el, ec = byte_to_line_col(text, e_byte)
        flags.append(make_flag(sl, sc, ec, 0.7, msg))


# ---------------------------------------------------------------------------
# 3. Oxford comma consistency
# ---------------------------------------------------------------------------

_NO_OXFORD  = re.compile(r"\b\w+,\s+\w+\s+and\s+\w+\b")
_HAS_OXFORD = re.compile(r"\b\w+,\s+\w+,\s+and\s+\w+\b")


def _oxford_flags(text: str) -> List[Dict[str, Any]]:
    no_ox  = list(_NO_OXFORD.finditer(text))
    has_ox = list(_HAS_OXFORD.finditer(text))

    # Separate: no_oxford patterns must not overlap with oxford ones
    # (oxford regex is more specific so its matches are correct)
    oxford_spans = {m.span() for m in has_ox}
    no_ox = [m for m in no_ox
             if not any(m.start() >= os and m.end() <= oe for os, oe in oxford_spans)]

    if not no_ox or not has_ox:
        return []

    flags = []
    majority_style = "oxford" if len(has_ox) >= len(no_ox) else "no-oxford"
    minority_matches = no_ox if majority_style == "oxford" else has_ox
    minority_label   = "no-oxford" if majority_style == "oxford" else "oxford"

    msg = f"Inconsistent Oxford comma: {minority_label} style mixed with {majority_style} style"
    for m in minority_matches:
        s_byte = len(text[:m.start()].encode("utf-8"))
        e_byte = len(text[:m.end()].encode("utf-8"))
        sl, sc = byte_to_line_col(text, s_byte)
        _el, ec = byte_to_line_col(text, e_byte)
        flags.append(make_flag(sl, sc, ec, 0.5, msg))

    return flags


# ---------------------------------------------------------------------------
# 4. Double spaces (within a line)
# ---------------------------------------------------------------------------

_DOUBLE_SPACE = re.compile(r"(?<!\n) {2,}(?!\n)")


def _double_space_flags(text: str) -> List[Dict[str, Any]]:
    return _flag_pattern(text, _DOUBLE_SPACE, 0.8, "Double space")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    flags: List[Dict[str, Any]] = []
    flags.extend(_dash_flags(text))
    flags.extend(_quote_flags(text))
    flags.extend(_oxford_flags(text))
    flags.extend(_double_space_flags(text))
    return {"flags": flags}
