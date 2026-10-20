#!/usr/bin/env python3
"""Fill README.md marker blocks with live data from the GitHub API.

Blocks (replaced in place):
  <!--ACTIVITY:START--> ... <!--ACTIVITY:END-->   recent public activity
  <!--HOSTWERK:START--> ... <!--HOSTWERK:END-->   Hostwerk spotlight card, links and the extension list
                                                  (from the public catalogue in hostwerk-public)
  <!--REPOS:START-->    ... <!--REPOS:END-->      optional: clickable, animated cards for other repositories
                                                  (pinned first, else most recently pushed; Hostwerk repos excluded)

Only the blocks whose markers are in the README are filled.

Cards are written to assets/cards/<repo>.svg, the spotlight to assets/hostwerk.svg.

Usage: GITHUB_TOKEN=... python scripts/update_readme.py <username> [README.md]
Standard library only.
"""
import base64
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
    repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false,
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
        # Slim event payloads may lack html_url, title and merged – build what is missing.
        pr = payload.get("pull_request") or {}
        number = pr.get("number") or payload.get("number")
        if not number:
            return None
        url = pr.get("html_url") or f"https://github.com/{repo}/pull/{number}"
        action = payload.get("action", "updated")
        action = "Merged" if action == "closed" and pr.get("merged") else action.capitalize()
        title = pr.get("title")
        suffix = f" – _{title[:72]}_" if title else ""
        return f"{action} PR [#{number}]({url}) in {link}{suffix}"
    if kind == "IssuesEvent":
        issue = payload.get("issue") or {}
        number = issue.get("number")
        if not number:
            return None
        url = issue.get("html_url") or f"https://github.com/{repo}/issues/{number}"
        return f"{payload.get('action', 'updated').capitalize()} issue [#{number}]({url}) in {link}"
    if kind == "CreateEvent" and payload.get("ref_type") == "repository":
        return f"Created repository {link}"
    if kind == "ReleaseEvent":
        release = payload.get("release") or {}
        tag = release.get("tag_name")
        if not tag:
            return None
        url = release.get("html_url") or f"https://github.com/{repo}/releases/tag/{tag}"
        return f"Released [{tag}]({url}) in {link}"
    if kind == "PublicEvent":
        return f"Made {link} public"
    return None


def activity_block(user: str, token: str) -> str:
    events = request(f"{API}/users/{user}/events/public?per_page=100", token)
    events.sort(key=lambda event: event["created_at"], reverse=True)
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


HOSTWERK_REPO = "hostwerk-public"
EXT_DIR = "assets/ext"
HOSTWERK_CATEGORIES = [
    ("games", "Games & Minecraft"),
    ("network", "Network & machines"),
    ("security", "Security & access"),
    ("monitoring", "Monitoring & status"),
    ("developer", "Developer tools"),
    ("ai", "AI & media"),
    ("communication", "Mail & communication"),
    ("other", "Other"),
]

SPOT_STYLE = """<style>
:root{--bg:#0d1117;--line:#30363d;--fg:#f0f6fc;--muted:#9198a1;--accent:#38bdf8;--tile:#161b22;--grid:#ffffff}
@media (prefers-color-scheme:light){:root{--bg:#ffffff;--line:#d1d9e0;--fg:#1f2328;--muted:#59636e;--accent:#0969da;--tile:#f6f8fa;--grid:#000000}}
.t{font-family:-apple-system,'Segoe UI',Inter,Ubuntu,Helvetica,Arial,sans-serif}
.k{font-size:13px;font-weight:700;letter-spacing:2px;fill:var(--accent)}
.h{font-size:56px;font-weight:800;letter-spacing:-1.5px}
.s{font-size:18px;fill:var(--fg);opacity:.85}
.p{font-size:14px;font-weight:600;fill:var(--fg)}
.pill{fill:var(--tile);stroke:var(--line)}
.u{font-size:13px;fill:var(--muted)}
.tile{fill:var(--tile);stroke:var(--line)}
.grid{stroke:var(--grid);stroke-opacity:.04}
.n{font-size:96px;font-weight:800;letter-spacing:-3px}
.f{animation:up .8s cubic-bezier(.2,.7,.2,1) both}
.pop{transform-box:fill-box;transform-origin:center;animation:pop .6s cubic-bezier(.2,.7,.2,1) both}
.fl{animation:float 5s ease-in-out infinite}
.live{transform-box:fill-box;transform-origin:center;animation:live 2s ease-in-out infinite}
@keyframes up{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
@keyframes pop{from{opacity:0;transform:scale(.3)}}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
@keyframes live{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(1.8)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style>"""


