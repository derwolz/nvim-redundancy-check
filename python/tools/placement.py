"""
python/tools/placement.py
Sentence placement checker for quill.nvim.

Detects sentences whose functional type (setting, action, dialogue, reflection,
description, transition) differs from the dominant type of their paragraph, then
suggests the nearest paragraph in the document where the sentence would fit better.

Modes
-----
fiction (default) — narrative prose signal lists
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from .shared import byte_to_line_col, make_flag


# ---------------------------------------------------------------------------
# Signal definitions per mode
# Each category has optional "words" (set) and "patterns" (list of regex str).
# Word hits score 2.0 each; pattern hits score 3.0 each.
# Final score is normalised by sentence word count.
# ---------------------------------------------------------------------------

_FICTION_SIGNALS: Dict[str, Dict] = {
    "setting": {
        "words": {
            "room", "street", "sky", "forest", "hill", "mountain", "valley",
            "field", "shore", "beach", "darkness", "light", "morning", "evening",
            "night", "dusk", "dawn", "sun", "moon", "stars", "wind", "rain",
            "snow", "fog", "mist", "heat", "cold", "shadow", "silence", "air",
            "ground", "floor", "wall", "ceiling", "door", "window", "tree",
            "river", "road", "path", "city", "town", "village", "house",
            "building", "stone", "grass", "leaves", "water", "horizon", "smoke",
            "fire", "earth", "land", "sea", "ocean", "cloud", "clouds", "bridge",
            "corridor", "hallway", "garden", "courtyard", "square", "alley",
            "canopy", "cliff", "coast", "desert", "dune", "glade", "harbor",
            "isle", "marsh", "meadow", "moor", "peak", "plain", "plateau",
            "ravine", "ridge", "shoreline", "slope", "summit", "swamp", "tundra",
        },
        "patterns": [
            r'\b(in|at|outside|inside|across|beneath|beyond|above|below|through|along)\s+the\b',
            r'\b(to\s+the\s+(north|south|east|west))\b',
            r'\b(stretche[sd]|loomed?|rose|spread)\b',
        ],
    },
    "action": {
        "words": {
            "ran", "run", "grabbed", "burst", "struck", "leapt", "leap", "fell",
            "rushed", "threw", "throw", "jumped", "jump", "hit", "pushed", "push",
            "pulled", "pull", "reached", "swung", "swing", "fired", "fire",
            "charged", "charge", "attacked", "attack", "escaped", "escape",
            "fought", "fight", "chased", "chase", "caught", "shot", "dropped",
            "drop", "lifted", "lift", "turned", "spun", "spin", "lunged", "lunge",
            "rolled", "roll", "fled", "flee", "stumbled", "staggered", "sprinted",
            "dove", "ducked", "slammed", "crashed", "tore", "ripped", "drove",
            "kicked", "punched", "blocked", "parried", "dodged", "seized",
            "hurled", "flung", "snapped", "bolted", "launched", "shoved",
            "wrestled", "scrambled", "vaulted", "snatched", "struck", "clashed",
        },
        "patterns": [],
    },
    "dialogue": {
        "words": {
            "said", "asked", "replied", "whispered", "shouted", "called",
            "answered", "muttered", "growled", "snapped", "declared", "announced",
            "told", "spoke", "talked", "cried", "laughed", "sighed", "gasped",
            "stammered", "stuttered", "murmured", "exclaimed", "insisted",
            "pleaded", "demanded", "agreed", "refused", "admitted", "confessed",
            "responded", "interrupted", "continued", "added", "began", "finished",
        },
        "patterns": [
            r'["""\u201c\u201d]',
            r"['''\u2018\u2019]",
        ],
    },
    "reflection": {
        "words": {
            "thought", "wonder", "wondered", "felt", "feel", "knew", "know",
            "realized", "realised", "remembered", "remember", "seemed", "appear",
            "appeared", "understood", "understand", "believed", "believe",
            "feared", "fear", "hoped", "hope", "imagined", "imagine", "decided",
            "decide", "considered", "consider", "wished", "wish", "doubted",
            "doubt", "sensed", "sense", "noticed", "notice", "expected", "expect",
            "assumed", "suppose", "supposed", "guessed", "guess", "recalled",
            "recall", "recognized", "recognised", "questioned", "pondered",
            "reflected", "mused", "reasoned", "concluded", "suspected", "regretted",
        },
        "patterns": [
            r'\b(he|she|they|it)\s+(thought|felt|knew|realized|wondered|remembered|sensed)\b',
        ],
    },
    "description": {
        "words": {
            "tall", "short", "dark", "pale", "bright", "soft", "hard", "rough",
            "smooth", "cold", "warm", "old", "young", "beautiful", "ugly",
            "small", "large", "thick", "thin", "heavy", "light", "quiet", "loud",
            "clean", "dirty", "sharp", "dull", "sweet", "bitter", "rich", "poor",
            "narrow", "wide", "deep", "shallow", "long", "slender", "massive",
            "tiny", "enormous", "ancient", "worn", "faded", "weathered", "gleaming",
            "golden", "silver", "grey", "gray", "black", "white", "amber",
            "scarlet", "crimson", "hollow", "jagged", "crooked", "twisted",
            "gaunt", "broad", "haggard", "lithe", "stocky", "wiry",
        },
        "patterns": [
            r'\b(was|were)\s+[a-z]+',
            r'\b(her|his|its|their)\s+[a-z]+\s+(was|were)\b',
        ],
    },
    "transition": {
        "words": {
            "meanwhile", "suddenly", "eventually", "later", "finally", "then",
            "next", "soon", "again", "once", "still", "already", "yet", "always",
            "never", "sometimes", "often", "afterward", "afterwards", "before",
            "after", "earlier", "previously", "subsequently", "immediately",
            "presently", "shortly", "briefly", "instantly", "thereafter",
            "meanwhile", "whereupon", "henceforth", "thenceforth",
        },
        "patterns": [
            r'\b(the\s+next\s+(day|morning|evening|night|moment|hour|week))\b',
            r'\b(a\s+(moment|while|second|minute|hour|day)\s+later)\b',
            r'\b(when\s+(he|she|they|it)\s+(arrived|returned|entered|left|woke))\b',
        ],
    },
}

