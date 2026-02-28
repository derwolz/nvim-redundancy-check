-- lua/redundancy/init.lua
-- Public API and setup entry point for redundancy.nvim

local M = {}

local core = require("redundancy.core")

---@class RedundancyConfig
---@field frequency_sensitivity number  How hard to dampen frequent words (default 50)
---@field decay_rate             number  Logarithmic decay rate (default 2.0)
---@field similarity_threshold  number  Min Levenshtein ratio 0–1 (default 0.82)
---@field min_severity           number  Minimum severity to flag (default 0.03)
---@field keymap                 string  Leader key suffix (default "r")

local defaults = {
  frequency_sensitivity = 50.0,
  decay_rate            = 2.0,
  similarity_threshold  = 0.82,
  min_severity          = 0.03,
  keymap                = "r",
}

M.config = vim.deepcopy(defaults)

--- Call this in your init.lua / lazy.nvim config block.
---@param opts RedundancyConfig|nil
function M.setup(opts)
  M.config = vim.tbl_deep_extend("force", defaults, opts or {})

  core.setup_highlights()
  core.setup_config(M.config)

  -- <Leader>r  →  toggle analysis on current buffer
  vim.keymap.set("n", "<Leader>" .. M.config.keymap, function()
    core.toggle()
  end, { desc = "Toggle redundancy analysis", silent = true })

  vim.notify("[redundancy.nvim] ready — press <Leader>" .. M.config.keymap .. " to analyse", vim.log.levels.INFO)
end

-- Expose core functions for manual use
M.run    = core.run
M.clear  = core.clear
M.toggle = core.toggle

return M
