-- lua/quill/init.lua
-- Public API and setup entry point for quill.nvim

local M = {}

local core = require("quill.core")

-- ---------------------------------------------------------------------------
-- Dependency management
-- ---------------------------------------------------------------------------

local function _plugin_root()
  local src = debug.getinfo(1, "S").source:sub(2)
  return vim.fn.fnamemodify(src, ":h:h:h")
end

local function _python_exe()
  return vim.fn.exepath("python3") ~= "" and "python3" or "python"
end

-- Install Python deps via pip if rapidfuzz is missing.
-- Called once from setup(); does nothing if rapidfuzz is already present.
local function _ensure_deps()
  local py = _python_exe()
  vim.fn.jobstart({ py, "-c", "import rapidfuzz" }, {
    on_exit = function(_, code)
      if code == 0 then return end  -- already installed
      local req = _plugin_root() .. "/python/requirements.txt"
      vim.notify("[quill] Installing rapidfuzz (one-time)…", vim.log.levels.INFO)
      vim.fn.jobstart({ py, "-m", "pip", "install", "-r", req, "--quiet" }, {
        on_exit = function(_, c)
          if c == 0 then
            vim.notify("[quill] rapidfuzz installed — fast analysis active.", vim.log.levels.INFO)
          else
            vim.notify(
              "[quill] Could not auto-install rapidfuzz. Run: pip install rapidfuzz",
              vim.log.levels.WARN
            )
          end
        end,
      })
    end,
  })
end

-- :QuillInstallDeps — force-reinstall Python dependencies
vim.api.nvim_create_user_command("QuillInstallDeps", function()
  local py  = _python_exe()
  local req = _plugin_root() .. "/python/requirements.txt"
  vim.notify("[quill] Installing Python dependencies…", vim.log.levels.INFO)
  vim.fn.jobstart({ py, "-m", "pip", "install", "-r", req }, {
    on_exit = function(_, code)
      if code == 0 then
        vim.notify("[quill] Dependencies installed.", vim.log.levels.INFO)
      else
        vim.notify("[quill] Install failed. Try: pip install rapidfuzz", vim.log.levels.ERROR)
      end
    end,
  })
end, { desc = "Install quill Python dependencies (rapidfuzz)" })

---@class QuillConfig
---@field frequency_sensitivity number  How hard to dampen frequent words (default 50)
---@field decay_rate             number  Logarithmic decay rate (default 2.0)
---@field similarity_threshold  number  Min Levenshtein ratio 0–1 (default 0.82)
---@field min_severity           number  Minimum severity to flag (default 0.03)
---@field keymap_prefix          string  Leader key prefix for all tools (default "l")
---@field run_all_keymap         string  Leader key suffix for run-all (default "ll")

local TOOLS = {
  { name="redundancy",  keymap="lr", desc="Redundancy check",
    hl_flagged={bg="#4a1010", fg="#ff8080", bold=true},
    hl_related ={bg="#003333", fg="#00e5e5", bold=true} },
  { name="rhythm",      keymap="lR", desc="Rhythm & readability",
    hl_flagged={bg="#1a2a00", fg="#a8c000", bold=true},
    hl_related ={bg="#0a1a00", fg="#70a000", bold=true} },
  { name="wordiness",   keymap="lw", desc="Wordiness",
    hl_flagged={bg="#2a1a00", fg="#ff9040", bold=true},
    hl_related ={bg="#1a0a00", fg="#c06020", bold=true} },
  { name="punctuation", keymap="lp", desc="Punctuation consistency",
    hl_flagged={bg="#1a002a", fg="#c080ff", bold=true},
    hl_related ={bg="#0a001a", fg="#8040c0", bold=true} },
  { name="typography",  keymap="lt", desc="Typography",
    hl_flagged={bg="#002a2a", fg="#40e0e0", bold=true},
    hl_related ={bg="#001a1a", fg="#20a0a0", bold=true} },
  { name="register",    keymap="lg", desc="Register consistency",
    hl_flagged={bg="#2a001a", fg="#ff80c0", bold=true},
    hl_related ={bg="#1a000a", fg="#c04080", bold=true} },
  { name="passive",   keymap="lv", desc="Passive voice",
    hl_flagged={bg="#2a1e00", fg="#ffcc44", bold=true},
    hl_related ={bg="#1a1200", fg="#c08800", bold=true} },
  { name="tense",     keymap="lT", desc="Tense consistency",
    hl_flagged={bg="#001a2a", fg="#5ab4ff", bold=true},
    hl_related ={bg="#000f1a", fg="#2a70c0", bold=true} },
  { name="structure", keymap="ls", desc="Sentence structure variety",
    hl_flagged={bg="#1a2a1a", fg="#88cc88", bold=true},
    hl_related ={bg="#0a1a0a", fg="#448844", bold=true} },
  { name="entity",    keymap="le", desc="Entity consistency",
    hl_flagged={bg="#2a0e08", fg="#ff7055", bold=true},
    hl_related ={bg="#1a0600", fg="#b84030", bold=true} },
  { name="agreement", keymap="la", desc="Subject-verb agreement",
    hl_flagged={bg="#1a1a2a", fg="#bbaaff", bold=true},
    hl_related ={bg="#0e0e1a", fg="#7766cc", bold=true} },
  { name="coherence", keymap="lc", desc="Paragraph coherence",
    hl_flagged={bg="#002a1a", fg="#44ddaa", bold=true},
    hl_related ={bg="#001a10", fg="#229966", bold=true} },
  { name="semantic",  keymap="lS", desc="Semantic pleonasm",
    hl_flagged={bg="#2a1a2a", fg="#e080ff", bold=true},
    hl_related ={bg="#1a0a1a", fg="#a040c0", bold=true} },
  { name="placement", keymap="lm", desc="Sentence placement",
    hl_flagged={bg="#1a1a00", fg="#e0d040", bold=true},
    hl_related ={bg="#0f0f00", fg="#a09820", bold=true} },
}

