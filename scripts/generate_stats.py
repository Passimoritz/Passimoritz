#!/usr/bin/env python3
"""Generate assets/stats.svg (stats card, streak, languages, heatmap) from the GitHub GraphQL API.

Usage: GITHUB_TOKEN=... python scripts/generate_stats.py <username> [output.svg]
Standard library only.
"""
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import date, timedelta

API = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    createdAt
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(ownerType: OWNER, isFork: false, first: 100, orderBy: {field: STARGAZERS, direction: DESC}) {
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
        return "#161b22"
    ratio = count / max(peak, 1)
    if ratio < 0.25:
        return "#0c4a6e"
    if ratio < 0.5:
        return "#0369a1"
    if ratio < 0.75:
        return "#0ea5e9"
    return "#7dd3fc"


def render(user: dict) -> str:
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = [
        (date.fromisoformat(d["date"]), d["contributionCount"])
        for w in cal["weeks"]
        for d in w["contributionDays"]
    ]
    current, longest = streaks(days)
    peak = max((c for _, c in days), default=1)

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

    out = []
    w, h = 1200, 560
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="GitHub statistics">')
    out.append("""<defs><clipPath id="c"><rect width="1200" height="560" rx="16"/></clipPath>
<linearGradient id="a" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#0ea5e9"/><stop offset="1" stop-color="#a78bfa"/></linearGradient></defs>
<style>
.t{font-family:'Segoe UI',Inter,Ubuntu,Helvetica,Arial,sans-serif}
.h{font-size:20px;font-weight:700;fill:#38bdf8}
.big{font-size:40px;font-weight:800;fill:#fff}
.lbl{font-size:13px;fill:#94a3b8;letter-spacing:.5px}
.f{}
.pulse{}
</style>""")
    out.append('<g clip-path="url(#c)"><rect width="1200" height="560" fill="#0b1120"/>')

    # tiles
    out.append('<text x="40" y="50" class="t h">Activity snapshot</text>')
    for i, (label, value) in enumerate(tiles):
        x = 40 + i * 188
        out.append(
            f'<g class="f t" style="animation-delay:{i*0.12:.2f}s">'
            f'<rect x="{x}" y="70" width="172" height="96" rx="12" fill="#111827" stroke="#1f2a44"/>'
            f'<text x="{x+16}" y="120" class="big">{value}</text>'
            f'<text x="{x+16}" y="146" class="lbl">{label.upper()}</text></g>'
        )

    # streak ring
    cx, cy, r = 150, 300, 62
    out.append('<text x="40" y="228" class="t h">Streak</text>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#1e293b" stroke-width="10"/>')
    ratio = min(current / max(longest, 1), 1)
    circ = 2 * 3.14159 * r
    out.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="url(#a)" stroke-width="10" stroke-linecap="round" '
        f'stroke-dasharray="{circ*ratio:.1f} {circ:.1f}" transform="rotate(-90 {cx} {cy})" class="pulse"/>'
    )
    out.append(f'<text x="{cx}" y="{cy+12}" text-anchor="middle" class="t big">{current}</text>')
    out.append(f'<text x="{cx}" y="{cy+98}" text-anchor="middle" class="t lbl">CURRENT STREAK (DAYS)</text>')
    out.append(f'<text x="{cx}" y="{cy+120}" text-anchor="middle" class="t lbl">LONGEST: {longest}</text>')

    # languages
    out.append('<text x="360" y="228" class="t h">Top languages</text>')
    for i, (name, (size, color)) in enumerate(top):
        pct = size / lang_total * 100
        y = 258 + i * 40
        out.append(f'<text x="360" y="{y}" class="t lbl" style="font-size:15px;fill:#e2e8f0">{name}</text>')
        out.append(f'<text x="640" y="{y}" text-anchor="end" class="t lbl">{pct:.1f}%</text>')
        out.append(f'<rect x="360" y="{y+8}" width="280" height="8" rx="4" fill="#1e293b"/>')
        out.append(f'<rect x="360" y="{y+8}" width="{280*pct/100:.1f}" height="8" rx="4" fill="{color}"/>')

    # heatmap (last 26 weeks)
    out.append('<text x="720" y="228" class="t h">Last 26 weeks</text>')
    weeks = cal["weeks"][-26:]
    for wi, week in enumerate(weeks):
        for di, day in enumerate(week["contributionDays"]):
            colour = level(day["contributionCount"], peak)
            out.append(
                f'<rect x="{720 + wi*17}" y="{248 + di*17}" width="14" height="14" rx="3" fill="{colour}" '
                f'class="f" style="animation-delay:{wi*0.03:.2f}s"/>'
            )

    out.append(f'<text x="600" y="540" text-anchor="middle" class="t lbl" style="font-size:12px">auto-generated {date.today().isoformat()} via GitHub Actions</text>')
    out.append("</g>")
    out.append('<rect x="0.5" y="0.5" width="1199" height="559" rx="16" fill="none" stroke="#38bdf8" stroke-opacity="0.35"/></svg>')
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
