"""
python/tools/semantic.py
Semantic pleonasm detector for quill.nvim.

Finds modifier+head pairs where one word's meaning is already contained in
the other.  Examples: "inching slowly", "ascend up", "merge together",
"dead corpse", "completely destroy".

Each match produces TWO flag entries sharing the same `group` id — one for
each word in the pair — so the cursor handler can blue-highlight both.
"""

import re
from typing import Any, Dict, FrozenSet, List, Set, Tuple

from .shared import build_positions, make_flag


# ---------------------------------------------------------------------------
# Pleonasm pair table
# Each entry: (set_a, set_b, max_gap, severity, note)
#   set_a / set_b  – frozensets of lowercased word forms (inflected)
#   max_gap        – max tokens that may appear between the two words
#   severity       – 0.0–1.0
#   note           – human-readable reason; used in the flag message
#
# Order is NOT enforced: a match fires if either word precedes the other
# within max_gap positions.  This catches both "inching slowly" and
# "slowly inched".
# ---------------------------------------------------------------------------

def _fs(*words: str) -> FrozenSet[str]:
    return frozenset(words)


_SLOW_VERBS = _fs(
    "inch", "inched", "inching", "inches",
    "crawl", "crawled", "crawling", "crawls",
    "creep", "crept", "creeping", "creeps",
    "trudge", "trudged", "trudging", "trudges",
    "plod", "plodded", "plodding", "plods",
    "shuffle", "shuffled", "shuffling", "shuffles",
    "slog", "slogged", "slogging", "slogs",
    "lumber", "lumbered", "lumbering", "lumbers",
    "shamble", "shambled", "shambling", "shambles",
    "hobble", "hobbled", "hobbling", "hobbles",
    "limp", "limped", "limping", "limps",
    "dawdle", "dawdled", "dawdling", "dawdles",
    "amble", "ambled", "ambling", "ambles",
    "saunter", "sauntered", "sauntering", "saunters",
    "stroll", "strolled", "strolling", "strolls",
    "meander", "meandered", "meandering", "meanders",
    "linger", "lingered", "lingering", "lingers",
    "lag", "lagged", "lagging", "lags",
    "totter", "tottered", "tottering", "totters",
)

_SLOW_ADVS = _fs(
    "slowly", "sluggishly", "leisurely", "languidly",
    "unhurriedly", "lazily", "gradually",
)

_FAST_VERBS = _fs(
    "sprint", "sprinted", "sprinting", "sprints",
    "dash", "dashed", "dashing", "dashes",
    "bolt", "bolted", "bolting", "bolts",
    "hurtle", "hurtled", "hurtling", "hurtles",
    "zoom", "zoomed", "zooming", "zooms",
    "zip", "zipped", "zipping", "zips",
    "race", "raced", "racing", "races",
    "rush", "rushed", "rushing", "rushes",
    "barrel", "barreled", "barrelled", "barreling", "barrelling", "barrels",
    "careen", "careened", "careening", "careens",
    "streak", "streaked", "streaking", "streaks",
    "whiz", "whizzed", "whizzing", "whizzes",
    "gallop", "galloped", "galloping", "gallops",
    "tear", "tore", "tearing",           # tear = move fast
    "fly", "flew", "flown", "flying", "flies",
)

_FAST_ADVS = _fs(
    "quickly", "rapidly", "swiftly", "speedily",
    "hastily", "briskly", "nimbly",
)

_QUIET_VERBS = _fs(
    "whisper", "whispered", "whispering", "whispers",
    "murmur", "murmured", "murmuring", "murmurs",
    "mumble", "mumbled", "mumbling", "mumbles",
    "mutter", "muttered", "muttering", "mutters",
    "hiss", "hissed", "hissing", "hisses",
    "sigh", "sighed", "sighing", "sighs",
    "rustle", "rustled", "rustling", "rustles",
    "tiptoe", "tiptoed", "tiptoeing", "tiptoes",
    "sneak", "sneaked", "sneaking", "sneaks", "snuck",
    "slink", "slunk", "slinking", "slinks",
    "glide", "glided", "gliding", "glides",
)

