# quill.nvim

A comprehensive prose-analysis suite for Neovim. Six independent tools analyse
your writing for redundancy, rhythm, wordiness, punctuation, typography, and
register — all without ever touching your file.

---

## How it works

- **Red highlight** — every word or phrase flagged by the active tool
- **Blue highlight** — when your cursor sits on a red word, related words
  (e.g. both members of a redundant pair) light up blue
- Highlights live in per-tool extmark namespaces — your file is never modified
- Press a keymap again to toggle the tool off

---

## Tools

| Keymap | Tool | Description |
|---|---|---|
| `<Leader>lr` | **Redundancy** | Near-duplicate words within a rolling window, shaped by Levenshtein similarity, distance decay, and frequency dampening |
| `<Leader>lR` | **Rhythm** | Runs of monotonously similar sentence lengths; long or lexically complex sentences; Flesch-Kincaid score in meta |
| `<Leader>lw` | **Wordiness** | 200+ inflated phrases, hollow openers, redundant pairs, weasel qualifiers, and bloated comparatives |
| `<Leader>lp` | **Punctuation** | Inconsistent dash style, quote style, Oxford comma, and double spaces |
| `<Leader>lt` | **Typography** | Double spaces, trailing whitespace, ellipsis inconsistency, and straight quotes in smart-quote documents |
| `<Leader>lg` | **Register** | Informal words in formal documents; formal/academic vocabulary in informal text |
| `<Leader>ll` | **Run all** | Runs all six tools simultaneously (no namespace collision) |

---

## Installation

### lazy.nvim

```lua
{
  "derwolz/nvim-redundancy-check",
  config = function()
    require("quill").setup()
  end,
}
```

### packer.nvim

```lua
use {
  "derwolz/nvim-redundancy-check",
  config = function()
    require("quill").setup()
  end,
}
```

### Manual (no plugin manager)

```bash
git clone https://github.com/derwolz/nvim-redundancy-check \
  ~/.local/share/nvim/site/pack/plugins/start/quill.nvim
```

Then add to your `init.lua`:

```lua
require("quill").setup()
```

**Requires:** Python 3 (`python3`) available on your `PATH`. No third-party
Python packages needed.

---

## Usage

Open any prose file, then use the keymaps above. Hover over a red-highlighted
word to see its related flags turn blue (most useful for redundancy pairs).
Toggle a tool off by pressing its keymap again.

---

## Configuration

All options are optional — defaults shown below:

```lua
require("quill").setup({
  -- Redundancy tool: how aggressively to dampen high-frequency words.
  -- Higher = "the"/"and" get even quieter. Range: 10–200.
  frequency_sensitivity = 50.0,

  -- Redundancy tool: how fast severity fades with word distance.
  -- Higher = steeper early drop. Range: 0.5–5.0.
  decay_rate = 2.0,

  -- Redundancy tool: minimum Levenshtein similarity to flag a pair.
  -- 1.0 = exact matches only. 0.82 catches morphological variants.
  similarity_threshold = 0.82,

  -- Redundancy tool: pairs below this severity are silently ignored.
  min_severity = 0.03,
})
```

The full config object is forwarded as JSON to every Python tool, so each tool
can also read custom keys from it.

---

## Highlight customisation

Each tool has two highlight groups: `QuillFlagged_<tool>` (red) and
`QuillRelated_<tool>` (blue). Override after `setup()`:

```lua
-- Redundancy flagged words
vim.api.nvim_set_hl(0, "QuillFlagged_redundancy", { bg="#4a1010", fg="#ff8080", bold=true })
-- Redundancy related words (cursor hover)
vim.api.nvim_set_hl(0, "QuillRelated_redundancy", { bg="#0d2a4a", fg="#80c8ff", bold=true })
```

---

## Project structure

```
quill.nvim/
├── lua/
│   └── quill/
│       ├── init.lua          ← setup(), tool registry, all keymaps
│       └── core.lua          ← generic highlight engine (run/clear/toggle/run_all)
├── python/
│   ├── backend.py            ← entry: python backend.py --tool <name> <path> <config_json>
│   └── tools/
│       ├── shared.py         ← tokenise(), byte_to_line_col(), make_flag()
│       ├── redundancy.py     ← tool 1
│       ├── rhythm.py         ← tool 2
│       ├── wordiness.py      ← tool 3
│       ├── punctuation.py    ← tool 4
│       ├── typography.py     ← tool 5
│       └── register.py       ← tool 6
└── README.md
```
