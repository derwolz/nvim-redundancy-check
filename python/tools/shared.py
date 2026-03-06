"""
python/tools/shared.py
Shared utilities for all quill.nvim analysis tools.
"""

import re
from typing import Generator, Tuple, List, Dict, Any, Optional

MIN_WORD_LENGTH = 2


def tokenise(text: str) -> Generator[Tuple[str, int, int], None, None]:
    """
    Yield (norm, start_byte, end_byte) for every word token.
    start_byte / end_byte are byte offsets into the UTF-8-encoded text.
    """
    for m in re.finditer(r"\b[a-zA-Z']+\b", text):
        raw  = m.group()
        norm = raw.lower().strip("'")
        if len(norm) < MIN_WORD_LENGTH:
            continue
        s_byte = len(text[:m.start()].encode("utf-8"))
        e_byte = len(text[:m.end()].encode("utf-8"))
        yield norm, s_byte, e_byte


def byte_to_line_col(text: str, byte_offset: int) -> Tuple[int, int]:
    """Convert a byte offset into (0-indexed line, 0-indexed byte-col)."""
    chunk = text.encode("utf-8")[:byte_offset]
    lines = chunk.split(b"\n")
    line  = len(lines) - 1
    col   = len(lines[-1])
    return line, col


def build_positions(text: str) -> List[Dict[str, Any]]:
    """
    Return a list of position dicts for every word token:
      { word, s_line, s_col, e_line, e_col }
    """
    positions = []
    for norm, s_byte, e_byte in tokenise(text):
        sl, sc = byte_to_line_col(text, s_byte)
        el, ec = byte_to_line_col(text, e_byte)
        positions.append({
            "word":   norm,
            "s_line": sl,
            "s_col":  sc,
            "e_line": el,
            "e_col":  ec,
        })
    return positions


def make_flag(
    s_line: int,
    s_col: int,
    e_col: int,
    severity: float,
    message: str,
    group: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a flag dict in the standard contract format."""
    flag: Dict[str, Any] = {
        "s_line":   s_line,
        "s_col":    s_col,
        "e_col":    e_col,
        "severity": round(severity, 5),
        "message":  message,
    }
    if group is not None:
        flag["group"] = group
    return flag