_QUIET_ADVS = _fs(
    "quietly", "softly", "silently", "mutely",
    "inaudibly", "stealthily", "noiselessly", "soundlessly",
)

_LOUD_VERBS = _fs(
    "shout", "shouted", "shouting", "shouts",
    "scream", "screamed", "screaming", "screams",
    "yell", "yelled", "yelling", "yells",
    "roar", "roared", "roaring", "roars",
    "bellow", "bellowed", "bellowing", "bellows",
    "howl", "howled", "howling", "howls",
    "shriek", "shrieked", "shrieking", "shrieks",
    "screech", "screeched", "screeching", "screeches",
    "boom", "boomed", "booming", "booms",
    "holler", "hollered", "hollering", "hollers",
    "blare", "blared", "blaring", "blares",
    "thunder", "thundered", "thundering", "thunders",
)

_LOUD_ADVS = _fs(
    "loudly", "noisily", "deafeningly", "boisterously",
)

_SAD_VERBS = _fs(
    "sob", "sobbed", "sobbing", "sobs",
    "weep", "wept", "weeping", "weeps",
    "cry", "cried", "crying", "cries",
    "mourn", "mourned", "mourning", "mourns",
    "grieve", "grieved", "grieving", "grieves",
    "lament", "lamented", "lamenting", "laments",
    "wail", "wailed", "wailing", "wails",
    "whimper", "whimpered", "whimpering", "whimpers",
    "mope", "moped", "moping", "mopes",
    "brood", "brooded", "brooding", "broods",
    "sulk", "sulked", "sulking", "sulks",
)

_SAD_ADVS = _fs(
    "sadly", "mournfully", "sorrowfully", "tearfully",
    "woefully", "dejectedly", "despondently", "forlornly",
)

_HAPPY_VERBS = _fs(
    "grin", "grinned", "grinning", "grins",
    "beam", "beamed", "beaming", "beams",
    "chuckle", "chuckled", "chuckling", "chuckles",
    "giggle", "giggled", "giggling", "giggles",
    "laugh", "laughed", "laughing", "laughs",
    "chortle", "chortled", "chortling", "chortles",
    "rejoice", "rejoiced", "rejoicing", "rejoices",
    "celebrate", "celebrated", "celebrating", "celebrates",
)

_HAPPY_ADVS = _fs(
    "happily", "joyfully", "gleefully", "merrily",
    "cheerfully", "delightedly", "jubilantly", "blissfully",
)

_ANGRY_VERBS = _fs(
    "glare", "glared", "glaring", "glares",
    "seethe", "seethed", "seething", "seethes",
    "fume", "fumed", "fuming", "fumes",
    "rage", "raged", "raging", "rages",
    "snarl", "snarled", "snarling", "snarls",
    "scowl", "scowled", "scowling", "scowls",
    "growl", "growled", "growling", "growls",
    "snap", "snapped", "snapping", "snaps",
    "storm", "stormed", "storming", "storms",
    "bristle", "bristled", "bristling", "bristles",
    "smoulder", "smouldered", "smouldering",
    "smolder", "smoldered", "smoldering",
)

_ANGRY_ADVS = _fs(
    "angrily", "furiously", "wrathfully", "indignantly",
    "irritably", "bitterly", "icily",
)

