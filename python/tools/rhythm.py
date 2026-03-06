"""
python/tools/rhythm.py
Rhythm & readability checker for quill.nvim.

Flags:
  - Runs of 3+ sentences with similar word counts (monotonous rhythm)
  - Sentences that are very long or lexically complex
Also computes Flesch-Kincaid Reading Ease in meta.
"""

import re
from typing import Any, Dict, List, Tuple

from .shared import byte_to_line_col, make_flag


# ---------------------------------------------------------------------------
# Syllable counting (vowel-group heuristic)
# ---------------------------------------------------------------------------

_VOWELS = re.compile(r"[aeiouAEIOU]+")
_SILENT_E = re.compile(r"[^aeiouAEIOU]e$", re.IGNORECASE)


def _count_syllables(word: str) -> int:
    count = len(_VOWELS.findall(word))
    # Silent trailing -e drops one syllable when it's not the only vowel group
    if _SILENT_E.search(word) and count > 1:
        count -= 1
    return max(1, count)


# ---------------------------------------------------------------------------
# Sentence splitting with byte positions
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> List[Dict[str, Any]]:
    """
    Return list of dicts:
      { text, s_byte, e_byte, s_line, s_col, e_line, e_col }
    """
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
        })
    return sentences


# ---------------------------------------------------------------------------
# Per-sentence stats
# ---------------------------------------------------------------------------

def _sentence_stats(sent_text: str) -> Tuple[int, float]:
    """Return (word_count, avg_syllables_per_word)."""
    words = re.findall(r"[a-zA-Z']+", sent_text)
    words = [w.strip("'") for w in words if len(w.strip("'")) >= 2]
    if not words:
        return 0, 0.0
    syl_count = sum(_count_syllables(w) for w in words)
    return len(words), syl_count / len(words)


# ---------------------------------------------------------------------------
# Flesch-Kincaid Reading Ease
# ---------------------------------------------------------------------------

def _flesch_kincaid(sentences: List[Dict[str, Any]]) -> float:
    total_words = 0
    total_syl   = 0
    for s in sentences:
        wc, avg_syl = _sentence_stats(s["text"])
        total_words += wc
        total_syl   += int(avg_syl * wc)
    n_sent = len(sentences)
    if n_sent == 0 or total_words == 0:
        return 0.0
    asl = total_words / n_sent           # avg sentence length
    asw = total_syl   / total_words      # avg syllables per word
    return 206.835 - 1.015 * asl - 84.6 * asw


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    monotony_run   = int(config.get("monotony_run", 3))
    monotony_delta = int(config.get("monotony_delta", 2))
    long_words     = int(config.get("long_sentence_words", 40))
    complex_syl    = float(config.get("complex_syllables", 2.5))

    sentences = _split_sentences(text)
    if not sentences:
        return {"flags": [], "meta": {"readability": 0.0}}

    # Compute stats per sentence
    stats = []
    for s in sentences:
        wc, avg_syl = _sentence_stats(s["text"])
        stats.append((wc, avg_syl))

    flags: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Monotony: runs of 3+ sentences within ±monotony_delta words
    # ------------------------------------------------------------------
    i = 0
    while i < len(sentences):
        run = [i]
        j   = i + 1
        while j < len(sentences):
            ref_wc = stats[i][0]
            cur_wc = stats[j][0]
            if abs(cur_wc - ref_wc) <= monotony_delta:
                run.append(j)
                j += 1
            else:
                break

        if len(run) >= monotony_run:
            avg_wc = sum(stats[k][0] for k in run) / len(run)
            sev    = min(1.0, 0.5 + 0.1 * (len(run) - monotony_run))
            msg    = (f"Run of similar-length sentences "
                      f"({len(run)} in a row, ~{avg_wc:.0f} words each)")
            for k in run:
                s = sentences[k]
                flags.append(make_flag(s["s_line"], s["s_col"], s["e_col"], sev, msg))
            i = run[-1] + 1
        else:
            i += 1

    # ------------------------------------------------------------------
    # Complexity: long or lexically dense sentences
    # ------------------------------------------------------------------
    for idx, s in enumerate(sentences):
        wc, avg_syl = stats[idx]
        if wc == 0:
            continue
        long_flag    = wc > long_words
        complex_flag = avg_syl > complex_syl
        if long_flag or complex_flag:
            sev = min(1.0, (wc / long_words) * 0.8) if long_flag else 0.6
            msg = f"Long complex sentence ({wc} words, avg {avg_syl:.1f} syl/word)"
            flags.append(make_flag(s["s_line"], s["s_col"], s["e_col"], sev, msg))

    fk = _flesch_kincaid(sentences)

    return {
        "flags": flags,
        "meta":  {"readability": round(fk, 1)},
    }
