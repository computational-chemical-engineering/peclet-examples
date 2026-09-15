--[[
  Add a "Download notebook" badge beside the "Open In Colab" badge, on every page that has one.

  WHY A FILTER AND NOT A LINE IN EACH .qmd. `execute: freeze: auto` caches the WHOLE rendered
  document — `_freeze/<page>/execute-results/html.json` holds `result.markdown`, which starts at
  `---\ntitle:` and runs to the end of the page — keyed on an md5 of the .qmd. So editing a page to
  add a badge either invalidates the cache (and the Pages build, which has no solver, tries to
  re-run the simulation and fails) or, if the hash is patched to match, publishes the cached document
  and the edit never appears at all. Both were tried on 2026-09-14/15 and both were reverted.

  A filter sidesteps the whole problem: it runs at RENDER time, on the document Quarto has already
  assembled — frozen or fresh, it does not care. No page source changes, so no freeze is touched.

  WHAT IT LOOKS FOR. The badge paragraph every example opens with:

      [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](...){target="_blank"}
      &nbsp;Runs on a free Colab CPU runtime — ...

  It appends a second badge to that same paragraph, so the two sit side by side.

  WHERE IT POINTS. `index.ipynb`, relative — the notebook is published next to the page by the
  `resources` entry in _quarto.yml, so the link is SAME-ORIGIN and the HTML5 `download` attribute is
  honoured: one click saves the file. (`download` is ignored cross-origin, which is why pointing at
  raw.githubusercontent or jsDelivr cannot work; and raw.githubusercontent serves .ipynb as
  text/plain, so it renders JSON in the browser instead of saving.)

  The filename is taken from the page's own directory, so the reader gets `poiseuille-ibm.ipynb`
  rather than 44 files all called `index.ipynb`.
]]

local BADGE_SRC = "https://img.shields.io/badge/Download-notebook-F37626?logo=jupyter&logoColor=white"

-- The directory name of the page being rendered, e.g. "poiseuille-ibm".
local function page_slug()
  local input = quarto.doc.input_file or ""
  local dir = input:match("([^/\\]+)[/\\][^/\\]+$")
  return dir or "notebook"
end

-- Does this paragraph carry the Colab badge?
local function has_colab_badge(para)
  local found = false
  pandoc.walk_block(para, {
    Image = function(img)
      if img.src:find("colab%-badge") then found = true end
    end,
    Link = function(link)
      if link.target:find("colab%.research%.google%.com") then found = true end
    end,
  })
  return found
end

local added = false

function Para(para)
  if added or not has_colab_badge(para) then
    return nil
  end
  added = true

  local img = pandoc.Image({ pandoc.Str("Download notebook") }, BADGE_SRC, "Download notebook")
  local link = pandoc.Link({ img }, "index.ipynb", "", {
    download = page_slug() .. ".ipynb",   -- same-origin => the browser saves rather than navigates
    title = "Download this page as a Jupyter notebook",
  })

  -- Insert right after the Colab badge, before the "Runs on a free Colab CPU runtime" prose, so the
  -- two badges read as a pair. The Colab link is the first Link in the paragraph.
  local out = {}
  local placed = false
  for _, el in ipairs(para.content) do
    table.insert(out, el)
    if not placed and el.t == "Link" then
      table.insert(out, pandoc.Space())
      table.insert(out, link)
      placed = true
    end
  end
  if not placed then
    table.insert(out, pandoc.Space())
    table.insert(out, link)
  end
  return pandoc.Para(out)
end
