#!/usr/bin/env python3
"""Fill README.md marker blocks with live data from the GitHub API.

Blocks (replaced in place):
  <!--ACTIVITY:START--> ... <!--ACTIVITY:END-->   recent public activity
  <!--REPOS:START-->    ... <!--REPOS:END-->      clickable, animated repository cards
                                                  (pinned repositories first, else most recently pushed)

Cards are written to assets/cards/<repo>.svg.

Usage: GITHUB_TOKEN=... python scripts/update_readme.py <username> [README.md]
Standard library only.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from html import escape

API = "https://api.github.com"
CARD_DIR = "assets/cards"
CARDS = 6

REPO_FIELDS = "name description url stargazerCount forkCount pushedAt isFork primaryLanguage { name color }"
QUERY = f"""
query($login: String!) {{
  user(login: $login) {{
    pinnedItems(first: {CARDS}, types: REPOSITORY) {{ nodes {{ ... on Repository {{ {REPO_FIELDS} }} }} }}
    repositories(first: 30, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false,
                 orderBy: {{field: PUSHED_AT, direction: DESC}}) {{ nodes {{ {REPO_FIELDS} }} }}
  }}
}}
"""

CARD_STYLE = """<style>
:root{--bg:#0d1117;--line:#30363d;--fg:#f0f6fc;--muted:#9198a1;--accent:#38bdf8}
@media (prefers-color-scheme:light){:root{--bg:#ffffff;--line:#d1d9e0;--fg:#1f2328;--muted:#59636e;--accent:#0969da}}
.t{font-family:-apple-system,'Segoe UI',Inter,Ubuntu,Helvetica,Arial,sans-serif}
.n{font-size:19px;font-weight:700;fill:var(--accent)}
.d{font-size:14px;fill:var(--fg);opacity:.85}
.m{font-size:13px;fill:var(--muted)}
.f{animation:up .7s cubic-bezier(.2,.7,.2,1) both}
.dot{transform-box:fill-box;transform-origin:center;animation:pulse 2.6s ease-in-out infinite}
.bar{transform-box:fill-box;transform-origin:left center;animation:grow 1.1s cubic-bezier(.2,.7,.2,1) both}
.sheen{animation:sheen 7s ease-in-out infinite}
@keyframes up{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@keyframes grow{from{transform:scaleX(0)}}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.35)}}
@keyframes sheen{0%{transform:translateX(-300px)}55%,100%{transform:translateX(900px)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style>"""

ICONS = {
    "PushEvent": "⬆️",
    "PullRequestEvent": "🔀",
    "IssuesEvent": "🐛",
    "CreateEvent": "✨",
    "ReleaseEvent": "🚀",
    "PublicEvent": "🌍",
}


def request(url: str, token: str, body: dict | None = None):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def ago(iso: str) -> str:
    then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    delta = datetime.now(timezone.utc) - then
    days = delta.days
    if days >= 365:
        return f"{days // 365} y ago"
    if days >= 30:
        return f"{days // 30} mo ago"
    if days >= 1:
        return f"{days} d ago"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours} h ago"
    return "just now"


def describe(event: dict) -> str | None:
    repo = event["repo"]["name"]
    link = f"[{repo}](https://github.com/{repo})"
    payload = event["payload"]
    kind = event["type"]
    if kind == "PushEvent":
        commits = payload.get("commits") or []
        branch = payload.get("ref", "").removeprefix("refs/heads/")
        if commits:
            message = commits[-1]["message"].splitlines()[0][:72]
            count = payload.get("size", len(commits))
            noun = "commit" if count == 1 else "commits"
            return f"Pushed {count} {noun} to {link} – _{message}_"
        # The events API no longer lists commits for pushes; fall back to the branch.
        return f"Pushed to `{branch}` in {link}" if branch else f"Pushed to {link}"
    if kind == "PullRequestEvent":
        pr = payload["pull_request"]
        action = "Merged" if payload["action"] == "closed" and pr.get("merged") else payload["action"].capitalize()
        title = pr.get("title")
        suffix = f" – _{title[:72]}_" if title else ""
        return f"{action} PR [#{pr['number']}]({pr['html_url']}) in {link}{suffix}"
    if kind == "IssuesEvent":
        issue = payload["issue"]
        return f"{payload['action'].capitalize()} issue [#{issue['number']}]({issue['html_url']}) in {link}"
    if kind == "CreateEvent" and payload.get("ref_type") == "repository":
        return f"Created repository {link}"
    if kind == "ReleaseEvent":
        release = payload["release"]
        return f"Released [{release['tag_name']}]({release['html_url']}) in {link}"
    if kind == "PublicEvent":
        return f"Made {link} public"
    return None


def activity_block(user: str, token: str) -> str:
    events = request(f"{API}/users/{user}/events/public?per_page=100", token)
    lines, seen = [], set()
    for event in events:
        text = describe(event)
        if not text or text in seen:
            continue
        seen.add(text)
        lines.append(f"{ICONS.get(event['type'], '•')} {text} · <sub>{ago(event['created_at'])}</sub>")
        if len(lines) == 8:
            break
    return "<br/>\n".join(lines) if lines else "_No public activity yet._"


def wrap(text: str, width: int, lines: int) -> list[str]:
    words, out, cur = text.split(), [], ""
    for word in words:
        if len(cur) + len(word) + 1 > width:
            out.append(cur)
            cur = word
            if len(out) == lines:
                break
        else:
            cur = f"{cur} {word}".strip()
    else:
        if cur:
            out.append(cur)
        return out
    out[-1] = out[-1][: width - 1].rstrip(" ,.;–-") + "…"
    return out


def card(repo: dict, index: int) -> str:
    lang = repo.get("primaryLanguage") or {}
    color = lang.get("color") or "#8b949e"
    desc = wrap(repo.get("description") or "No description yet.", 66, 2)
    delay = index * 0.12
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="150" viewBox="0 0 600 150" role="img" '
        f'aria-label="{escape(repo["name"])}">',
        '<defs><clipPath id="k"><rect width="600" height="150" rx="12"/></clipPath>'
        '<linearGradient id="a" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#0ea5e9"/>'
        '<stop offset="1" stop-color="#a78bfa"/></linearGradient>'
        '<linearGradient id="s" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset=".5" stop-color="#fff" stop-opacity=".06"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>'
        "</linearGradient></defs>",
        CARD_STYLE,
        '<g clip-path="url(#k)"><rect width="600" height="150" style="fill:var(--bg)"/>',
        f'<rect width="600" height="3" fill="url(#a)" class="bar" style="animation-delay:{delay:.2f}s"/>',
        f'<g class="t f" style="animation-delay:{delay + 0.1:.2f}s">',
        '<path d="M26 30h14a3 3 0 0 1 3 3v18a3 3 0 0 1-3 3H26zm0 0v24" fill="none" stroke-width="1.6" '
        'style="stroke:var(--muted)"/>',
        f'<text x="54" y="48" class="n">{escape(repo["name"])}</text>',
    ]
    for i, line in enumerate(desc):
        parts.append(f'<text x="26" y="{80 + i * 20}" class="d">{escape(line)}</text>')
    meta_x = 26
    parts.append("</g>")
    parts.append(f'<g class="t f m" style="animation-delay:{delay + 0.25:.2f}s">')
    if lang:
        parts.append(f'<circle cx="{meta_x + 6}" cy="128" r="6" fill="{escape(color)}" class="dot"/>')
        parts.append(f'<text x="{meta_x + 18}" y="133" class="m">{escape(lang["name"])}</text>')
        meta_x += 30 + len(lang["name"]) * 8
    parts.append(f'<text x="{meta_x}" y="133" class="m">★ {repo["stargazerCount"]}</text>')
    meta_x += 50
    parts.append(f'<text x="{meta_x}" y="133" class="m">⑂ {repo["forkCount"]}</text>')
    parts.append(f'<text x="574" y="133" text-anchor="end" class="m">updated {ago(repo["pushedAt"])}</text>')
    parts.append("</g>")
    parts.append('<rect width="300" height="150" fill="url(#s)" class="sheen"/></g>')
    parts.append('<rect x=".5" y=".5" width="599" height="149" rx="12" fill="none" style="stroke:var(--line)"/></svg>')
    return "\n".join(parts)


def repos_block(user: str, token: str) -> str:
    data = request(f"{API}/graphql", token, {"query": QUERY, "variables": {"login": user}})
    if "errors" in data:
        raise SystemExit(f"GraphQL error: {data['errors']}")
    node = data["data"]["user"]
    picked, names = [], set()
    for repo in node["pinnedItems"]["nodes"] + node["repositories"]["nodes"]:
        if not repo or repo["isFork"] or repo["name"].lower() == user.lower() or repo["name"] in names:
            continue
        picked.append(repo)
        names.add(repo["name"])
        if len(picked) == CARDS:
            break
    if not picked:
        return "_No public repositories yet._"

    os.makedirs(CARD_DIR, exist_ok=True)
    for stale in os.listdir(CARD_DIR):
        if stale.endswith(".svg") and stale[:-4] not in names:
            os.remove(os.path.join(CARD_DIR, stale))
    cells = []
    for index, repo in enumerate(picked):
        with open(os.path.join(CARD_DIR, f"{repo['name']}.svg"), "w", encoding="utf-8") as handle:
            handle.write(card(repo, index % 2))
        cells.append(
            f'<a href="{repo["url"]}"><img src="{CARD_DIR}/{repo["name"]}.svg" alt="{escape(repo["name"])}" width="49%"/></a>'
        )
    return '<p align="center">\n' + "\n".join(cells) + "\n</p>"


def replace_block(text: str, name: str, content: str) -> str:
    pattern = re.compile(rf"(<!--{name}:START-->)(.*?)(<!--{name}:END-->)", re.DOTALL)
    if not pattern.search(text):
        raise SystemExit(f"marker {name} not found in README")
    return pattern.sub(lambda m: f"{m.group(1)}\n{content}\n{m.group(3)}", text)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: update_readme.py <username> [README.md]")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")
    user = sys.argv[1]
    path = sys.argv[2] if len(sys.argv) > 2 else "README.md"
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    text = replace_block(text, "ACTIVITY", activity_block(user, token))
    text = replace_block(text, "REPOS", repos_block(user, token))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"updated {path}")


if __name__ == "__main__":
    main()