MODES: Dict[str, Dict] = {
    "fiction": _FICTION_SIGNALS,
}

# Human-readable labels for messages
_CATEGORY_LABELS: Dict[str, str] = {
    "setting":     "scene-setting",
    "action":      "action",
    "dialogue":    "dialogue",
    "reflection":  "introspective",
    "description": "descriptive",
    "transition":  "transitional",
}


# ---------------------------------------------------------------------------
# Sentence scoring
# ---------------------------------------------------------------------------

def _score_sentence(text: str, signals: Dict) -> Dict[str, float]:
    lower = text.lower()
    words = re.findall(r'\b[a-z]+\b', lower)
    word_count = max(len(words), 1)
    word_set = set(words)

    scores: Dict[str, float] = {}
    for cat, sigs in signals.items():
        score = 0.0
        score += len(word_set & sigs.get("words", set())) * 2.0
        for pat in sigs.get("patterns", []):
            if re.search(pat, text, re.IGNORECASE):
                score += 3.0
        scores[cat] = score / word_count
    return scores


def _dominant(scores: Dict[str, float], min_score: float) -> Optional[str]:
    if not scores:
        return None
    best = max(scores, key=scores.__getitem__)
    if scores[best] < min_score:
        return None
    return best


# ---------------------------------------------------------------------------
# Paragraph / sentence splitting
# ---------------------------------------------------------------------------

def _split_paragraphs(text: str) -> List[Dict[str, Any]]:
    """Split text into paragraphs; for each, split into sentences with positions."""
    para_pattern = re.compile(r"\n\s*\n")
    bounds: List[Tuple[int, int]] = []
    cursor = 0
    for sep in para_pattern.finditer(text):
        bounds.append((cursor, sep.start()))
        cursor = sep.end()
    bounds.append((cursor, len(text)))

    paragraphs = []
    for char_start, char_end in bounds:
        para_text = text[char_start:char_end].strip()
        if not para_text:
            continue

        stripped_start = text.find(para_text, char_start)
        sentences = []
        for m in re.finditer(r"[^.!?\n]+[.!?]+|[^\n]+", para_text):
            raw = m.group()
            abs_char   = stripped_start + m.start()
            abs_char_e = stripped_start + m.end()
            s_byte = len(text[:abs_char].encode("utf-8"))
            e_byte = len(text[:abs_char_e].encode("utf-8"))
            sl, sc = byte_to_line_col(text, s_byte)
            _,  ec = byte_to_line_col(text, e_byte)
            sentences.append({
                "text":   raw,
                "s_line": sl,
                "s_col":  sc,
                "e_col":  ec,
            })

        if sentences:
            paragraphs.append({
                "sentences":  sentences,
                "first_line": sentences[0]["s_line"],
            })

    return paragraphs


