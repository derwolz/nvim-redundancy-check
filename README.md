# redundancy.nvim

A Neovim plugin that detects redundant or near-duplicate words in your document
and highlights them without ever touching the file.

---

## How it works

- **Red highlight** — every word that has at least one suspiciously close twin
- **Blue highlight** — when your cursor sits on a word, all of its related words
  light up blue (the word itself too)
- Highlights live in a virtual extmark namespace — your file is never modified
- Press `<Leader>r` again to toggle everything off

Severity is shaped by three continuous factors:

| Factor | Effect |
|---|---|
| **Levenshtein similarity** | "result" / "results" scores ~0.92 |
| **Logarithmic distance decay** | Close pairs are louder; distant pairs fade but never disappear |
| **Frequency dampening** | "the" and "and" are whispered; rare content words are shouted |

---

## Installation

### lazy.nvim

```lua
{
  "derwolz/nvim-redundancy-check",
  config = function()
    require("redundancy").setup()
  end,
}
```

### packer.nvim

```lua
use {
  "derwolz/nvim-redundancy-check",
  config = function()
    require("redundancy").setup()
  end,
}
```

### Manual (no plugin manager)

Clone into your Neovim packages directory:

```bash
git clone https://github.com/derwolz/nvim-redundancy-check \
  ~/.local/share/nvim/site/pack/plugins/start/redundancy.nvim
```

Then add to your `init.lua`:

```lua
require("redundancy").setup()
```

**Requires:** Python 3 (`python3`) available on your `PATH`.

---

## Usage

| Key | Action |
|---|---|
| `<Leader>r` | Toggle analysis on/off for current buffer |

Move the cursor onto any red-highlighted word to see all its relatives turn blue.

---

## Configuration

All options are optional — defaults shown below:

```lua
require("redundancy").setup({
  -- How aggressively to dampen high-frequency words.
  -- Higher = "the"/"and" get even quieter. Range: 10–200.
  frequency_sensitivity = 50.0,

  -- How fast severity fades with word distance.
  -- Higher = steeper early drop. Range: 0.5–5.0.
  decay_rate = 2.0,

  -- Minimum Levenshtein similarity to flag a pair.
  -- 1.0 = exact matches only. 0.82 catches morphological variants.
  similarity_threshold = 0.82,

  -- Pairs below this severity are silently ignored (keeps noise down).
  min_severity = 0.03,

  -- Key appended to <Leader> to toggle. Default: "r" → <Leader>r
  keymap = "r",
})
```

---

## Highlight customisation

Override the colours after `setup()`:

```lua
-- Flagged words (red)
vim.api.nvim_set_hl(0, "RedundancyError", { bg = "#4a1010", fg = "#ff8080", bold = true })

-- Cursor-word relatives (blue)
vim.api.nvim_set_hl(0, "RedundancyFocus", { bg = "#0d2a4a", fg = "#80c8ff", bold = true })
```

---

## Project structure

```
redundancy.nvim/
├── lua/
│   └── redundancy/
│       ├── init.lua      ← public API + setup()
│       └── core.lua      ← highlights, extmarks, cursor tracking
├── python/
│   └── analyse.py        ← analysis backend (called async by Lua)
└── README.md
```