# Absolute verbs whose meaning is total — intensifiers add nothing
_ABS_VERBS = _fs(
    "destroy", "destroyed", "destroying", "destroys",
    "annihilate", "annihilated", "annihilating", "annihilates",
    "obliterate", "obliterated", "obliterating", "obliterates",
    "eradicate", "eradicated", "eradicating", "eradicates",
    "eliminate", "eliminated", "eliminating", "eliminates",
    "demolish", "demolished", "demolishing", "demolishes",
    "erase", "erased", "erasing", "erases",
    "exterminate", "exterminated", "exterminating", "exterminates",
    "extinguish", "extinguished", "extinguishing", "extinguishes",
    "vaporize", "vaporized", "vaporizing", "vaporizes",
    "vaporise", "vaporised", "vaporising", "vaporises",
    "finish", "finished", "finishing", "finishes",
    "complete", "completed", "completing", "completes",
    "conclude", "concluded", "concluding", "concludes",
    "exhaust", "exhausted", "exhausting", "exhausts",
    "deplete", "depleted", "depleting", "depletes",
    "devour", "devoured", "devouring", "devours",
    "engulf", "engulfed", "engulfing", "engulfs",
    "permeate", "permeated", "permeating", "permeates",
    "saturate", "saturated", "saturating", "saturates",
    "overwhelm", "overwhelmed", "overwhelming", "overwhelms",
)

_TOTAL_ADVS = _fs(
    "completely", "totally", "entirely", "utterly",
    "absolutely", "wholly", "thoroughly", "perfectly", "fully",
)

# Absolute adjectives that admit no degree
_ABS_ADJS = _fs(
    "unique", "perfect", "universal", "infinite", "eternal",
    "immortal", "unanimous", "absolute", "impossible", "omniscient",
    "omnipotent", "pristine", "flawless", "countless", "limitless",
    "endless", "boundless", "ceaseless", "timeless", "ageless",
    "peerless", "matchless", "incomparable", "inimitable",
    "invincible", "indestructible", "infallible", "impeccable",
)

_DEGREE_MODS = _fs(
    "very", "more", "most", "quite", "rather", "somewhat",
    "fairly", "extremely", "incredibly", "exceptionally",
)

# (verb_forms, particle, severity, note) for directional/reversal particles
_DIRECTIONAL: List[Tuple[FrozenSet[str], str, float, str]] = [
    (_fs("ascend","ascended","ascending","ascends"),   "up",
     0.85, "'ascend' already means 'go up'"),
    (_fs("descend","descended","descending","descends"), "down",
     0.85, "'descend' already means 'go down'"),
    (_fs("rise","rose","risen","rising","rises"),       "up",
     0.75, "'rise' already means 'go up'"),
    (_fs("sink","sank","sunk","sinking","sinks"),       "down",
     0.75, "'sink' already means 'go down'"),
    (_fs("fall","fell","fallen","falling","falls"),     "down",
     0.70, "'fall' already means 'go down'"),
    (_fs("plummet","plummeted","plummeting","plummets"), "down",
     0.80, "'plummet' already means 'fall rapidly downward'"),
    (_fs("plunge","plunged","plunging","plunges"),      "down",
     0.75, "'plunge' implies downward movement"),
    (_fs("drop","dropped","dropping","drops"),          "down",
     0.65, "'drop' implies downward"),
    (_fs("return","returned","returning","returns"),    "back",
     0.85, "'return' already means 'go back'"),
    (_fs("revert","reverted","reverting","reverts"),    "back",
     0.90, "'revert' already means 'go back to a previous state'"),
    (_fs("retreat","retreated","retreating","retreats"), "back",
     0.85, "'retreat' already means 'go back/away'"),
    (_fs("recede","receded","receding","recedes"),      "back",
     0.85, "'recede' already means 'move back'"),
    (_fs("rebound","rebounded","rebounding","rebounds"), "back",
     0.85, "'rebound' already means 'bounce back'"),
    (_fs("reply","replied","replying","replies"),       "back",
     0.80, "'reply' already means 'respond'"),
    (_fs("respond","responded","responding","responds"), "back",
     0.75, "'respond' already implies answering"),
    (_fs("repeat","repeated","repeating","repeats"),    "again",
     0.90, "'repeat' already means 'do again'"),
    (_fs("recur","recurred","recurring","recurs"),      "again",
     0.90, "'recur' already means 'happen again'"),
    (_fs("advance","advanced","advancing","advances"),  "forward",
     0.80, "'advance' already means 'go forward'"),
    (_fs("proceed","proceeded","proceeding","proceeds"), "forward",
     0.80, "'proceed' already means 'go forward'"),
    (_fs("progress","progressed","progressing","progresses"), "forward",
     0.75, "'progress' implies moving forward"),
    (_fs("circle","circled","circling","circles"),      "around",
     0.85, "'circle' already implies going around"),
    (_fs("surround","surrounded","surrounding","surrounds"), "around",
     0.80, "'surround' already implies encircling"),
    (_fs("revolve","revolved","revolving","revolves"),  "around",
     0.80, "'revolve' means going around"),
    (_fs("enter","entered","entering","enters"),        "into",
     0.80, "'enter' already means 'go into'"),
    (_fs("penetrate","penetrated","penetrating","penetrates"), "into",
     0.85, "'penetrate' already means 'go into'"),
    (_fs("exit","exited","exiting","exits"),            "out",
     0.80, "'exit' already means 'go out'"),
    (_fs("emerge","emerged","emerging","emerges"),      "out",
     0.70, "'emerge' implies coming out"),
    (_fs("withdraw","withdrew","withdrawn","withdrawing","withdraws"), "back",
     0.75, "'withdraw' implies pulling back"),
    (_fs("shrink","shrank","shrunk","shrinking","shrinks"), "down",
     0.70, "'shrink' implies reduction"),
    (_fs("reduce","reduced","reducing","reduces"),      "down",
     0.60, "'reduce' already implies decrease"),
]

