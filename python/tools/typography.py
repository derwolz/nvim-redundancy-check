"""
python/tools/typography.py
Typography checker for quill.nvim.

Handles absolute formatting errors (always wrong), complementary to
punctuation.py which handles inconsistency between valid choices.

Checks:
  1. Double spaces (always flag, severity 0.9)
  2. Trailing whitespace
  3. Ellipsis consistency (… vs ...)
  4. Dumb/straight quotes in an otherwise smart-quote document
"""

import re
from typing import Any, Dict, List

from .shared import byte_to_line_col, make_flag


# ---------------------------------------------------------------------------
# Helper
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
# 1. Double spaces
# ---------------------------------------------------------------------------

_DOUBLE_SPACE = re.compile(r"(?<!\n) {2,}(?!\n)")


def _double_space_flags(text: str) -> List[Dict[str, Any]]:
    return _flag_pattern(text, _DOUBLE_SPACE, 0.9, "Double space (typography error)")


# ---------------------------------------------------------------------------
# 2. Trailing whitespace
# ---------------------------------------------------------------------------

_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)


def _trailing_ws_flags(text: str) -> List[Dict[str, Any]]:
    return _flag_pattern(text, _TRAILING_WS, 0.7, "Trailing whitespace")


# ---------------------------------------------------------------------------
# 3. Ellipsis consistency
# ---------------------------------------------------------------------------

_UNICODE_ELLIPSIS = re.compile(r"\u2026")    # …
_THREE_DOTS       = re.compile(r"\.\.\.(?!\.)")  # ... (not ....)


def _ellipsis_flags(text: str) -> List[Dict[str, Any]]:
    uni_matches = list(_UNICODE_ELLIPSIS.finditer(text))
    dot_matches = list(_THREE_DOTS.finditer(text))

    n_uni = len(uni_matches)
    n_dot = len(dot_matches)

    if n_uni == 0 or n_dot == 0:
        return []

    minority_matches = uni_matches if n_uni <= n_dot else dot_matches
    minority_label   = "Unicode ellipsis (…)" if n_uni <= n_dot else "three-dot ellipsis (...)"

    flags = []
    for m in minority_matches:
        s_byte = len(text[:m.start()].encode("utf-8"))
        e_byte = len(text[:m.end()].encode("utf-8"))
        sl, sc = byte_to_line_col(text, s_byte)
        _el, ec = byte_to_line_col(text, e_byte)
        msg = f"Inconsistent ellipsis: {minority_label} mixed with majority style"
        flags.append(make_flag(sl, sc, ec, 0.6, msg))

    return flags


# ---------------------------------------------------------------------------
# 4. Straight quotes in a smart-quote document
# ---------------------------------------------------------------------------

_SMART_QUOTE   = re.compile(r'[\u201c\u201d\u2018\u2019]')
_STRAIGHT_QUOT = re.compile(r'["\']')


def _dumb_quote_flags(text: str) -> List[Dict[str, Any]]:
    n_smart    = len(_SMART_QUOTE.findall(text))
    n_straight = len(_STRAIGHT_QUOT.findall(text))

    # Only flag if the document predominantly uses smart quotes
    if n_smart == 0 or n_straight == 0:
        return []
    if n_smart < n_straight:
        return []   # doc uses straight quotes — not a typography error here

    flags = []
    for m in _STRAIGHT_QUOT.finditer(text):
        s_byte = len(text[:m.start()].encode("utf-8"))
        e_byte = len(text[:m.end()].encode("utf-8"))
        sl, sc = byte_to_line_col(text, s_byte)
        _el, ec = byte_to_line_col(text, e_byte)
        msg = "Straight quote in smart-quote document"
        flags.append(make_flag(sl, sc, ec, 0.8, msg))

    return flags


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    flags: List[Dict[str, Any]] = []
    flags.extend(_double_space_flags(text))
    flags.extend(_trailing_ws_flags(text))
    flags.extend(_ellipsis_flags(text))
    flags.extend(_dumb_quote_flags(text))
    return {"flags": flags}