def fetch_raw(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "profile-readme"}), timeout=20) as resp:
            return resp.read()
    except OSError:
        return None


def text(value, lang: str = "en") -> str:
    if isinstance(value, dict):
        return value.get(lang) or next(iter(value.values()), "")
    return value or ""


def spotlight(version: str, released: str, downloads: int) -> str:
    """Hostwerk card: name, pitch, live numbers and the latest release (extension tiles follow below it)."""
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="300" viewBox="0 0 1200 300" role="img" '
        f'aria-label="Hostwerk – the local server hub for Windows and Linux, latest release {escape(version)}">',
        '<defs><clipPath id="c"><rect width="1200" height="300" rx="14"/></clipPath>'
        '<linearGradient id="g" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#0ea5e9"/>'
        '<stop offset=".5" stop-color="#a78bfa"/><stop offset="1" stop-color="#0ea5e9"/>'
        '<animate attributeName="x1" values="0;-1;0" dur="8s" repeatCount="indefinite"/>'
        '<animate attributeName="x2" values="1;0;1" dur="8s" repeatCount="indefinite"/></linearGradient>'
        '<pattern id="p" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" class="grid"/></pattern>'
        '<radialGradient id="r" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#38bdf8" stop-opacity=".16"/>'
        '<stop offset="1" stop-color="#38bdf8" stop-opacity="0"/></radialGradient></defs>',
        SPOT_STYLE,
        '<g clip-path="url(#c)"><rect width="1200" height="300" style="fill:var(--bg)"/><rect width="1200" height="300" fill="url(#p)"/>',
        '<circle cx="960" cy="150" r="280" fill="url(#r)"><animate attributeName="r" values="260;300;260" dur="7s" repeatCount="indefinite"/></circle>',
        '<g class="t">',
        '<text x="48" y="64" class="k f">FLAGSHIP PROJECT</text>',
        '<text x="46" y="128" class="h f" fill="url(#g)" style="animation-delay:.1s">Hostwerk</text>',
        '<text x="48" y="164" class="s f" style="animation-delay:.25s">The local server hub for Windows and Linux –</text>',
        '<text x="48" y="188" class="s f" style="animation-delay:.3s">web servers, databases, mail, Minecraft and AI.</text>',
    ]
    pills = ["Windows · Linux"]
    if downloads:
        pills.insert(0, f"{downloads:,} downloads")
    x = 48
    for i, label in enumerate(pills):
        w = 26 + len(label) * 8
        out.append(
            f'<g class="f" style="animation-delay:{0.45 + i * 0.1:.2f}s"><rect x="{x}" y="212" width="{w}" height="32" rx="16" class="pill"/>'
            f'<text x="{x + w / 2:.0f}" y="233" text-anchor="middle" class="p">{escape(label)}</text></g>'
        )
        x += w + 10
    out.append('<circle cx="54" cy="268" r="3.5" fill="#22c55e" class="live"/>')
    out.append(f'<text x="66" y="273" class="u f" style="animation-delay:.9s">github.com/Passimoritz/{HOSTWERK_REPO}</text>')
    # right side: live extension count
    # right side: latest release
    out.append('<text x="960" y="96" text-anchor="middle" class="k f" style="animation-delay:.4s">LATEST RELEASE</text>')
    out.append(f'<text x="960" y="186" text-anchor="middle" class="n pop" fill="url(#g)" style="animation-delay:.5s">{escape(version)}</text>')
    if released:
        out.append(f'<text x="960" y="224" text-anchor="middle" class="u f" style="animation-delay:.8s">released {escape(released)}</text>')
    out.append("</g></g>")
    out.append('<rect x=".5" y=".5" width="1199" height="299" rx="14" fill="none" style="stroke:var(--line)"/></svg>')
    return "\n".join(out)