# Verbs that imply togetherness — "together" adds nothing
_TOGETHER_VERBS = _fs(
    "merge", "merged", "merging", "merges",
    "combine", "combined", "combining", "combines",
    "join", "joined", "joining", "joins",
    "unite", "united", "uniting", "unites",
    "gather", "gathered", "gathering", "gathers",
    "assemble", "assembled", "assembling", "assembles",
    "consolidate", "consolidated", "consolidating", "consolidates",
    "integrate", "integrated", "integrating", "integrates",
    "converge", "converged", "converging", "converges",
    "mingle", "mingled", "mingling", "mingles",
    "blend", "blended", "blending", "blends",
    "fuse", "fused", "fusing", "fuses",
    "collaborate", "collaborated", "collaborating", "collaborates",
    "cooperate", "cooperated", "cooperating", "cooperates",
    "pool", "pooled", "pooling", "pools",
    "mix", "mixed", "mixing", "mixes",
    "link", "linked", "linking", "links",
    "connect", "connected", "connecting", "connects",
    "couple", "coupled", "coupling", "couples",
    "bind", "bound", "binding", "binds",
)

# Noun → set of adjectives that are redundant (adj appears before noun
# in natural prose, but we flag both orders for predicative forms too)
_NOUN_PLEONASMS: List[Tuple[FrozenSet[str], FrozenSet[str], float, str]] = [
    (_fs("circle","circles"),
     _fs("round","circular"),
     0.90, "circles are round by definition"),
    (_fs("corpse","corpses","cadaver","cadavers","carcass","carcasses"),
     _fs("dead","lifeless","deceased"),
     0.95, "a corpse is already dead"),
    (_fs("tundra"),
     _fs("frozen","icy","cold","frigid"),
     0.80, "tundra is permanently frozen by definition"),
    (_fs("desert","deserts"),
     _fs("dry","arid","barren","parched"),
     0.80, "deserts are arid by definition"),
    (_fs("fire","fires","flame","flames","blaze","blazes","inferno","infernos"),
     _fs("hot","burning","blazing","searing","scorching"),
     0.85, "fire is hot by definition"),
    (_fs("ice","glacier","glaciers","icicle","icicles","iceberg","icebergs"),
     _fs("cold","frozen","icy","frigid","freezing"),
     0.85, "ice is frozen by definition"),
    (_fs("shadow","shadows","darkness","shade"),
     _fs("dark","shadowy","dim"),
     0.75, "shadows are dark by definition"),
    (_fs("blizzard","blizzards"),
     _fs("cold","icy","freezing","snowy","frigid"),
     0.80, "blizzards are freezing by definition"),
    (_fs("infant","infants","newborn","newborns","baby","babies","toddler","toddlers"),
     _fs("young","tiny","little","small","new"),
     0.80, "infants are already young/small"),
    (_fs("veteran","veterans"),
     _fs("experienced","seasoned","longtime","long-time"),
     0.70, "veterans are experienced by definition"),
    (_fs("ruin","ruins","wreckage"),
     _fs("crumbled","crumbling","dilapidated","derelict"),
     0.75, "ruins are already crumbled"),
    (_fs("antique","antiques","relic","relics","artifact","artifacts","artefact","artefacts"),
     _fs("old","ancient","aged"),
     0.85, "antiques are already old"),
    (_fs("forecast","forecasts","prediction","predictions","prophecy","prophecies"),
     _fs("future","upcoming","forthcoming"),
     0.85, "forecasts are by definition about the future"),
    (_fs("corpse","corpses","cadaver","cadavers"),
     _fs("dead","lifeless"),
     0.95, "a corpse is already dead"),
    (_fs("fact","facts"),
     _fs("true","actual","real","genuine"),
     0.90, "facts are true by definition"),
    (_fs("consensus"),
     _fs("general","mutual","common","collective","universal"),
     0.80, "consensus already implies general agreement"),
    (_fs("monopoly","monopolies"),
     _fs("sole","exclusive","complete","total"),
     0.80, "a monopoly is already exclusive control"),
    (_fs("pinnacle","apex","zenith","acme"),
     _fs("highest","topmost","utmost","ultimate"),
     0.80, "pinnacle already means the very highest point"),
    (_fs("bachelor","bachelors"),
     _fs("unmarried","single","unwed"),
     0.85, "a bachelor is already unmarried"),
    (_fs("noon","midday"),
     _fs("midday","middle"),
     0.75, "noon is already the middle of the day"),
    (_fs("debut","debuted"),
     _fs("first","initial","maiden"),
     0.80, "a debut is already a first appearance"),
    (_fs("prototype","prototypes"),
     _fs("initial","early","first","original","preliminary"),
     0.70, "a prototype is already an early/initial version"),
    (_fs("clone","clones"),
     _fs("exact","identical","perfect"),
     0.85, "clones are identical by definition"),
]

