"""
python/tools/structure.py
Sentence structure variety checker for quill.nvim.

Three passes:
  1. Same-opener runs (≥ run_threshold consecutive sentences starting the same way)
  2. Expletive constructions ("There is/are…", "It is/was…")
  3. "The [noun]" rut (>= the_rut_ratio of all sentences start with "The")
"""

import re
from typing import Any, Dict, List

from .shared import byte_to_line_col, make_flag


# ---------------------------------------------------------------------------
# Expletive patterns (anchored to sentence start after optional whitespace)
# ---------------------------------------------------------------------------

_EXPLETIVE_RE = re.compile(
    r"^\s*(?:"
    r"There\s+(?:is|are|was|were|have\s+been|has\s+been)"
    r"|It\s+(?:is|was|seems|appears|would\s+seem|would\s+appear)"
    r")",
    re.IGNORECASE,
)

# "The" opener (case-sensitive to avoid mid-sentence "the")
_THE_RE = re.compile(r"^\s*The\s", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Sentence splitting (local copy)
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
            "text":    raw,
            "s_byte":  s_byte,
            "e_byte":  e_byte,
            "s_line":  sl,
            "s_col":   sc,
            "e_line":  el,
            "e_col":   ec,
            "m_start": m.start(),   # character offset into text
        })
    return sentences


def _first_word(sent_text: str) -> str:
    """Return the lowercased first alphabetic word of a sentence."""
    m = re.search(r"[a-zA-Z]+", sent_text)
    return m.group().lower() if m else ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    run_threshold = int(config.get("run_threshold", 3))
    the_rut_ratio = float(config.get("the_rut_ratio", 0.40))

    sentences = _split_sentences(text)
    if not sentences:
        return {"flags": []}

    flags: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Pass 1: Same-opener runs
    # ------------------------------------------------------------------
    openers = [_first_word(s["text"]) for s in sentences]
    i = 0
    while i < len(sentences):
        opener = openers[i]
        if not opener:
            i += 1
            continue

        run = [i]
        j = i + 1
        while j < len(sentences) and openers[j] == opener:
            run.append(j)
            j += 1

        if len(run) >= run_threshold:
            sev = min(1.0, 0.4 + 0.1 * (len(run) - run_threshold))
            msg = (
                f"Repetitive sentence opener: '{opener}' used "
                f"{len(run)} times in a row"
            )
            for k in run:
                s = sentences[k]
                flags.append(make_flag(s["s_line"], s["s_col"], s["e_col"], sev, msg))
            i = run[-1] + 1
        else:
            i += 1

    # ------------------------------------------------------------------
    # Pass 2: Expletive constructions
    # ------------------------------------------------------------------
    for s in sentences:
        m = _EXPLETIVE_RE.match(s["text"])
        if not m:
            continue
        # Flag just the expletive span
        span_bytes = len(m.group(0).encode("utf-8"))
        e_col = s["s_col"] + span_bytes
        flags.append(make_flag(
            s["s_line"], s["s_col"], e_col,
            0.5,
            f"Expletive construction: '{m.group(0).strip()}' — consider restructuring",
        ))

    # ------------------------------------------------------------------
    # Pass 3: "The [noun]" rut
    # ------------------------------------------------------------------
    total = len(sentences)
    the_count = sum(1 for s in sentences if _THE_RE.match(s["text"]))
    if total > 0 and the_count / total > the_rut_ratio:
        for s in sentences:
            if _THE_RE.match(s["text"]):
                # Flag just the 3-byte "The" span
                flags.append(make_flag(
                    s["s_line"], s["s_col"], s["s_col"] + 3,
                    0.45,
                    f"'The' rut: {the_count}/{total} sentences start with 'The'",
                ))

    return {"flags": flags}
