# PDF fonts (Arabic / Persian)

`NotoSansArabic-Regular.ttf` and `Vazirmatn-Regular.ttf` are static
(weight 400) instances of Google's open-source (OFL-licensed) variable
fonts, each merged from two of that family's official unicode-range
subsets -- the Arabic-script subset (for shaping: both retain their
GSUB/GPOS tables) and the Basic Latin subset (so company names,
amounts, and any not-yet-translated Latin text in the same PDF still
render instead of showing as empty boxes).

Source: the woff2 files Next.js's own `next/font/google` self-hosting
already downloads into `frontend/.next/static/media/` when the frontend
(which uses these same two families for Persian/Arabic UI text, see
`frontend/app/layout.tsx`) is built or run in dev -- not fetched
separately for this purpose.

Regenerate (after a `npm run build` or `npm run dev` in `frontend/`, so
`.next/static/media/` is populated) with `fonttools` + `brotli` (not a
runtime dependency of this backend, only needed for this one-time
conversion -- `pip install fonttools brotli` into a scratch venv):

```python
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.merge import Merger

def to_static(src, dst):
    font = TTFont(src)
    if "fvar" in font:
        font = instantiateVariableFont(font, {"wght": 400.0}, inplace=True)
    font.flavor = None
    font.save(dst)
    return dst

# Find the two source woff2 paths by grepping frontend/.next's generated
# CSS for "Noto Sans Arabic" / "Vazirmatn" @font-face blocks: the one
# whose unicode-range includes U+600-6FF (Arabic script) and the one
# whose unicode-range includes U+00-FF (Basic Latin).
a = to_static("<arabic-range subset woff2>", "/tmp/_a.ttf")
l = to_static("<basic-latin subset woff2>", "/tmp/_l.ttf")
Merger().merge([a, l]).save("NotoSansArabic-Regular.ttf")  # or Vazirmatn-Regular.ttf
```
