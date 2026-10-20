#!/usr/bin/env python3
"""Generate assets/stats.svg (stats tiles, streak, languages, heatmap, weekly trend) from the GitHub GraphQL API.

The SVG is animated with CSS only (works inside <img> on GitHub), follows the
viewer's light/dark preference and stays static for prefers-reduced-motion.

Usage: GITHUB_TOKEN=... python scripts/generate_stats.py <username> [output.svg]
Standard library only.
"""
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import date
from html import escape

API = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    createdAt
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100, orderBy: {field: STARGAZERS, direction: DESC}) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 5, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

W, H = 1200, 620

STYLE = """<style>
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--fg:#f0f6fc;--muted:#9198a1;--accent:#38bdf8;--track:#21262d;
--l0:#1b2230;--l1:#0c4a6e;--l2:#0369a1;--l3:#0ea5e9;--l4:#7dd3fc}
@media (prefers-color-scheme:light){:root{--bg:#ffffff;--card:#f6f8fa;--line:#d1d9e0;--fg:#1f2328;--muted:#59636e;--accent:#0969da;--track:#eaeef2;
--l0:#ebeef2;--l1:#bae6fd;--l2:#7dd3fc;--l3:#0ea5e9;--l4:#0369a1}}
.t{font-family:-apple-system,'Segoe UI',Inter,Ubuntu,Helvetica,Arial,sans-serif}
.h{font-size:19px;font-weight:700;fill:var(--fg)}
.big{font-size:38px;font-weight:800;fill:var(--fg)}
.lbl{font-size:12px;fill:var(--muted);letter-spacing:.6px}
.name{font-size:15px;fill:var(--fg)}
.tile{fill:var(--card);stroke:var(--line)}
.trk{fill:var(--track)}
.l0{fill:var(--l0)}.l1{fill:var(--l1)}.l2{fill:var(--l2)}.l3{fill:var(--l3)}.l4{fill:var(--l4)}
.f{animation:up .7s cubic-bezier(.2,.7,.2,1) both}
.bar{transform-box:fill-box;transform-origin:left center;animation:grow 1.3s cubic-bezier(.2,.7,.2,1) both}
.c{transform-box:fill-box;transform-origin:center;animation:pop .45s cubic-bezier(.2,.7,.2,1) both}
.ring{animation:ring 1.8s cubic-bezier(.2,.7,.2,1) .3s both}
.draw{animation:draw 2.4s ease-out .6s both}
.area{animation:fade 1.2s ease-out 1.6s both}
.live{transform-box:fill-box;transform-origin:center;animation:live 2s ease-in-out infinite}
.sheen{animation:sheen 6s ease-in-out 1s infinite}
@keyframes up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes grow{from{transform:scaleX(0)}}
@keyframes pop{from{opacity:0;transform:scale(.2)}}
@keyframes fade{from{opacity:0}}
@keyframes draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
@keyframes live{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(1.8)}}
@keyframes sheen{0%{transform:translateX(-400px)}60%,100%{transform:translateX(1400px)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style>"""


def fetch(login: str, token: str) -> dict:
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def streaks(days: list[tuple[date, int]]) -> tuple[int, int]:
    """Return (current_streak, longest_streak). Today without contributions does not break the streak."""
    longest = run = 0
    for _, count in days:
        run = run + 1 if count > 0 else 0
        longest = max(longest, run)
    current = 0
    for idx in range(len(days) - 1, -1, -1):
        if days[idx][1] > 0:
            current += 1
        elif idx == len(days) - 1:
            continue
        else:
            break
    return current, longest


def level(count: int, peak: int) -> str:
    if count == 0:
        return "l0"
    ratio = count / max(peak, 1)
    if ratio < 0.25:
        return "l1"
    if ratio < 0.5:
        return "l2"
    if ratio < 0.75:
        return "l3"
    return "l4"


