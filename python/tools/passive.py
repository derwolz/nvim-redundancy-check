"""
python/tools/passive.py
Passive voice detector for quill.nvim.

Flags runs of passive-voice sentences. Short runs get a mild severity;
clusters >= cluster_threshold get a higher severity with a cluster message.
"""

import re
from typing import Any, Dict, List

from .shared import byte_to_line_col, make_flag


# ---------------------------------------------------------------------------
# Irregular past-participle forms
# ---------------------------------------------------------------------------

_IRREGULAR_PP = (
    "written|taken|given|seen|known|done|gone|made|said|found|left|brought|"
    "thought|built|kept|sent|set|put|cut|let|hit|run|become|come|begun|"
    "broken|chosen|drawn|driven|eaten|fallen|flown|forgotten|frozen|grown|"
    "hidden|hurt|lost|paid|proven|read|ridden|risen|shown|spoken|stolen|"
    "sworn|taught|told|thrown|understood|worn|won"
)

_PASSIVE_RE = re.compile(
    r"\b(?:am|is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?"
    r"(?:\w+ed|" + _IRREGULAR_PP + r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Sentence splitting (local copy of rhythm.py pattern — no import)
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
            "is_passive": bool(_PASSIVE_RE.search(raw)),
        })
    return sentences


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    cluster_threshold = int(config.get("cluster_threshold", 3))
    base_severity     = float(config.get("base_severity", 0.4))
    cluster_severity  = float(config.get("cluster_severity", 0.65))

    sentences = _split_sentences(text)
    if not sentences:
        return {"flags": [], "meta": {"passive_ratio": 0.0}}

    passive_count = sum(1 for s in sentences if s["is_passive"])
    passive_ratio = passive_count / len(sentences)

    flags: List[Dict[str, Any]] = []
    i = 0
    while i < len(sentences):
        if not sentences[i]["is_passive"]:
            i += 1
            continue

        # Extend run of consecutive passive sentences
        run_start = i
        while i < len(sentences) and sentences[i]["is_passive"]:
            i += 1
        run_end = i  # exclusive
        run_len = run_end - run_start

        if run_len >= cluster_threshold:
            sev = cluster_severity
            msg = (
                f"Passive-voice cluster: {run_len} consecutive passive sentences"
            )
        else:
            sev = base_severity
            msg = "Passive voice construction"

        for k in range(run_start, run_end):
            s = sentences[k]
            flags.append(make_flag(s["s_line"], s["s_col"], s["e_col"], sev, msg))

    return {
        "flags": flags,
        "meta":  {"passive_ratio": round(passive_ratio, 3)},
    }
