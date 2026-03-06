-- lua/quill/core.lua
-- Generic highlight engine for quill.nvim.
-- Manages per-tool namespaces, highlight groups, extmarks, and cursor tracking.

local M = {}

-- Per-tool namespace IDs
local namespaces = {}   -- namespaces[tool] = ns_id

-- Per-tool highlight group names
local hl_defs = {}      -- hl_defs[tool] = { flagged="QuillFlagged_X", related="QuillRelated_X" }

-- Per-tool, per-buffer state
-- state[tool][bufnr] = { flags, marks, active }
local state = {}

-- Plugin config (set via setup_config)
local cfg = {}

-- Hover float state
local _hover_win        = nil   -- current hover float window ID
local _hover_registered = {}    -- [bufnr] = true once hover autocmd is set up

-- ---------------------------------------------------------------------------
-- Config
-- ---------------------------------------------------------------------------

function M.setup_config(c)
  cfg = c
end

-- ---------------------------------------------------------------------------
-- Hover float helpers
-- ---------------------------------------------------------------------------

local function _close_hover()
  if _hover_win and vim.api.nvim_win_is_valid(_hover_win) then
    vim.api.nvim_win_close(_hover_win, true)
  end
  _hover_win = nil
end

local function _open_hover(flags_at_cursor)
  _close_hover()
  if #flags_at_cursor == 0 then return end

  -- De-duplicate messages
  local seen, lines = {}, {}
  for _, flag in ipairs(flags_at_cursor) do
    local key = (flag.tool or "") .. ":" .. (flag.message or "")
    if not seen[key] then
      seen[key] = true
      local sev    = flag.severity and string.format(" (%.0f%%)", flag.severity * 100) or ""
      local prefix = flag.tool and ("[" .. flag.tool .. "] ") or ""
      table.insert(lines, prefix .. (flag.message or "") .. sev)
    end
  end

  local width = 2
  for _, l in ipairs(lines) do width = math.max(width, #l) end
  width = math.min(width + 2, 80)

  local fbuf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_buf_set_lines(fbuf, 0, -1, false, lines)
  vim.bo[fbuf].modifiable = false

  _hover_win = vim.api.nvim_open_win(fbuf, false, {
    relative  = "cursor",
    row       = 1,
    col       = 0,
    width     = width,
    height    = #lines,
    border    = "rounded",
    style     = "minimal",
    focusable = false,
    zindex    = 50,
  })
end

local function _ensure_hover_autocmd(bufnr)
  if _hover_registered[bufnr] then return end
  _hover_registered[bufnr] = true

  local aug = vim.api.nvim_create_augroup("QuillHover_" .. bufnr, { clear = true })

  vim.api.nvim_create_autocmd({ "CursorMoved", "CursorMovedI" }, {
    buffer   = bufnr,
    group    = aug,
    callback = function()
      local row, col = unpack(vim.api.nvim_win_get_cursor(0))
      row = row - 1
      local found = {}
      for tool_name, tool_state in pairs(state) do
        local s = tool_state[bufnr]
        if s and s.active then
          for _, flag in ipairs(s.flags) do
            if flag.s_line == row and col >= flag.s_col and col < flag.e_col then
              table.insert(found, vim.tbl_extend("force", flag, { tool = tool_name }))
            end
          end
        end
      end
      if #found > 0 then _open_hover(found) else _close_hover() end
    end,
  })

  vim.api.nvim_create_autocmd({ "InsertEnter", "BufLeave" }, {
    buffer   = bufnr,
    group    = aug,
    callback = _close_hover,
  })
end

-- ---------------------------------------------------------------------------
-- Utility: resolve python backend path
-- ---------------------------------------------------------------------------

local function backend_path()
  local src = debug.getinfo(1, "S").source:sub(2)           -- strip leading @
  local dir = vim.fn.fnamemodify(src, ":h:h:h")             -- lua/quill/core.lua → plugin root
  return dir .. "/python/backend.py"
end

local function python_exe()
  return vim.fn.exepath("python3") ~= "" and "python3" or "python"
end

-- ---------------------------------------------------------------------------
-- Register a tool (called once per tool during setup)
-- ---------------------------------------------------------------------------

function M.register_tool(name, hl_flagged_def, hl_related_def)
  namespaces[name] = vim.api.nvim_create_namespace("quill_" .. name)

  local fg_name  = "QuillFlagged_" .. name
  local rel_name = "QuillRelated_" .. name

  vim.api.nvim_set_hl(0, fg_name,  hl_flagged_def)
  vim.api.nvim_set_hl(0, rel_name, hl_related_def)
  vim.api.nvim_set_hl(0, "QuillSign_" .. name, { fg = hl_flagged_def.fg })

  hl_defs[name] = { flagged = fg_name, related = rel_name }
  state[name]   = {}
end

-- ---------------------------------------------------------------------------
-- Internal: clear all extmarks for one tool + buffer
-- ---------------------------------------------------------------------------

local function clear_marks(tool_name, bufnr)
  local ns = namespaces[tool_name]
  if not ns then return end
  vim.api.nvim_buf_clear_namespace(bufnr, ns, 0, -1)
  if state[tool_name] and state[tool_name][bufnr] then
    state[tool_name][bufnr].marks = {}
  end
end

-- ---------------------------------------------------------------------------
-- Internal: place one extmark
-- ---------------------------------------------------------------------------

local function place_mark(tool_name, bufnr, s_line, s_col, e_col, hl_group)
  local ns = namespaces[tool_name]
  if not ns then return end
  return vim.api.nvim_buf_set_extmark(bufnr, ns, s_line, s_col, {
    end_row  = s_line,
    end_col  = e_col,
    hl_group = hl_group,
    priority = 150,
  })
end

-- ---------------------------------------------------------------------------
-- Internal: apply flagged (red) highlights for all flags of a tool
-- ---------------------------------------------------------------------------

local function apply_flagged_marks(tool_name, bufnr)
  local s = state[tool_name] and state[tool_name][bufnr]
  if not s then return end
  local ns = namespaces[tool_name]
  local hl = hl_defs[tool_name]
  for _, flag in ipairs(s.flags) do
    local sev     = flag.severity or 0
    local sign_ch = sev >= 0.7 and "● " or (sev >= 0.4 and "▸ " or "· ")
    local vt      = cfg.virtual_text
                    and {{ string.format(" · %d%%", math.floor(sev * 100)), "Comment" }}
                    or nil
    vim.api.nvim_buf_set_extmark(bufnr, ns, flag.s_line, flag.s_col, {
      end_row       = flag.s_line,
      end_col       = flag.e_col,
      hl_group      = hl.flagged,
      sign_text     = sign_ch,
      sign_hl_group = "QuillSign_" .. tool_name,
      priority      = 150,
      virt_text     = vt,
      virt_text_pos = "eol",
    })
  end
end

-- ---------------------------------------------------------------------------
-- CursorMoved handler: blue-highlight flags sharing a group with cursor flag
-- ---------------------------------------------------------------------------

local function on_cursor_moved(tool_name, bufnr)
  local s = state[tool_name] and state[tool_name][bufnr]
  if not s or not s.active then return end

  local row, col = unpack(vim.api.nvim_win_get_cursor(0))
  row = row - 1  -- 0-indexed

  -- Find which flags the cursor overlaps
  local cursor_groups = {}
  local cursor_flags  = {}
  for _, flag in ipairs(s.flags) do
    if flag.s_line == row and col >= flag.s_col and col < flag.e_col then
      table.insert(cursor_flags, flag)
      if flag.group ~= nil then
        cursor_groups[flag.group] = true
      end
    end
  end

  -- Redraw: clear → reds → blues for related
  clear_marks(tool_name, bufnr)
  apply_flagged_marks(tool_name, bufnr)

  if #cursor_flags == 0 then return end

  local hl = hl_defs[tool_name]

  -- Collect all flags sharing any of the cursor groups
  local related_set = {}
  if next(cursor_groups) then
    for _, flag in ipairs(s.flags) do
      if flag.group ~= nil and cursor_groups[flag.group] then
        local key = flag.s_line .. ":" .. flag.s_col .. ":" .. flag.e_col
        related_set[key] = flag
      end
    end
  end

  -- Blue-highlight related flags (overrides the red)
  for _, flag in pairs(related_set) do
    place_mark(tool_name, bufnr, flag.s_line, flag.s_col, flag.e_col, hl.related)
  end

  -- Also blue-highlight cursor flags themselves (they are in related_set if grouped,
  -- but if they have no group we still highlight them alone)
  for _, flag in ipairs(cursor_flags) do
    if flag.group == nil then
      place_mark(tool_name, bufnr, flag.s_line, flag.s_col, flag.e_col, hl.related)
    end
  end
end

-- ---------------------------------------------------------------------------
-- run(tool_name, bufnr)
-- ---------------------------------------------------------------------------

function M.run(tool_name, bufnr)
  bufnr = bufnr or vim.api.nvim_get_current_buf()

  if not namespaces[tool_name] then
    vim.notify("[quill] Unknown tool: " .. tool_name, vim.log.levels.ERROR)
    return
  end

  local filepath = vim.api.nvim_buf_get_name(bufnr)
  if filepath == "" then
    vim.notify("[quill] Buffer has no file path — save it first.", vim.log.levels.WARN)
    return
  end

  if vim.bo[bufnr].modified then
    vim.cmd("write")
  end

  local backend = backend_path()
  local python  = python_exe()
  local config_json = vim.json.encode(cfg)

  vim.notify("[quill/" .. tool_name .. "] Analysing…", vim.log.levels.INFO)

  local stdout_chunks = {}

  vim.fn.jobstart({
    python, backend, "--tool", tool_name, filepath, config_json
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
          vim.notify("[quill/" .. tool_name .. "] " .. line, vim.log.levels.ERROR)
        end
      end
    end,
    on_exit = function(_, code)
      if code ~= 0 then
        vim.notify("[quill/" .. tool_name .. "] failed (exit " .. code .. ")", vim.log.levels.ERROR)
        return
      end

      local raw = table.concat(stdout_chunks, "\n")
      local ok, parsed = pcall(vim.json.decode, raw)

      if not ok or type(parsed) ~= "table" then
        vim.notify("[quill/" .. tool_name .. "] Could not parse output.", vim.log.levels.ERROR)
        return
      end

      if parsed.error then
        vim.notify("[quill/" .. tool_name .. "] " .. parsed.error, vim.log.levels.ERROR)
        return
      end

      state[tool_name][bufnr] = {
        flags    = parsed.flags or {},
        marks    = {},
        active   = true,
        meta     = parsed.meta or {},
        filepath = filepath,
      }

      _ensure_hover_autocmd(bufnr)
      clear_marks(tool_name, bufnr)
      apply_flagged_marks(tool_name, bufnr)

      local n   = #state[tool_name][bufnr].flags
      local meta = parsed.meta or {}
      vim.notify(
        string.format("[quill/%s] %d flag%s (%d ms). Hover to see relations.",
          tool_name, n, n == 1 and "" or "s", meta.duration_ms or 0),
        vim.log.levels.INFO
      )

      -- Register CursorMoved autocmd for this tool+buffer
      local augroup = "QuillCursor_" .. tool_name .. "_" .. bufnr
      vim.api.nvim_create_autocmd({ "CursorMoved", "CursorMovedI" }, {
        buffer  = bufnr,
        group   = vim.api.nvim_create_augroup(augroup, { clear = true }),
        callback = function()
          on_cursor_moved(tool_name, bufnr)
        end,
      })
    end,
  })
end

-- ---------------------------------------------------------------------------
-- clear(tool_name, bufnr)
-- ---------------------------------------------------------------------------

function M.clear(tool_name, bufnr)
  bufnr = bufnr or vim.api.nvim_get_current_buf()
  _close_hover()
  clear_marks(tool_name, bufnr)
  if state[tool_name] and state[tool_name][bufnr] then
    state[tool_name][bufnr].active = false
  end
  local augroup = "QuillCursor_" .. tool_name .. "_" .. bufnr
  pcall(vim.api.nvim_del_augroup_by_name, augroup)
  vim.notify("[quill/" .. tool_name .. "] Cleared.", vim.log.levels.INFO)
end

-- ---------------------------------------------------------------------------
-- toggle(tool_name, bufnr)
-- ---------------------------------------------------------------------------

function M.toggle(tool_name, bufnr)
  bufnr = bufnr or vim.api.nvim_get_current_buf()
  local s = state[tool_name] and state[tool_name][bufnr]
  if s and s.active then
    M.clear(tool_name, bufnr)
  else
    M.run(tool_name, bufnr)
  end
end

-- ---------------------------------------------------------------------------
-- run_all(bufnr)
-- ---------------------------------------------------------------------------

function M.run_all(bufnr)
  bufnr = bufnr or vim.api.nvim_get_current_buf()
  for tool_name in pairs(namespaces) do
    M.run(tool_name, bufnr)
  end
end

-- ---------------------------------------------------------------------------
-- get_state() — read-only accessor (prevents external mutation of local)
-- ---------------------------------------------------------------------------

function M.get_state()
  return state
end

-- ---------------------------------------------------------------------------
-- summary_panel(bufnr)
-- ---------------------------------------------------------------------------

function M.summary_panel(bufnr)
  bufnr = bufnr or vim.api.nvim_get_current_buf()

  -- Collect rows
  local rows = {}
  for tool_name, tool_state in pairs(state) do
    local s = tool_state[bufnr]
    if s then
      local top_sev = 0.0
      for _, flag in ipairs(s.flags) do
        if (flag.severity or 0) > top_sev then
          top_sev = flag.severity
        end
      end
      table.insert(rows, {
        tool      = tool_name,
        flags     = #s.flags,
        status    = s.active and "on" or "off",
        top_sev   = top_sev,
        meta      = s.meta or {},
      })
    end
  end

  if #rows == 0 then
    vim.notify("[quill] No analysis results for this buffer. Run a tool first.", vim.log.levels.WARN)
    return
  end

  -- Sort alphabetically by tool name
  table.sort(rows, function(a, b) return a.tool < b.tool end)

  -- Build display lines
  local lines = {
    string.format(" %-14s  %-6s  %-6s  %-8s", "Tool", "Flags", "Status", "Top Sev"),
    string.rep("─", 42),
  }
  for _, row in ipairs(rows) do
    table.insert(lines, string.format(
      " %-14s  %-6d  %-6s  %-8.2f",
      row.tool, row.flags, row.status, row.top_sev
    ))
    -- Inline meta hints
    local m = row.meta
    if m.readability   then table.insert(lines, string.format("   readability: %.1f", m.readability))    end
    if m.passive_ratio then table.insert(lines, string.format("   passive_ratio: %.1f%%", m.passive_ratio * 100)) end
    if m.dominant_tense then table.insert(lines, string.format("   dominant_tense: %s", m.dominant_tense)) end
  end
  table.insert(lines, "")
  table.insert(lines, " [q / <Esc> / <CR> / <Space>]  close")

  -- Open floating window
  local ui     = vim.api.nvim_list_uis()[1] or { width = 80, height = 24 }
  local width  = 46
  local height = math.min(#lines + 2, ui.height - 4)
  local col    = math.floor((ui.width - width) / 2)
  local row_pos = math.floor((ui.height - height) / 2)

  local fbuf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_buf_set_lines(fbuf, 0, -1, false, lines)
  vim.bo[fbuf].modifiable = false

  local win = vim.api.nvim_open_win(fbuf, true, {
    relative = "editor",
    width    = width,
    height   = height,
    col      = col,
    row      = row_pos,
    border   = "rounded",
    title    = " Quill Summary ",
    title_pos = "center",
  })

  -- Close keymaps
  for _, key in ipairs({ "q", "<Esc>", "<CR>", "<Space>" }) do
    vim.keymap.set("n", key, function()
      if vim.api.nvim_win_is_valid(win) then
        vim.api.nvim_win_close(win, true)
      end
    end, { buffer = fbuf, silent = true, nowait = true })
  end
end

-- ---------------------------------------------------------------------------
-- export_report(bufnr)
-- ---------------------------------------------------------------------------

function M.export_report(bufnr)
  bufnr = bufnr or vim.api.nvim_get_current_buf()

  -- Determine filepath from any tool that has it
  local filepath = ""
  local total_flags = 0
  local tool_data = {}

  for tool_name, tool_state in pairs(state) do
    local s = tool_state[bufnr]
    if s then
      if s.filepath and s.filepath ~= "" then
        filepath = s.filepath
      end
      total_flags = total_flags + #s.flags
      table.insert(tool_data, {
        tool     = tool_name,
        flags    = s.flags,
        meta     = s.meta or {},
        flag_count = #s.flags,
      })
    end
  end

  if #tool_data == 0 then
    vim.notify("[quill] No analysis results to export. Run a tool first.", vim.log.levels.WARN)
    return
  end

  table.sort(tool_data, function(a, b) return a.tool < b.tool end)

  local date = os.date("%Y-%m-%d %H:%M")
  local lines = {
    "# Quill Analysis Report",
    "",
    string.format("**File:** `%s`", filepath ~= "" and filepath or "(unsaved buffer)"),
    string.format("**Date:** %s", date),
    string.format("**Total flags:** %d", total_flags),
    "",
    "---",
    "",
    "## Summary",
    "",
    string.format("| %-14s | %-6s | %-8s |", "Tool", "Flags", "Top Sev"),
    string.format("|%s|%s|%s|", string.rep("-", 16), string.rep("-", 8), string.rep("-", 10)),
  }

  for _, td in ipairs(tool_data) do
    local top_sev = 0.0
    for _, flag in ipairs(td.flags) do
      if (flag.severity or 0) > top_sev then top_sev = flag.severity end
    end
    table.insert(lines, string.format(
      "| %-14s | %-6d | %-8.2f |", td.tool, td.flag_count, top_sev
    ))
  end

  -- Readability metrics section
  local has_metrics = false
  local metric_lines = { "", "---", "", "## Readability Metrics", "" }
  for _, td in ipairs(tool_data) do
    local m = td.meta
    if m.readability or m.passive_ratio or m.dominant_tense then
      if not has_metrics then has_metrics = true end
      table.insert(metric_lines, string.format("**%s:**", td.tool))
      if m.readability    then table.insert(metric_lines, string.format("- Flesch-Kincaid: %.1f", m.readability)) end
      if m.passive_ratio  then table.insert(metric_lines, string.format("- Passive ratio: %.1f%%", m.passive_ratio * 100)) end
      if m.dominant_tense then table.insert(metric_lines, string.format("- Dominant tense: %s", m.dominant_tense)) end
      table.insert(metric_lines, "")
    end
  end
  if has_metrics then
    for _, ml in ipairs(metric_lines) do
      table.insert(lines, ml)
    end
  end

  -- Per-tool flag listings
  table.insert(lines, "")
  table.insert(lines, "---")
  table.insert(lines, "")
  table.insert(lines, "## Flags by Tool")

  for _, td in ipairs(tool_data) do
    table.insert(lines, "")
    table.insert(lines, string.format("### %s (%d flags)", td.tool, td.flag_count))
    table.insert(lines, "")
    if td.flag_count == 0 then
      table.insert(lines, "_No flags._")
    else
      -- Sort flags by line/col
      local sorted = vim.deepcopy(td.flags)
      table.sort(sorted, function(a, b)
        if a.s_line ~= b.s_line then return a.s_line < b.s_line end
        return a.s_col < b.s_col
      end)
      for _, flag in ipairs(sorted) do
        -- Output 1-indexed line numbers
        table.insert(lines, string.format(
          "- **L%d:%d** (sev %.2f) %s",
          flag.s_line + 1, flag.s_col, flag.severity or 0, flag.message or ""
        ))
      end
    end
  end

  -- Open report in a new bottom split
  vim.cmd("botright split | enew")
  local rbuf = vim.api.nvim_get_current_buf()
  vim.api.nvim_buf_set_lines(rbuf, 0, -1, false, lines)
  vim.bo[rbuf].buftype  = "nofile"
  vim.bo[rbuf].filetype = "markdown"
  vim.bo[rbuf].swapfile = false
  vim.bo[rbuf].modifiable = false

  vim.notify(
    string.format("[quill] Report written (%d flags across %d tools).", total_flags, #tool_data),
    vim.log.levels.INFO
  )
end

-- ---------------------------------------------------------------------------
-- Flag navigation
-- ---------------------------------------------------------------------------

local function _all_flags_sorted(bufnr)
  local all = {}
  for _, tool_state in pairs(state) do
    local s = tool_state[bufnr]
    if s and s.active then
      for _, flag in ipairs(s.flags) do table.insert(all, flag) end
    end
  end
  table.sort(all, function(a, b)
    return a.s_line < b.s_line or (a.s_line == b.s_line and a.s_col < b.s_col)
  end)
  return all
end

function M.next_flag(bufnr)
  bufnr = bufnr or vim.api.nvim_get_current_buf()
  local all = _all_flags_sorted(bufnr)
  if #all == 0 then vim.notify("[quill] No active flags.", vim.log.levels.WARN); return end
  local row, col = unpack(vim.api.nvim_win_get_cursor(0))
  row = row - 1
  for _, f in ipairs(all) do
    if f.s_line > row or (f.s_line == row and f.s_col > col) then
      vim.api.nvim_win_set_cursor(0, { f.s_line + 1, f.s_col }); return
    end
  end
  local f = all[1]
  vim.api.nvim_win_set_cursor(0, { f.s_line + 1, f.s_col })
  vim.notify("[quill] Wrapped to first flag.", vim.log.levels.INFO)
end

function M.prev_flag(bufnr)
  bufnr = bufnr or vim.api.nvim_get_current_buf()
  local all = _all_flags_sorted(bufnr)
  if #all == 0 then vim.notify("[quill] No active flags.", vim.log.levels.WARN); return end
  local row, col = unpack(vim.api.nvim_win_get_cursor(0))
  row = row - 1
  for i = #all, 1, -1 do
    local f = all[i]
    if f.s_line < row or (f.s_line == row and f.s_col < col) then
      vim.api.nvim_win_set_cursor(0, { f.s_line + 1, f.s_col }); return
    end
  end
  local f = all[#all]
  vim.api.nvim_win_set_cursor(0, { f.s_line + 1, f.s_col })
  vim.notify("[quill] Wrapped to last flag.", vim.log.levels.INFO)
end

return M
