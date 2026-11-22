"""Build light + dark OP-1 Punch (Boxer) GitHub telemetry SVGs from contribution data.

Usage: python card.py data.json out_dir fonts_dir
data.json is the response to query.graphql (see .github/workflows/stats.yml).
fonts_dir holds IBMPlexMono-Regular.ttf and IBMPlexMono-SemiBold.ttf.
Needs fontTools (pip install fonttools).
"""
import base64
import io
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ACCENT = "#e04545"
THEMES = {
    "light": {
        "bg": "#ffffff",
        "fg": "#1f2328",
        "body": "#1a8754",
        "wire": "#6b6399",
        "dim": "#dfe4ec",
        "accent": ACCENT,
    },
    "dark": {
        "bg": "#0d1117",
        "fg": "#f0f6fc",
        "body": "#68c796",
        "wire": "#7b75ad",
        "dim": "#262c36",
        "accent": ACCENT,
    },
}
FONT = "'card-mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
W, H = 720, 290
OSS_MIN_STARS = 100  # repos below this don't count as "open source" for the card


def short(n):
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def extract_metrics(data):
    user = data["user"]
    cal = user["contributionsCollection"]["contributionCalendar"]
    weeks = cal["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]

    # 12 monthly rounds (last 12 calendar months in order)
    by_month = defaultdict(int)
    for d in days:
        by_month[d["date"][:7]] += d["contributionCount"]
    months = [by_month[k] for k in sorted(by_month)[-12:]]

    # Active days in the last 7 days (drives the 7 head focus sparks)
    last7 = days[-7:]
    active_days_7 = sum(1 for d in last7 if d["contributionCount"] > 0)
    last7_sum = sum(d["contributionCount"] for d in last7)

    # Weekly pace needle fraction (0.12 .. 0.94) vs 52-week average & peak
    week_sums = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks]
    peak_week = max(week_sums) if week_sums else 1
    avg_week = (sum(week_sums) / len(week_sums)) if week_sums else 1
    # Map 0 -> 0.12, avg -> 0.52, peak -> 0.94 smoothly
    if last7_sum <= avg_week:
        pace_frac = 0.12 + 0.40 * (last7_sum / max(1.0, avg_week))
    else:
        pace_frac = 0.52 + 0.42 * ((last7_sum - avg_week) / max(1.0, peak_week - avg_week))
    pace_frac = max(0.12, min(0.94, pace_frac))

    oss = [
        r
        for r in user["repositoriesContributedTo"]["nodes"]
        if r and r["stargazerCount"] >= OSS_MIN_STARS
    ]  # r is None for repos the token cannot open

    return {
        "contributions": f"{cal['totalContributions']:,}",
        "prs": str(data["merged"]["issueCount"]),
        "oss": short(sum(r["stargazerCount"] for r in oss)) + "★",
        "months": months,
        "active_days_7": active_days_7,
        "pace_frac": pace_frac,
    }


def font_face(path, weight, text):
    """Embed only the glyphs the card uses, so each SVG stays compact."""
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
    encoded = base64.b64encode(buf.getvalue()).decode()
    return (
        f"@font-face{{font-family:'card-mono';font-weight:{weight};"
        f"src:url(data:font/woff;base64,{encoded}) format('woff')}}"
    )


def pace_gauge(cx, cy, frac, t):
    ticks = []
    for deg in (-180, -135, -90, -45, 0):
        a = math.radians(deg)
        x1, y1 = cx + 19 * math.cos(a), cy + 19 * math.sin(a)
        x2, y2 = cx + 26 * math.cos(a), cy + 26 * math.sin(a)
        ticks.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{t["body"]}" stroke-width="1.8" stroke-linecap="round"/>'
        )
    na = math.radians(-180 + frac * 180)
    nx, ny = cx + 22 * math.cos(na), cy + 22 * math.sin(na)
    return (
        "".join(ticks)
        + f'<line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" '
        f'stroke="{t["accent"]}" stroke-width="2" stroke-linecap="round"/>'
        + f'<circle cx="{cx}" cy="{cy}" r="3.2" fill="{t["accent"]}"/>'
    )