def ext_tile(ext: dict, index: int) -> str:
    """One animated 64×64 tile with the extension's own icon embedded (external images do not load inside <img>)."""
    name = escape(text(ext.get("name")))
    icon = fetch_raw(ext.get("icon") or "")
    if icon and icon.lstrip().startswith(b"<"):
        inner = f'<image x="15" y="15" width="34" height="34" href="data:image/svg+xml;base64,{base64.b64encode(icon).decode()}"/>'
    else:
        inner = f'<text x="32" y="41" text-anchor="middle" class="t p" style="font-size:22px">{escape(name[:1])}</text>'
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64" role="img" aria-label="{name}">',
        SPOT_STYLE,
        f'<g class="fl" style="animation-delay:{-(index * 0.7) % 5:.1f}s"><g class="pop" style="animation-delay:{0.2 + index * 0.05:.2f}s">',
        '<rect x="3" y="3" width="58" height="58" rx="13" class="tile"/>',
        inner,
        "</g></g></svg>",
    ])


def summary(ext: dict) -> str:
    """Short explanation for the tooltip: the catalogue description, cut at the first natural break."""
    desc = " ".join(text(ext.get("description")).split())
    for match in re.finditer(r"(: |\. |; | – )", desc):
        cut = match.start()
        if re.search(r"(\be\.g|\bi\.e|\betc|\bco|\bvs|\bz\.B)$", desc[:cut], re.IGNORECASE):
            continue
        if 30 <= cut <= 140:
            return desc[:cut].rstrip(".") + "."
    if len(desc) > 140:
        desc = desc[:139].rsplit(" ", 1)[0].rstrip(",;:–-") + "…"
    return desc


BUTTON_STYLE = """<style>
:root{--btn:#38bdf8;--btn-fg:#04202e;--btn-sub:#0b3b52;--btn-chip:#04202e}
@media (prefers-color-scheme:light){:root{--btn:#0969da;--btn-fg:#ffffff;--btn-sub:#dbeafe;--btn-chip:#ffffff}}
.t{font-family:-apple-system,'Segoe UI',Inter,Ubuntu,Helvetica,Arial,sans-serif}
.b{font-size:16px;font-weight:700;fill:var(--btn-fg)}
.s{font-size:13px;fill:var(--btn-sub)}
.chip{fill:var(--btn-chip);fill-opacity:.14}
.ic{fill:none;stroke:var(--btn-fg);stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.icf{fill:var(--btn-fg)}
</style>"""

# (key, label, file extensions in order of preference, name hints for generic archives)
PLATFORMS = (
    ("windows", "Windows", (".exe", ".msi"), ("win", "setup", "installer")),
    ("linux", "Linux", (".appimage", ".deb", ".rpm", ".tar.gz", ".tgz", ".tar.xz"), ("linux", "ubuntu", "debian")),
)
# updater metadata, checksums, other operating systems and source archives are never offered as downloads
SKIP_ASSET = ("sha", "checksum", ".sig", ".asc", ".blockmap", ".yml", ".yaml", ".txt", ".json", ".nupkg", ".md",
              "source", "mac", "darwin", ".dmg", ".pkg", "video", ".mp4", ".webm")
OTHER_OS = {"windows": ("linux", "appimage", ".deb", ".rpm"), "linux": ("win", ".exe", ".msi")}


def pick_asset(assets: list[dict], extensions: tuple, hints: tuple, key: str = "") -> dict | None:
    """Best installer for one platform.

    Score: preferred extension (earlier = better), OS word in the name, installer over portable,
    x64 over ARM; zip/tarballs only count when the name points at the platform.
    """
    best, best_score = None, 0
    for asset in assets:
        name = asset["name"].lower()
        if any(s in name for s in SKIP_ASSET) or any(o in name for o in OTHER_OS.get(key, ())):
            continue
        score = 0
        for index, ext in enumerate(extensions):
            if name.endswith(ext):
                score = 100 - index * 10
                break
        if not score and name.endswith((".zip", ".tar.gz", ".tgz", ".7z")) and any(h in name for h in hints):
            score = 40
        if not score:
            continue
        score += 5 * sum(h in name for h in hints)
        score -= 15 if "portable" in name else 0
        score -= 20 if any(t in name for t in ("arm", "aarch")) else 0
        if score > best_score:
            best, best_score = asset, score
    return best


