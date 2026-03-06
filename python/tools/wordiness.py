"""
python/tools/wordiness.py
Wordiness / verbosity checker for quill.nvim.

Detects inflated phrases, hollow openers, redundant pairs, weasel qualifiers,
and bloated comparatives, and suggests tighter alternatives.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from .shared import byte_to_line_col, make_flag


# ---------------------------------------------------------------------------
# Pattern table: (regex_str, suggestion_or_None, base_severity, category)
# Each pattern is case-insensitive.
# suggestion=None means the phrase adds no meaning ("Delete: adds no meaning").
# ---------------------------------------------------------------------------

_PATTERNS: List[Tuple[str, Optional[str], float, str]] = [
    # Hollow openers
    (r"\bit\s+is\s+important\s+to\s+note\s+that\b",     None,       0.85, "hollow"),
    (r"\bit\s+should\s+be\s+noted\s+that\b",             None,       0.80, "hollow"),
    (r"\bneedless\s+to\s+say\b",                          None,       0.90, "hollow"),
    (r"\bfor\s+what\s+it(?:'s|\s+is)\s+worth\b",         None,       0.70, "hollow"),
    (r"\bas\s+a\s+matter\s+of\s+fact\b",                  None,       0.75, "hollow"),
    (r"\bin\s+point\s+of\s+fact\b",                       None,       0.75, "hollow"),
    (r"\bthe\s+fact\s+of\s+the\s+matter\s+is\b",         None,       0.80, "hollow"),
    (r"\bat\s+this\s+point\s+in\s+time\b",                "now",      0.85, "hollow"),
    (r"\bin\s+today(?:'s|\s+day\s+and\s+age)\b",          "today",    0.70, "hollow"),
    (r"\bwhat\s+I(?:'m|\s+am)\s+trying\s+to\s+say\b",    None,       0.80, "hollow"),

    # Inflated prepositions
    (r"\bdue\s+to\s+the\s+fact\s+that\b",        "because",    0.90, "inflation"),
    (r"\bin\s+order\s+to\b",                      "to",         0.80, "inflation"),
    (r"\bprior\s+to\b",                           "before",     0.75, "inflation"),
    (r"\bsubsequent\s+to\b",                      "after",      0.75, "inflation"),
    (r"\bwith\s+regard\s+to\b",                   "about",      0.70, "inflation"),
    (r"\bwith\s+respect\s+to\b",                  "about",      0.70, "inflation"),
    (r"\bin\s+the\s+event\s+that\b",              "if",         0.85, "inflation"),
    (r"\bin\s+spite\s+of\s+the\s+fact\s+that\b", "although",   0.85, "inflation"),
    (r"\bon\s+the\s+occasion\s+of\b",             "when",       0.75, "inflation"),
    (r"\bfor\s+the\s+purpose\s+of\b",             "to",         0.80, "inflation"),
    (r"\bin\s+the\s+amount\s+of\b",               "of",         0.80, "inflation"),
    (r"\bat\s+the\s+present\s+time\b",            "now",        0.85, "inflation"),
    (r"\bduring\s+the\s+course\s+of\b",           "during",     0.80, "inflation"),
    (r"\bin\s+the\s+near\s+future\b",             "soon",       0.70, "inflation"),
    (r"\buntil\s+such\s+time\s+as\b",             "until",      0.85, "inflation"),

    # Weak verbs + nominalisation
    (r"\bmake\s+a\s+decision\b",           "decide",      0.85, "nominalization"),
    (r"\bmake\s+an\s+attempt\b",           "try",         0.85, "nominalization"),
    (r"\bgive\s+consideration\s+to\b",     "consider",    0.85, "nominalization"),
    (r"\bcome\s+to\s+a\s+conclusion\b",    "conclude",    0.85, "nominalization"),
    (r"\bperform\s+an\s+analysis\b",       "analyse",     0.80, "nominalization"),
    (r"\bconduct\s+an?\s+investigation\b", "investigate", 0.80, "nominalization"),
    (r"\bprovide\s+assistance\b",          "help",        0.80, "nominalization"),
    (r"\brender\s+assistance\b",           "help",        0.80, "nominalization"),
    (r"\bmake\s+a\s+recommendation\b",     "recommend",   0.80, "nominalization"),
    (r"\bcarry\s+out\s+a\s+review\b",      "review",      0.80, "nominalization"),
    (r"\btake\s+into\s+consideration\b",   "consider",    0.85, "nominalization"),
    (r"\bhave\s+an?\s+effect\s+on\b",      "affect",      0.80, "nominalization"),
    (r"\bexert\s+an?\s+influence\s+on\b",  "influence",   0.80, "nominalization"),
    (r"\bmake\s+use\s+of\b",               "use",         0.85, "nominalization"),
    (r"\bgive\s+rise\s+to\b",              "cause",       0.75, "nominalization"),

    # Redundant pairs
    (r"\beach\s+and\s+every\b",         "each",      0.90, "redundant_pair"),
    (r"\bfirst\s+and\s+foremost\b",     "first",     0.85, "redundant_pair"),
    (r"\btrue\s+and\s+accurate\b",      "accurate",  0.90, "redundant_pair"),
    (r"\bfinal\s+and\s+conclusive\b",   "final",     0.90, "redundant_pair"),
    (r"\bboth\s+alike\b",               "alike",     0.85, "redundant_pair"),
    (r"\bsum\s+total\b",                "total",     0.85, "redundant_pair"),
    (r"\bfuture\s+plans\b",             "plans",     0.80, "redundant_pair"),
    (r"\bpast\s+history\b",             "history",   0.90, "redundant_pair"),
    (r"\bunexpected\s+surprise\b",      "surprise",  0.90, "redundant_pair"),
    (r"\bfree\s+gift\b",                "gift",      0.90, "redundant_pair"),
    (r"\bclose\s+proximity\b",          "proximity", 0.85, "redundant_pair"),
    (r"\bbasic\s+fundamentals\b",       "basics",    0.85, "redundant_pair"),
    (r"\bend\s+result\b",               "result",    0.85, "redundant_pair"),
    (r"\bfinal\s+outcome\b",            "outcome",   0.85, "redundant_pair"),
    (r"\bnew\s+innovation\b",           "innovation",0.90, "redundant_pair"),
    (r"\badvance\s+planning\b",         "planning",  0.85, "redundant_pair"),
    (r"\bterrible\s+tragedy\b",         "tragedy",   0.85, "redundant_pair"),
    (r"\bforeseeable\s+future\b",       None,        0.65, "redundant_pair"),  # cliché

    # Weasel qualifiers
    (r"\bto\s+a\s+certain\s+extent\b",      None,  0.70, "weasel"),
    (r"\bin\s+some\s+ways?\b",              None,  0.65, "weasel"),
    (r"\bmore\s+or\s+less\b",               None,  0.70, "weasel"),
    (r"\bsomewhat\s+(?=\w)",                None,  0.55, "weasel"),
    (r"\brather\s+(?=\w)",                  None,  0.50, "weasel"),
    (r"\bfairly\s+(?=\w)",                  None,  0.50, "weasel"),
    (r"\bquite\s+(?=\w)",                   None,  0.50, "weasel"),
    (r"\bvery\s+unique\b",                  "unique", 0.90, "weasel"),
    (r"\babsolutely\s+essential\b",         "essential", 0.85, "weasel"),
    (r"\bcompletely\s+eliminate\b",         "eliminate", 0.80, "weasel"),
    (r"\btotally\s+destroy\b",              "destroy", 0.80, "weasel"),

    # Bloated comparatives
    (r"\ba\s+large\s+number\s+of\b",        "many",     0.85, "bloated"),
    (r"\bthe\s+vast\s+majority\s+of\b",     "most",     0.85, "bloated"),
    (r"\ba\s+majority\s+of\b",              "most",     0.75, "bloated"),
    (r"\ba\s+significant\s+number\s+of\b",  "many",     0.80, "bloated"),
    (r"\ba\s+wide\s+variety\s+of\b",        "various",  0.75, "bloated"),
    (r"\ba\s+wide\s+range\s+of\b",          "various",  0.75, "bloated"),
    (r"\bthe\s+majority\s+of\b",            "most",     0.70, "bloated"),
    (r"\bon\s+a\s+(?:daily|regular)\s+basis\b", "daily/regularly", 0.80, "bloated"),
    (r"\bfor\s+a\s+period\s+of\b",          None,       0.70, "bloated"),
    (r"\bof\s+a\s+(?:high|low)\s+quality\b","quality",  0.75, "bloated"),
    (r"\bin\s+a\s+(?:timely|prompt)\s+manner\b", "promptly", 0.80, "bloated"),
]


# ---------------------------------------------------------------------------
# Compile patterns once at import time
# ---------------------------------------------------------------------------

_COMPILED = [
    (re.compile(pat, re.IGNORECASE), sugg, sev, cat)
    for pat, sugg, sev, cat in _PATTERNS
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    flags: List[Dict[str, Any]] = []

    for regex, suggestion, base_sev, _cat in _COMPILED:
        for m in regex.finditer(text):
            matched = m.group()
            # Severity scales by how many words could be saved
            original_words = len(matched.split())
            saved_words    = original_words - (len(suggestion.split()) if suggestion else 0)
            sev = base_sev * min(1.0, max(0.3, saved_words / 5))

            if suggestion:
                msg = f"Wordy: consider '{suggestion}' instead"
            else:
                msg = "Delete: adds no meaning"

            s_byte = len(text[:m.start()].encode("utf-8"))
            e_byte = len(text[:m.end()].encode("utf-8"))
            sl, sc = byte_to_line_col(text, s_byte)
            _el, ec = byte_to_line_col(text, e_byte)

            flags.append(make_flag(sl, sc, ec, sev, msg))

    return {"flags": flags}