# ---------------------------------------------------------------------------
# Build the flat _PAIRS list from all categories above
# Each entry: (set_a, set_b, max_gap, severity, note)
# ---------------------------------------------------------------------------

_PAIRS: List[Tuple[FrozenSet[str], FrozenSet[str], int, float, str]] = []

def _add(a: FrozenSet[str], b: FrozenSet[str], gap: int,
         sev: float, note: str) -> None:
    _PAIRS.append((a, b, gap, sev, note))

# Manner verbs + redundant adverbs
_add(_SLOW_VERBS,  _SLOW_ADVS,  3, 0.80, "verb already implies slow movement")
_add(_FAST_VERBS,  _FAST_ADVS,  3, 0.80, "verb already implies fast movement")
_add(_QUIET_VERBS, _QUIET_ADVS, 3, 0.80, "verb already implies quiet/stealthy action")
_add(_LOUD_VERBS,  _LOUD_ADVS,  3, 0.80, "verb already implies loud sound")
_add(_SAD_VERBS,   _SAD_ADVS,   3, 0.75, "verb already implies sadness")
_add(_HAPPY_VERBS, _HAPPY_ADVS, 3, 0.75, "verb already implies happiness")
_add(_ANGRY_VERBS, _ANGRY_ADVS, 3, 0.75, "verb already implies anger")

# Absolute verbs + total adverbs
_add(_ABS_VERBS, _TOTAL_ADVS, 3, 0.80, "verb meaning is already absolute/total")