def size_label(size: int) -> str:
    return f"{size / 1024 / 1024:.0f} MB" if size >= 10 * 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"


def file_kind(name: str) -> str:
    lower = name.lower()
    for ext in (".appimage", ".tar.gz", ".tgz", ".exe", ".msi", ".deb", ".rpm", ".zip"):
        if lower.endswith(ext):
            return ext.lstrip(".").upper() if ext != ".appimage" else "AppImage"
    return "file"


def platform_icon(key: str) -> str:
    if key == "windows":
        return ('<g class="icf"><rect x="-10" y="-10" width="9" height="9" rx="1.5"/><rect x="1" y="-10" width="9" height="9" rx="1.5"/>'
                '<rect x="-10" y="1" width="9" height="9" rx="1.5"/><rect x="1" y="1" width="9" height="9" rx="1.5"/></g>')
    if key == "linux":
        return '<g class="ic"><rect x="-11" y="-10" width="22" height="20" rx="3"/><path d="M-6 -3l4 3-4 3M1 4h6"/></g>'
    return '<g class="ic"><path d="M0 -10v14M-6 -2l6 6 6-6M-10 10h20"/></g>'


def download_button(key: str, title: str, sub: str) -> str:
    """Static, clickable-through-<a> button; follows the viewer's light/dark preference."""
    width, height = 320, 72
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(title)} – {escape(sub)}">{BUTTON_STYLE}'
        f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="14" style="fill:var(--btn)"/>'
        f'<rect x="14" y="14" width="44" height="44" rx="11" class="chip"/>'
        f'<g transform="translate(36 36)">{platform_icon(key)}</g>'
        f'<text x="72" y="33" class="t b">{escape(title)}</text>'
        f'<text x="72" y="52" class="t s">{escape(sub)}</text>'
        f'<g transform="translate(292 36)" class="ic"><path d="M0 -9v13M-6 -2l6 6 6-6"/></g>'
        f"</svg>"
    )


def download_block(base: str, latest: dict | None, version: str, released: str, downloads: int) -> str:
    """Direct per-OS download buttons plus a facts line; falls back to one generic button."""
    assets = (latest or {}).get("assets", [])
    buttons = []
    for key, label, extensions, hints in PLATFORMS:
        asset = pick_asset(assets, extensions, hints, key)
        if not asset:
            continue
        sub = " · ".join(p for p in (file_kind(asset["name"]), size_label(asset["size"]), version) if p)
        path = f"assets/dl-{key}.svg"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(download_button(key, f"Download for {label}", sub))
        buttons.append(
            f'<a href="{escape(asset["browser_download_url"])}"><img src="{path}" width="320" height="72" '
            f'alt="Download Hostwerk for {label} ({escape(asset["name"])})"/></a>'
        )
    if len(buttons) < 2:
        title = "All downloads" if buttons else "Download Hostwerk"
        sub = " · ".join(p for p in ("Windows · Linux" if not buttons else "other platforms", version) if p)
        with open("assets/dl-latest.svg", "w", encoding="utf-8") as handle:
            handle.write(download_button("generic", title, sub))
        buttons.append(
            f'<a href="{base}/releases/latest"><img src="assets/dl-latest.svg" width="320" height="72" alt="Download Hostwerk"/></a>'
        )
    for stale in ("dl-windows.svg", "dl-linux.svg", "dl-latest.svg"):
        used = any(f"assets/{stale}" in b for b in buttons)
        if not used and os.path.exists(f"assets/{stale}"):
            os.remove(f"assets/{stale}")

    facts = [p for p in (version, released, f"{downloads:,} downloads" if downloads else "") if p]
    notes_url = (latest or {}).get("html_url") or f"{base}/releases/latest"
    links = [f'<a href="{notes_url}">Release notes &amp; all files</a>', f'<a href="{base}/releases">All releases</a>']
    line = " · ".join(facts + links)
    return f'<p align="center">\n{"&nbsp;&nbsp;".join(buttons)}\n<br/><sub>{line}</sub>\n</p>'


