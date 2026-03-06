"""
python/tools/entity.py
Entity consistency checker for quill.nvim.

Detects proper nouns and clusters near-duplicate forms using SequenceMatcher
(same greedy-seeding pattern as redundancy.py). Groups with ≥ 2 distinct forms
are flagged so cursor hover blue-highlights the whole entity family.
"""

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Dict, List, Tuple

from .shared import byte_to_line_col, make_flag


# ---------------------------------------------------------------------------
# Proper-noun detection
# ---------------------------------------------------------------------------

# Matches capitalised tokens (2+ chars) that may include internal dots (e.g. U.S.)
_PROPER_RE = re.compile(
    r"\b([A-Z][a-z]{1,}(?:\.[A-Z]\.)*(?:[A-Z][a-z]*)?)\b"
)


def _extract_entities(text: str) -> List[Dict[str, Any]]:
    """
    Return list of {form, s_line, s_col, e_col} for every proper-noun token,
    excluding sentence-start positions (where capitalisation is grammatical).
    """
    entities = []
    for m in _PROPER_RE.finditer(text):
        # Check if this is a sentence-start capital
        prefix = text[:m.start()].rstrip()
        if not prefix or prefix[-1] in ".!?":
            continue  # sentence-start — skip

        form   = m.group(1)
        s_byte = len(text[:m.start()].encode("utf-8"))
        e_byte = len(text[:m.end()].encode("utf-8"))
        sl, sc = byte_to_line_col(text, s_byte)
        _,  ec = byte_to_line_col(text, e_byte)
        entities.append({"form": form, "s_line": sl, "s_col": sc, "e_col": ec})
    return entities


# ---------------------------------------------------------------------------
# SequenceMatcher similarity (same helper as redundancy.py)
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ---------------------------------------------------------------------------
# Greedy clustering
# ---------------------------------------------------------------------------

def _cluster(forms: List[str], threshold: float) -> List[List[int]]:
    """
    Greedy seed-and-assign clustering of form indices.
    Returns list of clusters, each a list of indices into `forms`.
    """
    assigned = [-1] * len(forms)
    clusters: List[List[int]] = []

    for i, form in enumerate(forms):
        if assigned[i] != -1:
            continue
        cluster_idx = len(clusters)
        clusters.append([i])
        assigned[i] = cluster_idx
        for j in range(i + 1, len(forms)):
            if assigned[j] != -1:
                continue
            if _similarity(form, forms[j]) >= threshold:
                clusters[cluster_idx].append(j)
                assigned[j] = cluster_idx

    return clusters


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    entity_similarity = float(config.get("entity_similarity", 0.72))
    entity_min_count  = int(config.get("entity_min_count", 2))

    entities = _extract_entities(text)
    if not entities:
        return {"flags": []}

    # Unique forms for clustering
    unique_forms = list(dict.fromkeys(e["form"] for e in entities))
    clusters = _cluster(unique_forms, entity_similarity)

    flags: List[Dict[str, Any]] = []
    grp_id = 0

    for cluster in clusters:
        if len(cluster) < entity_min_count:
            continue  # only one form variant — consistent

        forms_in_cluster = [unique_forms[idx] for idx in cluster]

        # Count occurrences of each form
        counts = Counter(e["form"] for e in entities if e["form"] in forms_in_cluster)
        majority_form = counts.most_common(1)[0][0]
        majority_count = counts[majority_form]

        for occ in entities:
            if occ["form"] not in forms_in_cluster:
                continue
            is_minority = occ["form"] != majority_form
            if is_minority:
                msg = (
                    f"Inconsistent entity spelling: '{occ['form']}' "
                    f"vs '{majority_form}' (used {majority_count}\u00d7)"
                )
            else:
                msg = f"Entity has inconsistent spelling elsewhere"
            flags.append(make_flag(
                occ["s_line"], occ["s_col"], occ["e_col"],
                0.65,
                msg,
                group=grp_id,
            ))

        grp_id += 1

    return {"flags": flags}
