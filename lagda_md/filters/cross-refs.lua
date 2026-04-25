-- cross-refs.lua
-- Optional Pandoc Lua filter for projects whose .lagda sources use
-- \label, \Cref / \cref, and \caption.  Layered on top of agda-filter.lua
-- when the user passes --enable-cross-refs to convert_lagda.py.
--
-- Transforms:
--   \label{target}       -> <a id="sanitized_target"></a>
--   \Cref{a,b,...}       -> Markdown links with prefix ("Figure", "Section", etc.)
--   \cref{a,b,...}       -> identical, lowercase form
--   \caption{text}       -> Span with class "caption-text" and bold "Caption:" prefix

local function sanitize(target)
  return target:gsub("[^%w%-_%.%:]", "_")
end

local function make_attrs(classes)
  classes = classes or {}
  if type(pandoc.Attr) == "function" then
    return pandoc.Attr("", classes, {})
  else
    return {"", classes, {}}
  end
end

local function infer_prefix(target)
  if     target:match("^fig:") then return "Figure"
  elseif target:match("^sec:") then return "Section"
  elseif target:match("^tbl:") then return "Table"
  elseif target:match("^eq:")  then return "Equation"
  else                              return "Ref."
  end
end

local function transform_latex_command(text)
  -- \label{target}
  local label_target = text:match("^\\label%s*{(.-)}$")
  if label_target then
    return pandoc.RawInline("html", '<a id="' .. sanitize(label_target) .. '"></a>')
  end

  -- \Cref{a,b,...} or \cref{a,b,...}
  local cref_targets = text:match("^\\[Cc]ref%s*{(.-)}$")
  if cref_targets then
    local inlines = {}
    local first = true
    for target in cref_targets:gmatch("([^,]+)") do
      target = target:match("^%s*(.-)%s*$")
      if not first then
        table.insert(inlines, pandoc.Str(","))
        table.insert(inlines, pandoc.Space())
      end
      first = false
      local link_text = {
        pandoc.Str(infer_prefix(target)),
        pandoc.Space(),
        pandoc.Str(target),
      }
      table.insert(inlines, pandoc.Link(link_text, "#" .. sanitize(target)))
    end
    if #inlines == 1 then return inlines[1] end
    return pandoc.Span(inlines)
  end

  -- \caption{text}
  local caption_text = text:match("^\\caption%s*{(.*)}$")
  if caption_text then
    return pandoc.Span(
      {
        pandoc.Strong(pandoc.Str("Caption:")),
        pandoc.Space(),
        pandoc.Str(caption_text),
      },
      make_attrs({"caption-text"})
    )
  end

  return nil
end

function RawInline(inline)
  if inline.format and inline.format:match("latex") then
    local result = transform_latex_command(inline.text)
    if result then return result end
  end
  return inline
end
