"""
python/tools/coherence.py
Paragraph coherence checker for quill.nvim.

Two checks per paragraph:
  1. Orphan paragraphs: non-first paragraphs with only one sentence.
  2. Topic drift: body sentences whose content-word overlap with the topic
     sentence (first sentence of the paragraph) is below min_overlap.
"""

import re
from typing import Any, Dict, List, Set

from .shared import byte_to_line_col, make_flag


# ---------------------------------------------------------------------------
# Stoplist (~35 common function words)
# ---------------------------------------------------------------------------

_STOPLIST: Set[str] = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "day", "get", "has", "him", "his",
    "how", "its", "may", "now", "own", "see", "two", "who", "did", "she",
    "that", "this", "they", "with", "from", "have", "been", "were", "what",
}


def _content_words(sentence_text: str) -> Set[str]:
    words = re.findall(r"[a-zA-Z]+", sentence_text.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPLIST}


# ---------------------------------------------------------------------------
# Sentence splitter (local copy)
# ---------------------------------------------------------------------------

def _split_sentences_in(para_text: str, para_byte_start: int) -> List[Dict[str, Any]]:
    sentences = []
    for m in re.finditer(r"[^.!?]+[.!?]+", para_text):
        raw    = m.group()
        abs_s  = para_byte_start + len(para_text[:m.start()].encode("utf-8"))
        abs_e  = para_byte_start + len(para_text[:m.end()].encode("utf-8"))

        # We need the full text to do byte_to_line_col, but we only have the
        # para. Store abs byte offsets and resolve later.
        sentences.append({
            "text":    raw,
            "abs_s":   abs_s,
            "abs_e":   abs_e,
        })
    return sentences


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    min_overlap        = float(config.get("min_overlap", 0.30))
    flag_orphans       = bool(config.get("flag_orphan_paragraphs", True))
    orphan_severity    = float(config.get("orphan_severity", 0.35))

    # Split text into paragraphs (blank-line separated)
    para_pattern = re.compile(r"\n\s*\n")
    para_bounds: List[tuple] = []
    cursor = 0
    for sep in para_pattern.finditer(text):
        para_bounds.append((cursor, sep.start()))
        cursor = sep.end()
    para_bounds.append((cursor, len(text)))

    flags: List[Dict[str, Any]] = []

    full_bytes = text.encode("utf-8")

    def _resolve(abs_byte: int):
        chunk = full_bytes[:abs_byte]
        lines = chunk.split(b"\n")
        return len(lines) - 1, len(lines[-1])

    for para_idx, (char_start, char_end) in enumerate(para_bounds):
        para_text = text[char_start:char_end].strip()
        if not para_text:
            continue

        # Byte offset of the stripped para start within `text`
        stripped_start = text.find(para_text, char_start)
        para_byte_start = len(text[:stripped_start].encode("utf-8"))

        sentences = _split_sentences_in(para_text, para_byte_start)
        if not sentences:
            continue

        n_sents = len(sentences)

        # ------------------------------------------------------------------
        # Check 1: Orphan paragraph
        # ------------------------------------------------------------------
        if flag_orphans and para_idx > 0 and n_sents == 1:
            sl, sc = _resolve(sentences[0]["abs_s"])
            _, ec  = _resolve(sentences[0]["abs_e"])
            flags.append(make_flag(sl, sc, ec, orphan_severity,
                                   "Orphan paragraph: single-sentence non-opening paragraph"))
            continue  # no topic-drift check for single-sentence para

        if n_sents < 2:
            continue

        # ------------------------------------------------------------------
        # Check 2: Topic drift
        # ------------------------------------------------------------------
        topic_words = _content_words(sentences[0]["text"])
        if not topic_words:
            continue

        for sent in sentences[1:]:
            body_words = _content_words(sent["text"])
            if not body_words:
                continue
            overlap = len(topic_words & body_words) / len(topic_words)
            if overlap < min_overlap:
                sev = max(0.3, 0.9 - overlap)
                msg = (
                    f"Possible topic drift: sentence shares "
                    f"{overlap:.0%} content words with paragraph opener"
                )
                sl, sc = _resolve(sent["abs_s"])
                _, ec  = _resolve(sent["abs_e"])
                flags.append(make_flag(sl, sc, ec, sev, msg))

    return {"flags": flags}
