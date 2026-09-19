--[[
  Give every page a META DESCRIPTION, because for a code nobody has heard of yet, almost nobody
  arrives at the front door. They arrive from a search for their own problem — "Zick Homsy sphere
  array permeability", "cut-cell immersed boundary python" — and land in the middle of the site.
  Without a description, the search result shows whatever snippet the engine invents.

  WHY A FILTER AND NOT A LINE IN EACH .qmd — the same reason as _download-badge.lua, and it is
  worth restating because it has already cost this repository two reverted attempts (2026-09-14/15).
  `execute: freeze: auto` keys the cached document on an md5 of the .qmd. Adding `description:` to
  55 front matters would invalidate all 55 freezes; the Pages build has no solver, so it would try
  to re-execute them and fail — and two of those pages are GPU-hours. A filter runs at RENDER time,
  on the document Quarto has already assembled, frozen or fresh. No page source changes, so no
  freeze is touched.

  WHAT IT DOES. Every page here carries a `subtitle` and none carries a `description`; the
  subtitles already read like meta descriptions. Search engines display roughly 160 characters and
  the median subtitle is 212, so an over-long one is cut at the last sentence end past about
  two-thirds of the limit, or failing that at a word boundary with an ellipsis. Never mid-word, and
  never mid-character: the limit is in characters, not bytes — these subtitles are full of em dashes.

  The sentence rule has a floor because a short first sentence is usually the hook while the second
  carries the searchable terms: "Give a box of grains a random kick and let inelastic collisions
  bleed the energy away." says nothing about CFD–DEM, Haff's law or MFIX-Exa.

  `hide-description` is set alongside, because Quarto's HTML title block otherwise DISPLAYS the
  description beneath the subtitle (share/formats/html/templates/title-block.html), and a truncated
  copy of the subtitle directly under the subtitle is not what anyone wants. The <meta> tag in
  <head> is unaffected by it.

  A closing "Run this yourself / pip install peclet" block was tried here as well and CUT
  (2026-09-19): 41 of 46 examples already open with a Colab badge and 27 pages close with the style
  guide's "Reproduce this" section, so it duplicated one or both; on the Snellius benchmark pages
  its claim that the page runs from the released package was false. The five examples that have
  neither fall under the style guide's rule, to be added when each page is next re-executed.
]]

local LIMIT = 160          -- characters: what a search result displays before it clips
local FLOOR = 0.65         -- a sentence end counts only past this fraction of LIMIT

-- Position of the last match of `pat` in `s`, or nil.
local function last_match(s, pat)
  return s:match("^.*()" .. pat)
end

-- Strip trailing whitespace, ASCII punctuation, and the multi-byte dashes the subtitles favour
-- (a Lua character class cannot hold a multi-byte character, hence the separate patterns).
local TAIL = { "[%s%p]+$", "—$", "–$" }
local function trim_tail(s)
  local changed
  repeat
    changed = false
    for _, pat in ipairs(TAIL) do
      local n
      s, n = s:gsub(pat, "")
      if n > 0 then changed = true end
    end
  until not changed
  return s
end

local function shorten(s)
  local len = utf8.len(s)
  if not len or len <= LIMIT then return s end
  local head = s:sub(1, utf8.offset(s, LIMIT + 1) - 1)        -- the first LIMIT characters, whole
  local floor = utf8.offset(s, math.floor(LIMIT * FLOOR))     -- as a byte offset into `s`
  -- prefer a sentence end, so the description reads as a finished thought
  local cut = last_match(head, "[%.!?] ")
  if cut and cut >= floor then return s:sub(1, cut) end
  -- otherwise the last word boundary, with an ellipsis to show it continues
  cut = last_match(head, "%s")
  if cut and cut >= floor then return trim_tail(s:sub(1, cut - 1)) .. "…" end
  return trim_tail(head) .. "…"
end

function Pandoc(doc)
  local meta = doc.meta
  if meta.description or not meta.subtitle then return nil end
  meta.description = pandoc.MetaString(shorten(pandoc.utils.stringify(meta.subtitle)))
  meta["hide-description"] = pandoc.MetaBool(true)
  return doc
end
