-- agda-filter.lua
-- Pandoc Lua filter for the agda-lagda-migrator package.
--
-- This is the slimmed default filter, handling only the universal case:
-- @@AgdaTerm@@ markers emitted by lagda_md.preprocess for Agda identifiers
-- in prose are converted into Code elements with the appropriate CSS class.
--
-- Projects whose .lagda sources use \label, \Cref, or \caption can layer
-- the optional `cross-refs.lua` filter on top of this one to handle those
-- constructs.
--
-- The full FLS-shaped filter (with HighlightPlaceholder and other
-- FLS-specific handlers) lives at examples/fls-pipeline/agda-filter.lua.

--- Parses key=value pairs from an AgdaTerm marker payload.
--  Example input: "basename=Acnt@@class=AgdaRecord"
--  @return table mapping keys to values.
local function parse_agda_term_payload(text)
  local args = {}
  -- Split on @@ field separator.  Preserves single @ characters
  -- (which arise from the @@ → @ @ escape applied by preprocess).
  local position = 1
  while position <= #text do
    local separator_start, separator_end = text:find("@@", position, true)
    local field
    if separator_start then
      field = text:sub(position, separator_start - 1)
      position = separator_end + 1
    else
      field = text:sub(position)
      position = #text + 1
    end
    local key, value = field:match("^([^=]+)=(.*)$")
    if key then
      key = key:match("^%s*(.-)%s*$")
      value = value:match("^%s*(.-)%s*$")
      args[key] = value
    end
  end
  return args
end

--- Constructs a Pandoc attribute structure compatible with both 2.x and 3.x.
local function make_attrs(classes)
  classes = classes or {}
  local identifier = ""
  local kv = {}
  if type(pandoc.Attr) == "function" then
    return pandoc.Attr(identifier, classes, kv)
  else
    return {identifier, classes, kv}
  end
end

--- Reverses the @@ -> @ @ escape applied by lagda_md.preprocess.
local function unescape(text)
  return (text:gsub("@ @", "@@"))
end

--- Processes Code inline elements containing AgdaTerm markers.
--  Input shape: <code>@@AgdaTerm@@basename=NAME@@class=CLASS@@</code>.
--  Output: a Code element with text=NAME and CSS class=CLASS.
function Code(inline)
  local payload = inline.text:match("^%s*@@AgdaTerm@@(.-)@@%s*$")
  if not payload then
    return inline
  end

  local args = parse_agda_term_payload(payload)
  if args.basename and args["class"] then
    return pandoc.Code(unescape(args.basename), make_attrs({args["class"]}))
  end

  io.stderr:write("Warning: malformed AgdaTerm payload: " .. payload .. "\n")
  return inline
end

--- Walks Div elements to ensure inline handlers fire on inner content,
--  and adds markdown="1" to theorem-class divs (a Pandoc convention that
--  lets the Markdown writer process Markdown content nested inside HTML).
function Div(div)
  for _, class in ipairs(div.classes) do
    if class == "theorem" then
      div.attributes["markdown"] = "1"
      break
    end
  end
  return pandoc.walk_block(div, { Code = Code })
end
