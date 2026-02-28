"""
redundancy.nvim — analysis backend
Reads a file path from argv[1], runs the redundancy checker, and prints
a JSON array of flag objects to stdout for the Lua plugin to consume.

Each flag includes byte-level line/col positions so Neovim extmarks work
correctly regardless of multibyte characters.
"""

import re
import sys
import json
import math
from difflib import SequenceMatcher
from collections import Counter


# ---------------------------------------------------------------------------
# Parameters (can be overridden via argv)
# ---------------------------------------------------------------------------

FREQUENCY_SENSITIVITY  = float(sys.argv[2]) if len(sys.argv) > 2 else 50.0
DECAY_RATE             = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
SIMILARITY_THRESHOLD   = float(sys.argv[4]) if len(sys.argv) > 4 else 0.82
MIN_SEVERITY           = float(sys.argv[5]) if len(sys.argv) > 5 else 0.03
MIN_WORD_LENGTH        = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def tokenise(text: str):
    """
    Yield (norm, start_byte, end_byte) for every word token.
    start_byte / end_byte are offsets into the UTF-8 encoded text.
    """
    encoded = text.encode("utf-8")
    for m in re.finditer(r"\b[a-zA-Z']+\b", text):
        raw  = m.group()
        norm = raw.lower().strip("'")
        if len(norm) < MIN_WORD_LENGTH:
            continue
        # character offsets → byte offsets
        s_byte = len(text[:m.start()].encode("utf-8"))
        e_byte = len(text[:m.end()].encode("utf-8"))
        yield norm, s_byte, e_byte


def byte_offset_to_line_col(text: str, byte_offset: int):
    """Convert a byte offset into (0-indexed line, 0-indexed col-in-bytes)."""
    chunk   = text.encode("utf-8")[:byte_offset]
    lines   = chunk.split(b"\n")
    line    = len(lines) - 1
    col     = len(lines[-1])
    return line, col


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def decay(distance: int, rate: float) -> float:
    return 1.0 / math.log(math.e + distance * rate)


def freq_weight(word: str, counter: Counter, total: int, sensitivity: float) -> float:
    return 1.0 / (1.0 + sensitivity * (counter[word] / total))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("[]")
        return

    path = sys.argv[1]
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        print(json.dumps({"error": str(e)}))
        return

    # Collect all tokens with positions
    tokens = list(tokenise(text))
    if not tokens:
        print("[]")
        return

    norms   = [t[0] for t in tokens]
    total   = len(norms)
    counter = Counter(norms)

    # Pre-compute line/col for every token
    positions = []
    for norm, s_byte, e_byte in tokens:
        sl, sc = byte_offset_to_line_col(text, s_byte)
        el, ec = byte_offset_to_line_col(text, e_byte)
        positions.append({
            "word":     norm,
            "s_line":   sl,
            "s_col":    sc,
            "e_line":   el,
            "e_col":    ec,
        })

    # Compare every pair within a rolling window
    # We use a generous window — decay handles the severity, not a hard cutoff
    WINDOW = 300

    flags = []
    seen  = set()

    for i in range(len(positions)):
        for j in range(i + 1, min(i + WINDOW, len(positions))):
            key = (i, j)
            if key in seen:
                continue
            seen.add(key)

            wa = positions[i]["word"]
            wb = positions[j]["word"]
            dist = j - i

            sim = similarity(wa, wb)
            if sim < SIMILARITY_THRESHOLD:
                continue

            fwa = freq_weight(wa, counter, total, FREQUENCY_SENSITIVITY)
            fwb = freq_weight(wb, counter, total, FREQUENCY_SENSITIVITY)
            dec = decay(dist, DECAY_RATE)
            sev = sim * fwa * fwb * dec

            if sev < MIN_SEVERITY:
                continue

            flags.append({
                "i":        i,
                "j":        j,
                "word_a":   wa,
                "word_b":   wb,
                "dist":     dist,
                "sim":      round(sim, 4),
                "severity": round(sev, 5),
                "pos_a":    positions[i],
                "pos_b":    positions[j],
            })

    # Also output the full token list so Lua can do cursor-word lookup
    output = {
        "flags":    flags,
        "tokens":   positions,
    }

    print(json.dumps(output))


main()