def boxer_svg(m, t, faces):
    # 7 radiating focus sparks above boxer's head = active days in the last 7 days
    head_ticks = []
    for idx, deg in enumerate((-58, -38, -19, 0, 19, 38, 58)):
        a = math.radians(deg - 90)
        x1, y1 = 340 + 36 * math.cos(a), 76 + 36 * math.sin(a)
        x2, y2 = 340 + 49 * math.cos(a), 76 + 49 * math.sin(a)
        lit = idx < m["active_days_7"]
        if not lit:
            col = t["dim"]
        elif idx == m["active_days_7"] - 1:
            col = t["accent"]
        else:
            col = t["wire"]
        head_ticks.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{col}" stroke-width="2" stroke-linecap="round"/>'
        )

    # 12 monthly rounds vertical meter (bottom = oldest month, top = current round)
    months = m["months"] or [0] * 12
    max_m = max(months) or 1
    meter_x = 486
    meter_bars = []
    for i, val in enumerate(months):
        y = 198 - i * 13
        norm = val / max_m
        is_now = i == len(months) - 1
        is_peak = val == max_m and val > 0
        if is_now:
            col = t["accent"]
        elif is_peak:
            col = t["fg"]
        elif val > 100:
            col = t["body"]
        else:
            col = t["wire"]
        op = max(0.25, 0.35 + norm * 0.65)
        cls = ' class="pulse"' if is_now else ""
        meter_bars.append(
            f'<line x1="{meter_x}" y1="{y}" x2="{meter_x + 22}" y2="{y}" '
            f'stroke="{col}" stroke-width="2.6" stroke-linecap="round" opacity="{op:.2f}"{cls}/>'
        )

    # Dynamic start X for PRs wire so 2-, 3-, or 4-digit PR counts never collide
    prs_digits = len(m["prs"])
    prs_font = 58 if prs_digits <= 2 else (48 if prs_digits == 3 else 40)
    prs_wire_x = min(192, 34 + int(prs_digits * prs_font * 0.62) + 14)

    aria = f"{m['contributions']} contributions/yr, {m['prs']} prs landed, {m['oss']} oss reach"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{aria}">
