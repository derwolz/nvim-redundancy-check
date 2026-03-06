"""
python/tools/register.py
Register consistency checker for quill.nvim.

Detects when informal words appear in a formal document, or when
academic/formal vocabulary appears in an informal piece.
"""

import re
from typing import Any, Dict, List, Set

from .shared import byte_to_line_col, make_flag


# ---------------------------------------------------------------------------
# Word lists
# ---------------------------------------------------------------------------

INFORMAL: Set[str] = {
    # Contractions & shortenings
    "gonna", "wanna", "kinda", "sorta", "gotta", "hafta", "shoulda",
    "coulda", "woulda", "dunno", "lemme", "gimme", "lotta", "oughta",
    # Casual interjections
    "yeah", "yep", "nope", "nah", "ok", "okay", "yup",
    "wow", "gosh", "golly", "hmm", "oops", "whoa", "hey",
    # Informal nouns / adjectives
    "stuff", "things", "folks", "guys", "kids", "lots", "tons",
    "bucks", "bud", "pal", "buddy", "dude", "gal", "chap", "mate",
    "awesome", "cool", "neat", "rad", "epic", "super", "mega",
    "amazing", "awesome", "terrible", "horrible", "sucks", "lousy",
    "fella", "fellas", "y'all", "yall",
    # Intensifiers / fillers
    "literally", "basically", "honestly", "actually", "totally",
    "seriously", "definitely", "absolutely", "obviously", "clearly",
    "like", "just", "really", "very", "pretty", "quite",
    # Informal verbs
    "gonna", "wanna", "grab", "snag", "chat", "hang", "chill",
    "freak", "freak out", "blow up", "mess up", "screw up",
    "check out", "kick off", "wrap up",
    # Internet/modern informal
    "selfie", "tweet", "post", "blog", "vibe", "vlog",
    "dm", "lol", "omg", "btw", "fyi", "imo", "tbh",
    # More
    "heck", "darn", "dang", "crud", "crap",
    "big deal", "no big deal", "whatsoever", "whatnot",
}

FORMAL_MARKERS: Set[str] = {
    # Conjunctive adverbs
    "furthermore", "moreover", "nevertheless", "nonetheless", "however",
    "therefore", "consequently", "accordingly", "subsequently", "henceforth",
    "heretofore", "hereafter", "herein", "therein", "thereupon",
    # Legal / bureaucratic
    "aforementioned", "aforesaid", "notwithstanding", "pursuant",
    "whereas", "wherefore", "heretofore", "herewith", "therewith",
    "inasmuch", "insofar", "heretofore", "vis-a-vis",
    # Academic / formal vocabulary
    "utilize", "utilise", "endeavour", "endeavor", "commence",
    "facilitate", "ascertain", "demonstrate", "illustrate", "elucidate",
    "promulgate", "disseminate", "enumerate", "delineate",
    "corroborate", "substantiate", "ascertain", "constitute",
    "predominantly", "subsequently", "approximately", "accordingly",
    "pertaining", "regarding", "concerning", "respecting",
    "implementation", "methodology", "framework", "paradigm",
    "conceptualise", "conceptualize", "synthesise", "synthesize",
    "amongst", "whilst", "hence", "thus", "thereby", "whereby",
    "prima facie", "inter alia", "sui generis", "de facto",
    # Formal verbs
    "ameliorate", "mitigate", "obviate", "preclude", "necessitate",
    "engender", "exacerbate", "circumvent", "expunge", "adjudicate",
    "deliberate", "mandate", "stipulate", "promulgate",
}


# ---------------------------------------------------------------------------
# Tokenise for register (simple word boundaries)
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"\b[a-zA-Z']+\b")


def _register_tokens(text: str) -> List[Dict[str, Any]]:
    tokens = []
    for m in _WORD_RE.finditer(text):
        word = m.group().lower().strip("'")
        if len(word) < 2:
            continue
        s_byte = len(text[:m.start()].encode("utf-8"))
        e_byte = len(text[:m.end()].encode("utf-8"))
        sl, sc = byte_to_line_col(text, s_byte)
        _el, ec = byte_to_line_col(text, e_byte)
        tokens.append({
            "word":   word,
            "raw":    m.group(),
            "s_line": sl,
            "s_col":  sc,
            "e_col":  ec,
        })
    return tokens


# ---------------------------------------------------------------------------
# Informality score for a word (0.0–1.0)
# Slang / internet terms score higher than casual intensifiers.
# ---------------------------------------------------------------------------

_HIGH_INFORMAL = {
    "gonna", "wanna", "kinda", "sorta", "gotta", "dunno", "hafta",
    "lol", "omg", "btw", "fyi", "imo", "tbh", "dm", "y'all", "yall",
}


def _informality_score(word: str) -> float:
    if word in _HIGH_INFORMAL:
        return 1.0
    return 0.6  # average informal word


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    informal_threshold = float(config.get("informal_threshold", 0.005))
    formal_threshold   = float(config.get("formal_threshold",   0.001))
    informal_doc_ratio = float(config.get("informal_doc_ratio", 0.02))

    tokens = _register_tokens(text)
    if not tokens:
        return {"flags": []}

    total = len(tokens)

    informal_hits = [(t, _informality_score(t["word"]))
                     for t in tokens if t["word"] in INFORMAL]
    formal_hits   = [t for t in tokens if t["word"] in FORMAL_MARKERS]

    informal_ratio = len(informal_hits) / total
    formal_ratio   = len(formal_hits)   / total

    flags: List[Dict[str, Any]] = []

    # Formal document: effectively no informal words, but formal markers present
    if informal_ratio < informal_threshold and formal_ratio > formal_threshold:
        for t, info_score in informal_hits:
            sev = min(1.0, 0.7 + 0.3 * info_score)
            msg = f"Informal word in formal document: '{t['raw']}'"
            flags.append(make_flag(t["s_line"], t["s_col"], t["e_col"], sev, msg))

    # Informal document: lots of informal markers
    elif informal_ratio > informal_doc_ratio:
        for t in formal_hits:
            msg = f"Academic register in informal text: '{t['raw']}'"
            flags.append(make_flag(t["s_line"], t["s_col"], t["e_col"], 0.5, msg))

    # Neutral: no flags

    return {"flags": flags}