# Absolute adjectives + degree modifiers
_add(_ABS_ADJS, _DEGREE_MODS, 2, 0.85, "adjective is absolute — degree modifier doesn't apply")

# Togetherness verbs + "together"
_add(_TOGETHER_VERBS, _fs("together"), 3, 0.85, "verb already implies joining/union")

# Directional pairs (one per particle word)
for _verb_forms, _particle, _sev, _note in _DIRECTIONAL:
    _add(_verb_forms, _fs(_particle), 3, _sev, _note)

# Noun + redundant adjective
for _nouns, _adjs, _sev, _note in _NOUN_PLEONASMS:
    _add(_nouns, _adjs, 2, _sev, _note)


# ---------------------------------------------------------------------------
# Build inverted index at import time for fast scanning
# ---------------------------------------------------------------------------

# _idx_a[word] = list of pair indices where word is in set_a
# _idx_b[word] = list of pair indices where word is in set_b
_idx_a: Dict[str, List[int]] = {}
_idx_b: Dict[str, List[int]] = {}

for _i, (_sa, _sb, _, _, _) in enumerate(_PAIRS):
    for _w in _sa:
        _idx_a.setdefault(_w, []).append(_i)
    for _w in _sb:
        _idx_b.setdefault(_w, []).append(_i)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def _find_pleonasms(
    tokens: List[Dict[str, Any]],
) -> List[Tuple[int, int, float, str]]:
    """
    Return list of (head_idx, mod_idx, severity, note).
    head_idx is the set_a token (the word whose meaning subsumes the other).
    mod_idx  is the set_b token (the redundant modifier/particle).
    Pairs are deduplicated; each (head, mod) is reported at most once.
    """
    results: List[Tuple[int, int, float, str]] = []
    reported: Set[frozenset] = set()

    for i, tok_i in enumerate(tokens):
        word_i = tok_i["word"]

        # word_i is the HEAD (set_a) → scan ahead for MODIFIER (set_b)
        for pidx in _idx_a.get(word_i, []):
            sa, sb, max_gap, sev, note = _PAIRS[pidx]
            for j in range(i + 1, min(len(tokens), i + max_gap + 2)):
                word_j = tokens[j]["word"]
                if word_j in sb:
                    key = frozenset((i, j))
                    if key not in reported:
                        reported.add(key)
                        results.append((i, j, sev, note))   # head=i, mod=j
                    break

        # word_i is the MODIFIER (set_b) → scan ahead for HEAD (set_a)
        for pidx in _idx_b.get(word_i, []):
            sa, sb, max_gap, sev, note = _PAIRS[pidx]
            for j in range(i + 1, min(len(tokens), i + max_gap + 2)):
                word_j = tokens[j]["word"]
                if word_j in sa:
                    key = frozenset((i, j))
                    if key not in reported:
                        reported.add(key)
                        results.append((j, i, sev, note))   # head=j, mod=i
                    break

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    min_sev = float(config.get("min_severity", 0.05))

    tokens = build_positions(text)
    if not tokens:
        return {"flags": [], "meta": {}}

    matches = _find_pleonasms(tokens)

    flags: List[Dict[str, Any]] = []
    group_id = 0

    for head_idx, mod_idx, sev, note in matches:
        if sev < min_sev:
            continue

        th = tokens[head_idx]
        tm = tokens[mod_idx]

        # Same message on both flags: the modifier is always the redundant word.
        # The hover float deduplicates identical messages so one clear line appears.
        msg = f"Semantic pleonasm: '{tm['word']}' is redundant — {note}"

        flags.append(make_flag(
            th["s_line"], th["s_col"], th["e_col"],
            sev, msg, group=group_id,
        ))
        flags.append(make_flag(
            tm["s_line"], tm["s_col"], tm["e_col"],
            sev, msg, group=group_id,
        ))
        group_id += 1

    return {"flags": flags, "meta": {}}
