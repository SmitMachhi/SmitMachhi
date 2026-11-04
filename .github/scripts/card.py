"""Build light + dark stat tiles (one SVG per stat, so each can link somewhere) from GitHub's contribution data.

Usage: python card.py data.json out_dir fonts_dir
data.json is the response to query.graphql (see .github/workflows/stats.yml).
fonts_dir holds IBMPlexMono-Regular.ttf and IBMPlexMono-SemiBold.ttf.
Needs fontTools (pip install fonttools).
"""
import base64
import io
import json
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

THEMES = {
    "light": {"fg": "#1f2328", "muted": "#59636e", "line": "#d1d9e0", "accent": "#0969da"},
    "dark": {"fg": "#f0f6fc", "muted": "#9198a1", "line": "#3d444d", "accent": "#4493f8"},
}
FONT = "'card-mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
W, H = 240, 104  # one tile; README puts three side by side
OSS_MIN_STARS = 100  # repos below this don't count as "open source" for the card


def stats(data):
    user = data["user"]
    oss = [r for r in user["repositoriesContributedTo"]["nodes"] if r["stargazerCount"] >= OSS_MIN_STARS]
    return [
        ("contributions", f"{user['contributionsCollection']['contributionCalendar']['totalContributions']:,}", "", "contributions / yr"),
        ("prs", str(data["merged"]["issueCount"]), "", "prs merged"),
        ("oss", short(sum(r["stargazerCount"] for r in oss)), "★", "oss i contribute to"),
    ]


def short(n):
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def font_face(path, weight, text):
    """Embed only the glyphs the card uses, so each SVG stays a few KB."""
    font = TTFont(path, recalcTimestamp=False)  # same input -> same bytes, so no daily no-op commits
    opts = subset.Options()
    opts.flavor = "woff"
    opts.layout_features = []
    sub = subset.Subsetter(opts)
    sub.populate(text=text)
    sub.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff"
    font.save(buf)
    data = base64.b64encode(buf.getvalue()).decode()
    return f"@font-face{{font-family:'card-mono';font-weight:{weight};src:url(data:font/woff;base64,{data}) format('woff')}}"


def svg(value, mark, label, t, faces, divider):
    star = f'<tspan class="mark" dx="2">{mark}</tspan>' if mark else ""
    line = f'<line x1="0.5" y1="24" x2="0.5" y2="84" stroke="{t["line"]}"/>' if divider else ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{value}{mark} {label}">
<style>
{faces}
text{{font-family:{FONT};text-anchor:middle}}
.num{{font-size:32px;font-weight:600;letter-spacing:-1px;fill:{t['fg']}}}
.mark{{fill:{t['accent']}}}
.label{{font-size:13px;fill:{t['muted']}}}
</style>
{line}<text x="{W / 2}" y="52" class="num">{value}{star}</text><text x="{W / 2}" y="80" class="label">{label}</text>
</svg>
"""


def main():
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["data"]
    out, fonts = Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    cols = stats(data)
    for i, (key, value, mark, label) in enumerate(cols):
        faces = font_face(fonts / "IBMPlexMono-SemiBold.ttf", 600, value + mark) + font_face(
            fonts / "IBMPlexMono-Regular.ttf", 400, label
        )
        for name, theme in THEMES.items():
            (out / f"{key}-{name}.svg").write_text(svg(value, mark, label, theme, faces, divider=i > 0), encoding="utf-8")
    print(ascii(cols))


if __name__ == "__main__":
    main()
