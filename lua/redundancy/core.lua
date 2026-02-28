-- redundancy/core.lua
-- Manages analysis state, highlight groups, extmarks, and cursor tracking.

local M = {}

-- Highlight groups
local HL_RED  = "RedundancyError"    -- word has at least one close twin
local HL_BLUE = "RedundancyFocus"    -- words related to the word under cursor

-- Namespace for all extmarks (keeps them isolated from real content)
local NS = vim.api.nvim_create_namespace("redundancy")

-- Plugin config (set via setup_config)
local cfg = {}

function M.setup_config(c)
  cfg = c
end

-- Per-buffer state
-- state[bufnr] = {
--   flags  = [...],   -- raw flag list from Python
--   tokens = [...],   -- raw token list from Python
--   marks  = [...],   -- list of extmark ids we placed
--   active = false,
-- }
local state = {}

-- ---------------------------------------------------------------------------
-- Highlight group setup
-- ---------------------------------------------------------------------------

function M.setup_highlights()
  -- Red bg for flagged words (all-on analysis view)
  vim.api.nvim_set_hl(0, HL_RED, {
    bg = "#4a1010",
    fg = "#ff8080",
    bold = true,
  })
  -- Blue bg for cursor-word relatives
  vim.api.nvim_set_hl(0, HL_BLUE, {
    bg = "#0d2a4a",
    fg = "#80c8ff",
    bold = true,
  })
end

-- ---------------------------------------------------------------------------
-- Utility: get the Python script path (sits next to this plugin)
-- ---------------------------------------------------------------------------

local function python_script()
  -- __FILE__ equivalent: find where this script lives
  local src = debug.getinfo(1, "S").source:sub(2)  -- strip leading @
  local dir = vim.fn.fnamemodify(src, ":h:h:h")     -- go up three dirs (lua/redundancy/core.lua → plugin root)
  return dir .. "/python/analyse.py"
end

-- ---------------------------------------------------------------------------
-- Clear all extmarks for a buffer
-- ---------------------------------------------------------------------------

local function clear_marks(bufnr)
  vim.api.nvim_buf_clear_namespace(bufnr, NS, 0, -1)
  if state[bufnr] then
    state[bufnr].marks = {}
  end
end

-- ---------------------------------------------------------------------------
-- Place a highlight extmark (returns the mark id)
-- ---------------------------------------------------------------------------