local defaults = {
  frequency_sensitivity = 50.0,
  decay_rate            = 2.0,
  similarity_threshold  = 0.82,
  min_severity          = 0.03,
  virtual_text          = false,
}

M.config = vim.deepcopy(defaults)

--- Call this in your init.lua / lazy.nvim config block.
---@param opts QuillConfig|nil
function M.setup(opts)
  M.config = vim.tbl_deep_extend("force", defaults, opts or {})

  core.setup_config(M.config)
  _ensure_deps()

  for _, tool in ipairs(TOOLS) do
    core.register_tool(tool.name, tool.hl_flagged, tool.hl_related)

    vim.keymap.set("n", "<Leader>" .. tool.keymap, function()
      core.toggle(tool.name)
    end, { desc = tool.desc, silent = true })
  end

  -- <Leader>ll → run all tools
  vim.keymap.set("n", "<Leader>ll", function()
    core.run_all()
  end, { desc = "Run all quill tools", silent = true })

  -- <Leader>li → summary panel
  vim.keymap.set("n", "<Leader>li", function()
    core.summary_panel()
  end, { desc = "Quill summary panel", silent = true })

  -- <Leader>lE → export report
  vim.keymap.set("n", "<Leader>lE", function()
    core.export_report()
  end, { desc = "Export quill report", silent = true })

  -- <Leader>ln / <Leader>lN → flag navigation
  vim.keymap.set("n", "<Leader>ln", function()
    core.next_flag()
  end, { desc = "Next quill flag", silent = true })

  vim.keymap.set("n", "<Leader>lN", function()
    core.prev_flag()
  end, { desc = "Prev quill flag", silent = true })

  -- <Leader>l. → dismiss flag under cursor for the active tool
  vim.keymap.set("n", "<Leader>l.", function()
    local tool = core.get_active_tool()
    if not tool then
      vim.notify("[quill] No active analysis.", vim.log.levels.WARN); return
    end
    core.dismiss_flag(tool)
  end, { desc = "Dismiss flag under cursor (active tool)", silent = true })

  -- <Leader>l% → next flag for the active tool
  vim.keymap.set("n", "<Leader>l%", function()
    local bufnr = vim.api.nvim_get_current_buf()
    local tool = core.get_active_tool(bufnr)
    if not tool then
      vim.notify("[quill] No active analysis.", vim.log.levels.WARN); return
    end
    core.next_flag(bufnr)
  end, { desc = "Next flag (active tool)", silent = true })

end

-- Expose core functions for manual use
M.run           = core.run
M.clear         = core.clear
M.toggle        = core.toggle
M.run_all       = core.run_all
M.get_state     = core.get_state
M.summary_panel = core.summary_panel
M.export_report = core.export_report
M.next_flag       = core.next_flag
M.prev_flag       = core.prev_flag
M.get_active_tool = core.get_active_tool

return M