def render(user: dict) -> str:
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = [
        (date.fromisoformat(d["date"]), d["contributionCount"])
        for w in cal["weeks"]
        for d in w["contributionDays"]
    ]
    current, longest = streaks(days)

    repos = user["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)
    langs: dict[str, list] = defaultdict(lambda: [0, "#38bdf8"])
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            langs[edge["node"]["name"]][0] += edge["size"]
            langs[edge["node"]["name"]][1] = edge["node"]["color"] or "#38bdf8"
    top = sorted(langs.items(), key=lambda kv: kv[1][0], reverse=True)[:6]
    lang_total = sum(v[0] for _, v in top) or 1

    tiles = [
        ("Contributions (12 mo)", cal["totalContributions"]),
        ("Commits", user["contributionsCollection"]["totalCommitContributions"]),
        ("Pull Requests", user["pullRequests"]["totalCount"]),
        ("Issues", user["issues"]["totalCount"]),
        ("Stars", stars),
        ("Repos", user["repositories"]["totalCount"]),
    ]

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="GitHub statistics">',
        f"""<defs><clipPath id="clip"><rect width="{W}" height="{H}" rx="14"/></clipPath>
<linearGradient id="acc" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#0ea5e9"/><stop offset="1" stop-color="#a78bfa"/></linearGradient>
<linearGradient id="fillg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#38bdf8" stop-opacity=".35"/><stop offset="1" stop-color="#38bdf8" stop-opacity="0"/></linearGradient>
<linearGradient id="sh" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".07"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>""",
        STYLE,
        f'<g clip-path="url(#clip)"><rect width="{W}" height="{H}" style="fill:var(--bg)"/>',
    ]

    # tiles
    out.append('<text x="40" y="48" class="t h f">Activity snapshot</text>')
    for i, (label, value) in enumerate(tiles):
        x = 40 + i * 188
        out.append(
            f'<g class="f t" style="animation-delay:{0.1 + i * 0.1:.2f}s">'
            f'<rect x="{x}" y="66" width="172" height="100" rx="12" class="tile"/>'
            f'<rect x="{x}" y="66" width="172" height="3" rx="1.5" fill="url(#acc)"/>'
            f'<text x="{x + 16}" y="118" class="big">{value:,}</text>'
            f'<text x="{x + 16}" y="146" class="lbl">{escape(label.upper())}</text></g>'
        )

    # streak ring
    cx, cy, r = 150, 312, 62
    circ = 2 * 3.14159 * r
    ratio = min(current / max(longest, 1), 1) if current else 0
    out.append('<text x="40" y="222" class="t h f" style="animation-delay:.6s">Streak</text>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke-width="10" style="stroke:var(--track)"/>')
    out.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="url(#acc)" stroke-width="10" stroke-linecap="round" '
        f'stroke-dasharray="{circ:.1f} {circ:.1f}" stroke-dashoffset="{circ * (1 - ratio):.1f}" '
        f'transform="rotate(-90 {cx} {cy})" class="ring" style="--c:{circ:.1f}"/>'
    )
    out.append(f'<style>@keyframes ring{{from{{stroke-dashoffset:{circ:.1f}}}}}</style>')
    out.append(f'<text x="{cx}" y="{cy + 13}" text-anchor="middle" class="t big f" style="animation-delay:.8s">{current}</text>')
    out.append(f'<text x="{cx}" y="{cy + 98}" text-anchor="middle" class="t lbl f" style="animation-delay:.9s">CURRENT STREAK (DAYS)</text>')
    out.append(f'<text x="{cx}" y="{cy + 118}" text-anchor="middle" class="t lbl f" style="animation-delay:1s">LONGEST: {longest}</text>')

    # languages
    out.append('<text x="330" y="222" class="t h f" style="animation-delay:.7s">Top languages</text>')
    if not top:
        out.append('<text x="330" y="256" class="t lbl">NO LANGUAGE DATA YET</text>')
    for i, (name, (size, color)) in enumerate(top):
        pct = size / lang_total * 100
        y = 254 + i * 34
        delay = 0.8 + i * 0.12
        out.append(f'<g class="f" style="animation-delay:{delay:.2f}s">')
        out.append(f'<circle cx="335" cy="{y - 5}" r="5" fill="{escape(color)}"/>')
        out.append(f'<text x="348" y="{y}" class="t name">{escape(name)}</text>')
        out.append(f'<text x="660" y="{y}" text-anchor="end" class="t lbl">{pct:.1f}%</text></g>')
        out.append(f'<rect x="330" y="{y + 8}" width="330" height="7" rx="3.5" class="trk"/>')
        out.append(
            f'<rect x="330" y="{y + 8}" width="{max(330 * pct / 100, 7):.1f}" height="7" rx="3.5" fill="{escape(color)}" '
            f'class="bar" style="animation-delay:{delay + 0.1:.2f}s"/>'
        )

    # heatmap (last 26 weeks)
    weeks = cal["weeks"][-26:]
    recent = [d["contributionCount"] for w in weeks for d in w["contributionDays"]]
    peak = max(recent, default=0)
    out.append('<text x="720" y="222" class="t h f" style="animation-delay:.8s">Last 26 weeks</text>')
    for wi, week in enumerate(weeks):
        for day in week["contributionDays"]:
            di = date.fromisoformat(day["date"]).isoweekday() % 7
            out.append(
                f'<rect x="{720 + wi * 17}" y="{240 + di * 17}" width="14" height="14" rx="3" '
                f'class="c {level(day["contributionCount"], peak)}" style="animation-delay:{0.9 + wi * 0.035 + di * 0.02:.2f}s">'
                f'<title>{day["date"]}: {day["contributionCount"]}</title></rect>'
            )
    out.append('<g class="f" style="animation-delay:1.9s">')
    out.append('<text x="720" y="392" class="t lbl">LESS</text>')
    for i in range(5):
        out.append(f'<rect x="{758 + i * 17}" y="381" width="14" height="14" rx="3" class="l{i}"/>')
    out.append('<text x="848" y="392" class="t lbl">MORE</text>')
    out.append(
        f'<text x="1162" y="392" text-anchor="end" class="t lbl">{sum(recent):,} IN 26 WEEKS · BEST DAY {peak}</text></g>'
    )

    # weekly trend over 12 months
    totals = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cal["weeks"]]
    top_week = max(totals, default=0) or 1
    x0, x1, y0, y1 = 40, 1160, 590, 470
    step = (x1 - x0) / max(len(totals) - 1, 1)
    pts = [(x0 + i * step, y0 - (t / top_week) * (y0 - y1)) for i, t in enumerate(totals)]
    line = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    out.append('<text x="40" y="450" class="t h f" style="animation-delay:1.2s">Weekly contributions · 12 months</text>')
    out.append(f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" style="stroke:var(--line)"/>')
    if pts:
        out.append(f'<path d="{line} L{x1},{y0} L{x0},{y0} Z" fill="url(#fillg)" class="area"/>')
        out.append(
            f'<path d="{line}" fill="none" stroke="url(#acc)" stroke-width="2.5" stroke-linejoin="round" '
            f'pathLength="1" stroke-dasharray="1" class="draw"/>'
        )
        lx, ly = pts[-1]
        out.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" style="fill:var(--accent)" class="live"/>')
        out.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" style="fill:var(--accent)"/>')

    # footer + sheen
    out.append(f'<circle cx="514" cy="606" r="3" fill="#22c55e" class="live"/>')
    out.append(
        f'<text x="600" y="610" text-anchor="middle" class="t lbl" style="font-size:11px">updated {date.today().isoformat()} via GitHub Actions</text>'
    )
    out.append(f'<rect x="0" y="0" width="400" height="{H}" fill="url(#sh)" class="sheen"/>')
    out.append("</g>")
    out.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" style="stroke:var(--line)"/></svg>')
    return "\n".join(out)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: generate_stats.py <username> [output.svg]")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")
    target = sys.argv[2] if len(sys.argv) > 2 else "assets/stats.svg"
    svg = render(fetch(sys.argv[1], token))
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(svg)
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