# ---------------------------------------------------------------------------
# Nearest-paragraph search (radiates outward from current index)
# ---------------------------------------------------------------------------

def _find_nearest(
    paragraphs: List[Dict], current_idx: int, target_dom: str
) -> Optional[Dict]:
    n = len(paragraphs)
    for delta in range(1, n):
        for sign in (-1, 1):
            j = current_idx + sign * delta
            if 0 <= j < n and paragraphs[j].get("dominant") == target_dom:
                return paragraphs[j]
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    mode               = config.get("placement_mode", "fiction")
    min_score          = float(config.get("placement_min_score", 0.15))
    mismatch_threshold = float(config.get("placement_mismatch_threshold", 0.40))
    base_severity      = float(config.get("placement_severity", 0.55))

    signals = MODES.get(mode, MODES["fiction"])

    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return {"flags": [], "meta": {"mode": mode}}

    # Score every sentence and aggregate per paragraph
    for para in paragraphs:
        for sent in para["sentences"]:
            sent["scores"] = _score_sentence(sent["text"], signals)

        profile: Dict[str, float] = {}
        for sent in para["sentences"]:
            for cat, score in sent["scores"].items():
                profile[cat] = profile.get(cat, 0.0) + score
        n_sents = len(para["sentences"])
        para["profile"]  = {cat: v / n_sents for cat, v in profile.items()}
        para["dominant"] = _dominant(para["profile"], min_score)

    flags: List[Dict[str, Any]] = []
    grp_id = 0

    for i, para in enumerate(paragraphs):
        para_dom = para.get("dominant")
        # Need at least 2 sentences to establish paragraph context
        if para_dom is None or len(para["sentences"]) < 2:
            continue

        for sent in para["sentences"]:
            sent_dom = _dominant(sent["scores"], min_score)
            if sent_dom is None or sent_dom == para_dom:
                continue

            # Require a clear gap between the sentence's top category score
            # and the score it gets for the paragraph's dominant category
            sent_top       = sent["scores"].get(sent_dom, 0.0)
            sent_para_cat  = sent["scores"].get(para_dom, 0.0)
            if sent_top - sent_para_cat < mismatch_threshold:
                continue

            sev        = min(0.9, base_severity + (sent_top - sent_para_cat) * 0.4)
            sent_label = _CATEGORY_LABELS.get(sent_dom, sent_dom)
            para_label = _CATEGORY_LABELS.get(para_dom, para_dom)

            target = _find_nearest(paragraphs, i, sent_dom)

            if target is not None:
                target_line = target["first_line"] + 1  # 1-indexed for display
                msg = (
                    f"Misplaced {sent_label} sentence in a {para_label} paragraph"
                    f" — may fit better near line {target_line}"
                )
                t_sent = target["sentences"][0]
                flags.append(make_flag(
                    sent["s_line"], sent["s_col"], sent["e_col"],
                    sev, msg, group=grp_id,
                ))
                flags.append(make_flag(
                    t_sent["s_line"], t_sent["s_col"], t_sent["e_col"],
                    0.12,
                    f"Suggested destination for {sent_label} content"
                    f" (from line {sent['s_line'] + 1})",
                    group=grp_id,
                ))
                grp_id += 1
            else:
                msg = (
                    f"Misplaced {sent_label} sentence in a {para_label} paragraph"
                    f" — no nearby {sent_label} section found"
                )
                flags.append(make_flag(
                    sent["s_line"], sent["s_col"], sent["e_col"], sev, msg,
                ))

    return {"flags": flags, "meta": {"mode": mode}}
