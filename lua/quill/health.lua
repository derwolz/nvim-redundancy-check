-- lua/quill/health.lua
-- :checkhealth quill

local M = {}

function M.check()
  vim.health.start("quill.nvim")

  -- Python executable
  local py = vim.fn.exepath("python3")
  if py == "" then py = vim.fn.exepath("python") end
  if py == "" then
    vim.health.error("python3 not found in PATH")
    return
  end
  vim.health.ok("python: " .. py)

  -- rapidfuzz
  local ver = vim.fn.system({ py, "-c", "import rapidfuzz; print(rapidfuzz.__version__)" })
  if vim.v.shell_error == 0 then
    vim.health.ok("rapidfuzz " .. vim.trim(ver) .. " (fast C++ backend active)")
  else
    vim.health.warn(
      "rapidfuzz not installed — analysis will fall back to pure-Python difflib",
      { "Run :QuillInstallDeps  or  pip install rapidfuzz" }
    )
  end
end

return M