local function place_mark(bufnr, s_line, s_col, e_col, hl_group)
  -- e_col is end col in the same line (we assume tokens don't span lines)
  return vim.api.nvim_buf_set_extmark(bufnr, NS, s_line, s_col, {
    end_row    = s_line,
    end_col    = e_col,
    hl_group   = hl_group,
    priority   = 150,
  })
end

-- ---------------------------------------------------------------------------
-- Apply red highlights for ALL flagged tokens
-- ---------------------------------------------------------------------------

local function apply_red_marks(bufnr)
  local s = state[bufnr]
  if not s then return end

  -- Collect every token index that appears in at least one flag
  local flagged = {}
  for _, flag in ipairs(s.flags) do
    flagged[flag.i] = true
    flagged[flag.j] = true
  end

  for idx, _ in pairs(flagged) do
    local tok = s.tokens[idx + 1]  -- Lua is 1-indexed
    if tok then
      place_mark(bufnr, tok.s_line, tok.s_col, tok.e_col, HL_RED)
    end
  end
end

-- ---------------------------------------------------------------------------
-- Cursor handler: blue-highlight words related to the word under cursor
-- ---------------------------------------------------------------------------

local function on_cursor_moved(bufnr)
  local s = state[bufnr]
  if not s or not s.active then return end

  -- Get cursor position (1-indexed line, 0-indexed col)
  local row, col = unpack(vim.api.nvim_win_get_cursor(0))
  row = row - 1  -- convert to 0-indexed

  -- Find which token the cursor is on
  local cursor_idx = nil
  for i, tok in ipairs(s.tokens) do
    if tok.s_line == row and col >= tok.s_col and col < tok.e_col then
      cursor_idx = i - 1  -- store as 0-indexed to match flag data
      break
    end
  end

  -- Clear existing blue marks, then re-draw all reds
  clear_marks(bufnr)
  apply_red_marks(bufnr)

  if cursor_idx == nil then return end

  -- Find all flags that involve this token index
  local related = {}
  for _, flag in ipairs(s.flags) do
    if flag.i == cursor_idx then
      related[flag.j] = flag.severity
    elseif flag.j == cursor_idx then
      related[flag.i] = flag.severity
    end
  end

  -- Blue-highlight the cursor word itself and all its relatives
  local cursor_tok = s.tokens[cursor_idx + 1]
  if cursor_tok and next(related) then
    place_mark(bufnr, cursor_tok.s_line, cursor_tok.s_col, cursor_tok.e_col, HL_BLUE)
    for rel_idx, _ in pairs(related) do
      local rel_tok = s.tokens[rel_idx + 1]
      if rel_tok then
        place_mark(bufnr, rel_tok.s_line, rel_tok.s_col, rel_tok.e_col, HL_BLUE)
      end
    end
  end
end

-- ---------------------------------------------------------------------------
-- Run analysis for the current buffer
-- ---------------------------------------------------------------------------

function M.run(bufnr)
  bufnr = bufnr or vim.api.nvim_get_current_buf()
  local filepath = vim.api.nvim_buf_get_name(bufnr)

  if filepath == "" then
    vim.notify("[redundancy] Buffer has no file path — save it first.", vim.log.levels.WARN)
    return
  end

  -- Save buffer if modified so Python reads current content
  if vim.bo[bufnr].modified then
    vim.cmd("write")
  end

  local script = python_script()
  local python  = vim.fn.exepath("python3") ~= "" and "python3" or "python"

  vim.notify("[redundancy] Analysing…", vim.log.levels.INFO)

  -- Run Python asynchronously
  local stdout_chunks = {}

  vim.fn.jobstart({
    python, script, filepath,
    tostring(cfg.frequency_sensitivity or 50.0),
    tostring(cfg.decay_rate            or 2.0),
    tostring(cfg.similarity_threshold  or 0.82),
    tostring(cfg.min_severity          or 0.03),
  }, {
    stdout_buffered = true,
    on_stdout = function(_, data)
      for _, chunk in ipairs(data) do
        table.insert(stdout_chunks, chunk)
      end
    end,
    on_stderr = function(_, data)
      for _, line in ipairs(data) do
        if line ~= "" then
          vim.notify("[redundancy] " .. line, vim.log.levels.ERROR)
        end
      end
    end,
    on_exit = function(_, code)
      if code ~= 0 then
        vim.notify("[redundancy] Analysis failed (exit " .. code .. ")", vim.log.levels.ERROR)
        return
      end

      local raw = table.concat(stdout_chunks, "\n")
      local ok, parsed = pcall(vim.json.decode, raw)

      if not ok or type(parsed) ~= "table" then
        vim.notify("[redundancy] Could not parse analysis output.", vim.log.levels.ERROR)
        return
      end

      if parsed.error then
        vim.notify("[redundancy] " .. parsed.error, vim.log.levels.ERROR)
        return
      end

      state[bufnr] = {
        flags  = parsed.flags  or {},
        tokens = parsed.tokens or {},
        marks  = {},
        active = true,
      }

      clear_marks(bufnr)
      apply_red_marks(bufnr)

      local n = #state[bufnr].flags
      vim.notify(
        string.format("[redundancy] %d pair%s flagged. Hover a word to see its relatives.", n, n == 1 and "" or "s"),
        vim.log.levels.INFO
      )

      -- Register cursor autocmd for this buffer
      vim.api.nvim_create_autocmd({ "CursorMoved", "CursorMovedI" }, {
        buffer  = bufnr,
        group   = vim.api.nvim_create_augroup("RedundancyCursor_" .. bufnr, { clear = true }),
        callback = function()
          on_cursor_moved(bufnr)
        end,
      })
    end,
  })
end

-- ---------------------------------------------------------------------------
-- Toggle off: clear all marks and deactivate
-- ---------------------------------------------------------------------------

function M.clear(bufnr)
  bufnr = bufnr or vim.api.nvim_get_current_buf()
  clear_marks(bufnr)
  if state[bufnr] then
    state[bufnr].active = false
  end
  -- Remove cursor autocmd
  pcall(vim.api.nvim_del_augroup_by_name, "RedundancyCursor_" .. bufnr)
  vim.notify("[redundancy] Cleared.", vim.log.levels.INFO)
end

-- ---------------------------------------------------------------------------
-- Toggle: run if inactive, clear if active
-- ---------------------------------------------------------------------------

function M.toggle(bufnr)
  bufnr = bufnr or vim.api.nvim_get_current_buf()
  if state[bufnr] and state[bufnr].active then
    M.clear(bufnr)
  else
    M.run(bufnr)
  end
end

return M
