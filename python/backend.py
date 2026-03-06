"""
python/backend.py
Entry point for the quill.nvim Python backend.

Usage:
    python backend.py --tool <name> <filepath> [config_json]

Prints a single JSON object to stdout:
    {
        "tool":   "<name>",
        "meta":   { "flagged": N, "duration_ms": M, ... },
        "flags":  [ { s_line, s_col, e_col, severity, message, ?group }, ... ],
        "tokens": []
    }
"""

import argparse
import json
import sys
import time
import os

# Ensure the python/ directory is on the path so `tools.*` imports work
sys.path.insert(0, os.path.dirname(__file__))

from tools import (redundancy, rhythm, wordiness, punctuation, typography, register,
                   passive, tense, structure, entity, agreement, coherence, semantic,
                   placement)


DISPATCH = {
    "redundancy":  redundancy.analyse,
    "rhythm":      rhythm.analyse,
    "wordiness":   wordiness.analyse,
    "punctuation": punctuation.analyse,
    "typography":  typography.analyse,
    "register":    register.analyse,
    "passive":     passive.analyse,
    "tense":       tense.analyse,
    "structure":   structure.analyse,
    "entity":      entity.analyse,
    "agreement":   agreement.analyse,
    "coherence":   coherence.analyse,
    "semantic":    semantic.analyse,
    "placement":   placement.analyse,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="quill.nvim analysis backend")
    parser.add_argument("--tool", required=True, choices=list(DISPATCH.keys()),
                        help="Which tool to run")
    parser.add_argument("filepath", help="Path to the file to analyse")
    parser.add_argument("config_json", nargs="?", default="{}",
                        help="JSON config object (optional)")
    args = parser.parse_args()

    try:
        config = json.loads(args.config_json)
    except json.JSONDecodeError:
        config = {}

    try:
        with open(args.filepath, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    fn = DISPATCH[args.tool]

    t0 = time.monotonic()
    result = fn(text, config)
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    flags  = result.get("flags", [])
    meta   = result.get("meta", {})
    meta["flagged"]     = len(flags)
    meta["duration_ms"] = elapsed_ms

    output = {
        "tool":   args.tool,
        "meta":   meta,
        "flags":  flags,
        "tokens": result.get("tokens", []),
    }

    print(json.dumps(output))


if __name__ == "__main__":
    main()