<style>
{faces}
text{{font-family:{FONT}}}
@keyframes bob{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-2.5px)}}}}
@keyframes jab{{0%,82%,100%{{transform:translate(0,0)}}89%{{transform:translate(-4px,1.5px)}}94%{{transform:translate(0,0)}}}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.38}}}}
.bob{{animation:bob 3s ease-in-out infinite}}
.jab{{animation:jab 4.8s ease-in-out infinite}}
.pulse{{animation:pulse 2.4s ease-in-out infinite}}
</style>
<text x="34" y="48" fill="{t['wire']}" font-size="15" font-weight="600" letter-spacing="1.6">PACE</text>
{pace_gauge(64, 96, m['pace_frac'], t)}
<polyline points="104,42 192,42 266,94" fill="none" stroke="{t['wire']}" stroke-width="1.6" stroke-linejoin="round"/>
<circle cx="266" cy="94" r="3.8" fill="{t['wire']}"/>
<text x="34" y="160" fill="{t['wire']}" font-size="14" font-weight="600" letter-spacing="1.4">PRS LANDED</text>
<text x="32" y="228" fill="{t['body']}" font-size="{prs_font}" font-weight="400" letter-spacing="-2">{m['prs']}</text>
<polyline points="{prs_wire_x},222 196,222 296,192" fill="none" stroke="{t['wire']}" stroke-width="1.6" stroke-linejoin="round"/>
<circle cx="296" cy="192" r="3.8" fill="{t['wire']}"/>
<g class="bob">
{"".join(head_ticks)}
<path d="M 322 72 C 322 52, 358 52, 358 72 L 357 86 C 357 100, 349 112, 340 112 C 331 112, 323 100, 323 86 Z" fill="{t['bg']}" stroke="{t['body']}" stroke-width="2" stroke-linejoin="round"/>
<path d="M 322 78 C 317 78, 317 89, 322 90" fill="none" stroke="{t['body']}" stroke-width="1.8" stroke-linecap="round"/>
<path d="M 358 78 C 363 78, 363 89, 358 90" fill="none" stroke="{t['body']}" stroke-width="1.8" stroke-linecap="round"/>
<line x1="329" y1="81" x2="337" y2="83" stroke="{t['wire']}" stroke-width="2" stroke-linecap="round"/>
<line x1="351" y1="81" x2="343" y2="83" stroke="{t['wire']}" stroke-width="2" stroke-linecap="round"/>
<line x1="338" y1="92" x2="342" y2="92" stroke="{t['body']}" stroke-width="1.6" stroke-linecap="round"/>
<path d="M 334 100 Q 340 97 346 100" fill="none" stroke="{t['body']}" stroke-width="1.6" stroke-linecap="round"/>
<path d="M 326 108 L 288 122 C 272 128, 258 148, 248 176 L 268 188 L 284 166" fill="none" stroke="{t['body']}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M 354 108 L 386 122 C 402 130, 408 148, 404 166" fill="none" stroke="{t['body']}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M 294 148 Q 320 162 346 154" fill="none" stroke="{t['body']}" stroke-width="1.6" stroke-linecap="round"/>
<path d="M 346 154 Q 368 158 380 144" fill="none" stroke="{t['body']}" stroke-width="1.6" stroke-linecap="round"/>
<path d="M 298 164 L 296 208 M 372 162 L 368 206" fill="none" stroke="{t['body']}" stroke-width="1.7" stroke-linecap="round"/>
<path d="M 284 226 L 272 268 M 374 222 L 406 268 M 326 248 L 336 268" fill="none" stroke="{t['fg']}" stroke-width="1.9" stroke-linecap="round"/>
<path d="M 292 228 L 284 268" fill="none" stroke="{t['wire']}" stroke-width="1.5" stroke-linecap="round"/>
<g>
<path d="M 380 172 C 384 150, 412 140, 434 150 C 452 158, 456 184, 444 198 C 430 212, 400 210, 386 198 Z" fill="{t['bg']}" stroke="{t['accent']}" stroke-width="2.2" stroke-linejoin="round"/>
<path d="M 374 176 L 392 170 L 398 198 L 380 202 Z" fill="{t['bg']}" stroke="{t['fg']}" stroke-width="1.6"/>
<line x1="382" y1="184" x2="389" y2="191" stroke="{t['fg']}" stroke-width="1.4"/>
<line x1="389" y1="184" x2="382" y2="191" stroke="{t['fg']}" stroke-width="1.4"/>
</g>
<g class="jab">
<path d="M 278 176 C 288 158, 326 154, 348 168 C 366 180, 366 206, 348 220 C 330 234, 294 232, 280 212 Z" fill="{t['bg']}" stroke="{t['accent']}" stroke-width="2.3" stroke-linejoin="round"/>
<path d="M 288 178 C 304 172, 322 178, 326 190" fill="none" stroke="{t['accent']}" stroke-width="1.6" stroke-linecap="round"/>
<path d="M 262 184 L 284 174 L 292 206 L 270 212 Z" fill="{t['bg']}" stroke="{t['fg']}" stroke-width="1.6"/>
</g>
</g>
{"".join(meter_bars)}
<rect x="{meter_x - 6}" y="232" width="34" height="24" fill="none" stroke="{t['wire']}" stroke-width="1.5"/>
<text x="{meter_x + 11}" y="248" text-anchor="middle" fill="{t['wire']}" font-size="11" font-weight="600" letter-spacing="0.8">12R</text>
<text x="686" y="48" text-anchor="end" fill="{t['body']}" font-size="13.5" font-weight="600" letter-spacing="1.2">CONTRIB / YR</text>
<text x="688" y="112" text-anchor="end" fill="{t['fg']}" font-size="44" font-weight="400" letter-spacing="-2">{m['contributions']}</text>
<text x="686" y="162" text-anchor="end" fill="{t['body']}" font-size="13.5" font-weight="600" letter-spacing="1.2">OSS REACH</text>
<text x="688" y="226" text-anchor="end" fill="{t['accent']}" font-size="44" font-weight="400" letter-spacing="-2">{m['oss']}</text>
</svg>
"""


def main():
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))["data"]
    out, fonts = Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    m = extract_metrics(data)

    regular_chars = m["contributions"] + m["prs"] + m["oss"]
    semibold_chars = "PACE PRS LANDED 12R CONTRIB / YR OSS REACH"
    faces = font_face(fonts / "IBMPlexMono-Regular.ttf", 400, regular_chars) + font_face(
        fonts / "IBMPlexMono-SemiBold.ttf", 600, semibold_chars
    )

    for name, theme in THEMES.items():
        (out / f"boxer-{name}.svg").write_text(boxer_svg(m, theme, faces), encoding="utf-8")

    print(ascii({k: m[k] for k in ("contributions", "prs", "oss", "active_days_7")}))


if __name__ == "__main__":
    main()