def hostwerk_block(user: str, token: str) -> str:
    raw = fetch_raw(f"https://raw.githubusercontent.com/{user}/{HOSTWERK_REPO}/main/catalog/extensions.json")
    exts = json.loads(raw) if raw else []
    if isinstance(exts, dict):
        exts = exts.get("extensions", [])
    order = {key: i for i, (key, _) in enumerate(HOSTWERK_CATEGORIES)}
    labels = dict(HOSTWERK_CATEGORIES)
    exts.sort(key=lambda e: (order.get(e.get("category"), 99), text(e.get("name")).lower()))

    version, released, downloads = "", "", 0
    latest: dict | None = None
    try:
        releases = request(f"{API}/repos/{user}/{HOSTWERK_REPO}/releases?per_page=100", token)
        stable = [r for r in releases if not r["draft"] and not r["prerelease"] and re.match(r"^v\d", r["tag_name"])]
        latest = stable[0] if stable else None
        version = stable[0]["tag_name"] if stable else ""
        if stable and stable[0].get("published_at"):
            day = datetime.fromisoformat(stable[0]["published_at"].replace("Z", "+00:00"))
            released = f"{day:%B} {day.day}, {day.year}"
        downloads = sum(a["download_count"] for r in releases for a in r["assets"])
    except OSError:
        pass

    with open("assets/hostwerk.svg", "w", encoding="utf-8") as handle:
        handle.write(spotlight(version or "latest", released, downloads))

    # one tile per extension; the title attribute is the hover tooltip GitHub keeps
    os.makedirs(EXT_DIR, exist_ok=True)
    ids = set()
    tiles = []
    for index, ext in enumerate(exts):
        ext_id = re.sub(r"[^a-z0-9-]", "-", str(ext.get("id") or text(ext.get("name"))).lower())
        ids.add(ext_id)
        with open(os.path.join(EXT_DIR, f"{ext_id}.svg"), "w", encoding="utf-8") as handle:
            handle.write(ext_tile(ext, index))
        facts = [labels.get(ext.get("category"), "Extension")]
        if ext.get("native"):
            facts.append("part of Hostwerk")
        if ext.get("version"):
            facts.append(f"v{ext['version']}")
        tip = f"{text(ext.get('name'))} – {summary(ext)}\n{' · '.join(facts)}"
        tip = escape(tip).replace("\n", "&#10;")
        tiles.append(
            f'<a href="{ext.get("homepage") or f"https://github.com/{user}/{HOSTWERK_REPO}"}" title="{tip}">'
            f'<img src="{EXT_DIR}/{ext_id}.svg" width="56" height="56" alt="{escape(text(ext.get("name")))}" title="{tip}"/></a>'
        )
    for stale in os.listdir(EXT_DIR):
        if stale.endswith(".svg") and stale[:-4] not in ids:
            os.remove(os.path.join(EXT_DIR, stale))

    base = f"https://github.com/{user}/{HOSTWERK_REPO}"
    parts = [f'<a href="{base}"><img src="assets/hostwerk.svg" alt="Hostwerk – the local server hub for Windows and Linux" width="100%"/></a>']
    if tiles:
        parts.append('<p align="center">\n' + "\n".join(tiles) + "\n</p>")
    parts.append(download_block(base, latest, version, released, downloads))
    return "\n\n".join(parts)


def repos_block(user: str, token: str) -> str:
    data = request(f"{API}/graphql", token, {"query": QUERY, "variables": {"login": user}})
    if "errors" in data:
        raise SystemExit(f"GraphQL error: {data['errors']}")
    node = data["data"]["user"]
    picked, names = [], set()
    for repo in node["pinnedItems"]["nodes"] + node["repositories"]["nodes"]:
        if (
            not repo
            or repo["isFork"]
            or repo["name"].lower() == user.lower()
            or repo["name"].startswith("hostwerk")
            or repo["name"] in names
        ):
            continue
        picked.append(repo)
        names.add(repo["name"])
        if len(picked) == CARDS:
            break
    os.makedirs(CARD_DIR, exist_ok=True)
    for stale in os.listdir(CARD_DIR):
        if stale.endswith(".svg") and stale[:-4] not in names:
            os.remove(os.path.join(CARD_DIR, stale))
    if not picked:
        return ""
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
    for name, build in (("HOSTWERK", hostwerk_block), ("ACTIVITY", activity_block), ("REPOS", repos_block)):
        if f"<!--{name}:START-->" in text:
            text = replace_block(text, name, build(user, token))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"updated {path}")


if __name__ == "__main__":
    main()
