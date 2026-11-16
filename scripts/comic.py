#!/usr/bin/env python3
"""Comic design kit for the profile: themes, fonts and drawing helpers shared by every SVG.

The profile reads like a calm, editorial comic issue: panels with ink lines and hard offset
shadows, narrator caption boxes, a speech bubble and fading halftone dots.

Every graphic is written twice – assets/<name>-light.svg and assets/<name>-dark.svg – and the
README shows them through <picture>, so GitHub picks the one that matches the reader's theme.

Fonts (SIL Open Font License, scripts/fonts/OFL-*.txt): Bricolage Grotesque for titles and text,
JetBrains Mono for captions. SVGs inside <img> cannot load external files, so each SVG embeds a
WOFF2 subset of exactly the characters it uses (needs fontTools + brotli).

Run directly to (re)build the static pages:
  python scripts/comic.py   → cover, ch-1…ch-5, origin, footer (light + dark)
"""
import base64
import html
import os
import re
from functools import lru_cache
from html import escape
from io import BytesIO

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT_DIR = os.path.join(HERE, "fonts")
FONTS = {  # css family → (file, class)
    "PMDisplay": ("Bricolage-ExtraBold.ttf", "d"),
    "PMText": ("Bricolage-Medium.ttf", "tx"),
    "PMMono": ("JetBrainsMono-Bold.ttf", "mo"),
}
CLASS_FONT = {cls: fam for fam, (_, cls) in FONTS.items()}

# ── Themes ────────────────────────────────────────────────────────────────────────────────
LIGHT = {
    "name": "light", "paper": "#fffdf8", "paper2": "#f6f1e6", "ink": "#1c1a23", "line": "#1c1a23",
    "muted": "#6b6676", "shadow": "#1c1a23",
    "amber": "#eaa53a", "coral": "#e2604f", "teal": "#1f9a8b", "blue": "#3a72dc", "violet": "#7564e6",
    "on_accent": "#1c1a23",
}
DARK = {
    "name": "dark", "paper": "#161b22", "paper2": "#1d232d", "ink": "#ece7dc", "line": "#cfc9bc",
    "muted": "#98a0ad", "shadow": "#010409",
    "amber": "#f0b24a", "coral": "#f07a69", "teal": "#3cc2b1", "blue": "#6d9dff", "violet": "#a596ff",
    "on_accent": "#1c1a23",
}
THEMES = (LIGHT, DARK)


# ── Fonts ─────────────────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=None)
def _font(family: str):
    from fontTools.ttLib import TTFont

    return TTFont(os.path.join(FONT_DIR, FONTS[family][0]))


def width(text: str, size: float, cls: str = "d", spacing: float = 0) -> float:
    """Rendered width of text in px, from the font's advances."""
    font = _font(CLASS_FONT[cls])
    cmap, hmtx, upm = font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm
    total = sum(hmtx[cmap[ord(ch)]][0] if ord(ch) in cmap else upm * .55 for ch in text)
    return total * size / upm + spacing * len(text)


@lru_cache(maxsize=256)
def _subset(family: str, chars: str) -> str:
    from fontTools import subset
    from fontTools.ttLib import TTFont

    font = TTFont(os.path.join(FONT_DIR, FONTS[family][0]))
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga", "calt"]
    sub = subset.Subsetter(opts)
    sub.populate(text=chars + " ")
    sub.subset(font)
    buf = BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


def font_faces(markup: str, families: tuple | None = None) -> str:
    """@font-face rules for the fonts the markup uses, subset to the characters it shows."""
    chars = "".join(sorted(set(html.unescape("".join(re.findall(r">([^<>]+)<", markup))))))
    if families is None:
        used = set()
        for classes in re.findall(r'class="([^"]*)"', markup):
            used |= {CLASS_FONT[c] for c in classes.split() if c in CLASS_FONT}
        families = tuple(sorted(used))
    return "".join(
        f"@font-face{{font-family:'{fam}';src:url(data:font/woff2;base64,{_subset(fam, chars)}) format('woff2')}}"
        for fam in families
    )


BASE_CSS = """
.d{font-family:'PMDisplay','Segoe UI',sans-serif;font-weight:800}
.tx{font-family:'PMText','Segoe UI',sans-serif;font-weight:500}
.mo{font-family:'PMMono',Consolas,monospace;font-weight:700;letter-spacing:1.4px}
.up{animation:up .9s cubic-bezier(.2,.8,.2,1) both}
.fade{animation:fade 1.2s ease both}
.live{animation:live 2.4s ease-in-out infinite}
@keyframes up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}}
@keyframes live{0%,100%{opacity:1}50%{opacity:.3}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""


def svg(w: int, h: int, label: str, body: str, extra_css: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="{escape(label)}"><style>{font_faces(body)}{BASE_CSS}{extra_css}</style>{body}</svg>'
    )


# ── Writing themed files ──────────────────────────────────────────────────────────────────


def write_themed(stem: str, build) -> None:
    """Write <stem>-light.svg and <stem>-dark.svg (stem relative to the repo root) from build(theme)."""
    for t in THEMES:
        path = os.path.join(ROOT, f"{stem}-{t['name']}.svg")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(build(t))


def picture(stem: str, alt: str, width_attr: str = "100%", height: int | None = None, title: str = "") -> str:
    """<picture> that follows the reader's GitHub theme."""
    size = f' width="{width_attr}"' + (f' height="{height}"' if height else "")
    tip = f' title="{title}"' if title else ""
    return (
        f'<picture><source media="(prefers-color-scheme: dark)" srcset="{stem}-dark.svg"/>'
        f'<img src="{stem}-light.svg" alt="{alt}"{size}{tip}/></picture>'
    )


# ── Drawing helpers ───────────────────────────────────────────────────────────────────────


def halftone(pid: str, x, y, w, h, cx, cy, r, color: str, opacity: float, size: int = 10) -> str:
    """Halftone dots that fade out from (cx, cy) – the comic texture, kept quiet."""
    return (
        f'<defs><pattern id="{pid}" width="{size}" height="{size}" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<circle cx="{size / 2}" cy="{size / 2}" r="{size * .19:.2f}" fill="{color}" fill-opacity="{opacity}"/></pattern>'
        f'<radialGradient id="{pid}g" gradientUnits="userSpaceOnUse" cx="{cx}" cy="{cy}" r="{r}">'
        f'<stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        f'<mask id="{pid}m"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#{pid}g)"/></mask></defs>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#{pid})" mask="url(#{pid}m)"/>'
    )


def panel(x, y, w, h, t: dict, fill: str | None = None, shadow: int = 6, stroke: float = 2.5, rx: int = 10) -> str:
    """Comic panel: hard offset shadow, then the panel with an ink border."""
    return (
        f'<rect x="{x + shadow}" y="{y + shadow}" width="{w}" height="{h}" rx="{rx}" fill="{t["shadow"]}"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill or t["paper"]}" stroke="{t["line"]}" stroke-width="{stroke}"/>'
    )


def clipped(cid: str, x, y, w, h, inner: str, rx: int = 10) -> str:
    return f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/></clipPath><g clip-path="url(#{cid})">{inner}</g>'


def caption_w(text: str, size: int = 13) -> float:
    return width(text.upper(), size, "mo", 1.4) + 24


def caption(x, y, text: str, t: dict, fill: str | None = None, color: str | None = None, size: int = 13,
            style: str = "") -> str:
    """Narrator caption box (mono, uppercase) with a small hard shadow."""
    text = text.upper()
    w, h = caption_w(text, size), size + 16
    return (
        f'<g class="up" style="{style}"><rect x="{x + 3}" y="{y + 3}" width="{w:.0f}" height="{h}" rx="3" fill="{t["shadow"]}"/>'
        f'<rect x="{x}" y="{y}" width="{w:.0f}" height="{h}" rx="3" fill="{fill or t["amber"]}" stroke="{t["line"]}" stroke-width="2"/>'
        f'<text x="{x + 12}" y="{y + h / 2 + size * .36:.1f}" class="mo" font-size="{size}" fill="{color or t["on_accent"]}">{escape(text)}</text></g>'
    )


def bubble(x, y, w, h, lines: list[str], t: dict, size: int = 18, tail=(-50, 34), style: str = "") -> str:
    """Speech bubble with a tail from its lower-left third."""
    tx, ty = x + w * .3, y + h
    path = (f"M{x + 18},{y} H{x + w - 18} Q{x + w},{y} {x + w},{y + 18} V{y + h - 18} Q{x + w},{y + h} {x + w - 18},{y + h} "
            f"H{tx + 30} L{tx + tail[0]},{ty + tail[1]} L{tx + 4},{ty} H{x + 18} Q{x},{y + h} {x},{y + h - 18} V{y + 18} Q{x},{y} {x + 18},{y} Z")
    lh = size * 1.38
    top = y + h / 2 - lh * (len(lines) - 1) / 2 + size * .34
    out = [f'<g class="up" style="{style}"><path d="{path}" fill="{t["shadow"]}" transform="translate(5 5)"/>',
           f'<path d="{path}" fill="{t["paper"]}" stroke="{t["line"]}" stroke-width="2.5" stroke-linejoin="round"/>']
    for i, line in enumerate(lines):
        out.append(f'<text x="{x + 26}" y="{top + i * lh:.1f}" class="tx" font-size="{size}" fill="{t["ink"]}">{escape(line)}</text>')
    return "".join(out) + "</g>"


def wrap(text: str, size: float, max_w: float, cls: str = "tx") -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        cand = f"{cur} {word}".strip()
        if width(cand, size, cls) > max_w and cur:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def fit_size(text: str, size: float, max_w: float, cls: str = "d") -> float:
    w = width(text, size, cls)
    return size if w <= max_w else size * max_w / w


def ellipsize(text: str, size: float, max_w: float, cls: str = "tx") -> str:
    if width(text, size, cls) <= max_w:
        return text
    while text and width(text + "…", size, cls) > max_w:
        text = text[:-1]
    return text.rstrip(" -_./,") + "…"


# ── Shared project card (Hostwerk and Mirage use the same layout) ────────────────────────


def project_card(t: dict, name: str, issue: str, narrator: str, pitch: str, pills: list[str], stat_label: str,
                 stat_value: str, stat_sub: str, url_text: str, accent: str, cycle: list[str] | None = None) -> str:
    """1200×320 project panel – identical layout for every project. accent / cycle are theme keys."""
    W, H = 1200, 320
    a = t[accent]
    body = [
        panel(4, 4, W - 18, H - 18, t),
        clipped("pc", 4, 4, W - 18, H - 18, halftone("ht", 4, 4, W - 18, H - 18, W - 14, 4, 560, a, .55)),
        caption(36, 34, narrator, t),
        caption(36 + caption_w(narrator) + 13, 34, issue, t, fill=t["ink"], color=t["paper"], style="animation-delay:.08s"),
        f'<text x="32" y="148" class="d up" font-size="80" letter-spacing="-2" fill="{t["ink"]}" style="animation-delay:.12s">{escape(name)}</text>',
        f'<rect x="36" y="162" width="88" height="6" rx="3" fill="{a}" class="up" style="animation-delay:.2s"/>',
    ]
    for i, line in enumerate(wrap(pitch, 19, 650)[:2]):
        body.append(f'<text x="36" y="{204 + i * 27}" class="tx up" font-size="19" fill="{t["ink"]}" style="animation-delay:{.25 + i * .04:.2f}s">{escape(line)}</text>')
    x = 36
    for i, label in enumerate(pills):
        w = width(label, 14, "tx") + 28
        fill, color = (t["amber"], t["on_accent"]) if i == 0 else (t["paper"], t["ink"])
        body.append(
            f'<g class="up" style="animation-delay:{.35 + i * .06:.2f}s"><rect x="{x + 3}" y="261" width="{w:.0f}" height="30" rx="15" fill="{t["shadow"]}"/>'
            f'<rect x="{x}" y="258" width="{w:.0f}" height="30" rx="15" fill="{fill}" stroke="{t["line"]}" stroke-width="2"/>'
            f'<text x="{x + w / 2:.0f}" y="278" text-anchor="middle" class="tx" font-size="14" fill="{color}">{escape(label)}</text></g>'
        )
        x += w + 10
    body.append(f'<circle cx="{x + 12}" cy="273" r="4" fill="{t["teal"]}" class="live"/>'
                f'<text x="{x + 24}" y="277.5" class="mo up" font-size="11.5" fill="{t["muted"]}" style="animation-delay:.6s">{escape(url_text.upper())}</text>')
    # stat block on the right
    sx, sy, sw, sh = 858, 52, 288, 210
    band = f'<rect x="{sx}" y="{sy}" width="{sw}" height="12" fill="{a}">'
    if cycle:
        vals = ";".join(t[c] for c in cycle + cycle[:1])
        band += f'<animate attributeName="fill" values="{vals}" dur="{len(cycle) * 3}s" repeatCount="indefinite"/>'
    band += "</rect>"
    size = fit_size(stat_value, 66, sw - 48)
    body.append(
        f'<g class="up" style="animation-delay:.3s">{panel(sx, sy, sw, sh, t, rx=8)}'
        + clipped("sc", sx, sy, sw, sh, band, 8)
        + f'<line x1="{sx}" y1="{sy + 12}" x2="{sx + sw}" y2="{sy + 12}" stroke="{t["line"]}" stroke-width="2"/>'
        f'<text x="{sx + 24}" y="{sy + 52}" class="mo" font-size="12" fill="{t["muted"]}">{escape(stat_label.upper())}</text>'
        f'<text x="{sx + 22}" y="{sy + 132}" class="d" font-size="{size:.0f}" letter-spacing="-1.5" fill="{t["ink"]}">{escape(stat_value)}</text>'
        f'<text x="{sx + 24}" y="{sy + 174}" class="tx" font-size="15" fill="{t["muted"]}">{escape(stat_sub)}</text></g>'
    )
    return svg(W, H, f"{name} – {pitch}", "".join(body))


def tile(t: dict, inner: str, label: str, index: int) -> str:
    """64×64 sticker tile for an extension icon."""
    return svg(64, 64, label, (
        f'<g class="up" style="animation-delay:{.1 + index * .03:.2f}s">'
        f'<rect x="6" y="6" width="54" height="54" rx="13" fill="{t["shadow"]}"/>'
        f'<rect x="3" y="3" width="54" height="54" rx="13" fill="{t["paper"]}" stroke="{t["line"]}" stroke-width="2"/>'
        f"{inner}</g>"
    ))


BUTTON_ICONS = {
    "arrow": "M0 -9v13M-6 -1l6 6 6-6M-9 10h18",
    "linux": "M-11 -9h22v18h-22zM-6 -3l4 3-4 3M1 4h6",
    "code": "M-5 -8l-7 8 7 8M5 -8l7 8-7 8",
    "store": "M-11 -3h22l-2 13h-18zM-5 -3v-3a5 5 0 0 1 10 0v3",
}


def button(t: dict, title_text: str, sub: str, primary: bool = True, icon: str = "arrow") -> str:
    """320×80 button: ink border, hard shadow, quiet type."""
    fill, color = (t["amber"], t["on_accent"]) if primary else (t["paper"], t["ink"])
    if icon == "windows":
        glyph = (f'<g fill="{color}"><rect x="-9" y="-9" width="8" height="8" rx="1"/><rect x="1" y="-9" width="8" height="8" rx="1"/>'
                 '<rect x="-9" y="1" width="8" height="8" rx="1"/><rect x="1" y="1" width="8" height="8" rx="1"/></g>')
    else:
        glyph = (f'<path d="{BUTTON_ICONS.get(icon, BUTTON_ICONS["arrow"])}" fill="none" stroke="{color}" stroke-width="2.4" '
                 'stroke-linecap="round" stroke-linejoin="round"/>')
    body = (
        f'<g class="up"><rect x="8" y="8" width="306" height="66" rx="12" fill="{t["shadow"]}"/>'
        f'<rect x="3" y="3" width="306" height="66" rx="12" fill="{fill}" stroke="{t["line"]}" stroke-width="2.5"/>'
        f'<circle cx="38" cy="36" r="19" fill="none" stroke="{color}" stroke-width="2" stroke-opacity=".45"/>'
        f'<g transform="translate(38 36)">{glyph}</g>'
        f'<text x="70" y="37" class="d" font-size="{fit_size(title_text, 21, 220):.1f}" fill="{color}">{escape(title_text)}</text>'
        f'<text x="71" y="56" class="mo" font-size="10.5" fill="{color}" fill-opacity=".7">{escape(sub.upper())}</text></g>'
    )
    return svg(320, 80, f"{title_text} – {sub}", body)


def activity_card(t: dict, entries: list[dict]) -> str:
    """Recent activity as a log panel. entries: {kind, verb, repo, detail, ago}."""
    W, row = 1200, 50
    H = 116 + max(len(entries), 1) * row
    colors = {"push": "blue", "pr": "violet", "issue": "coral", "create": "teal", "release": "amber", "public": "teal"}
    body = [
        panel(4, 4, W - 18, H - 18, t),
        clipped("pc", 4, 4, W - 18, H - 18, halftone("ht", 4, 4, W - 18, H - 18, W - 14, H - 14, 460, t["coral"], .5)),
        caption(36, 34, "Activity log", t, fill=t["coral"]),
        f'<text x="{W - 50}" y="55" text-anchor="end" class="mo" font-size="11.5" fill="{t["muted"]}">LIVE FROM GITHUB · REFRESHED EVERY 6 H</text>',
    ]
    if entries:
        body.append(f'<line x1="56" y1="112" x2="56" y2="{112 + (len(entries) - 1) * row}" stroke="{t["line"]}" stroke-width="2" stroke-opacity=".3"/>')
    else:
        body.append(f'<text x="36" y="124" class="tx" font-size="18" fill="{t["muted"]}">No public activity yet.</text>')
    for i, e in enumerate(entries):
        y = 112 + i * row
        verb = e["verb"]
        vw = width(verb, 18, "d") + 8
        repo = ellipsize(e["repo"], 18, 640 - vw)
        rx = 82 + vw
        dx = rx + width(repo, 18, "tx") + 14
        detail = ellipsize(e.get("detail", ""), 15, W - 200 - dx) if e.get("detail") and W - 200 - dx > 80 else ""
        body.append(
            f'<g class="up" style="animation-delay:{.1 + i * .05:.2f}s">'
            f'<circle cx="56" cy="{y}" r="7" fill="{t[colors.get(e["kind"], "blue")]}" stroke="{t["line"]}" stroke-width="2"/>'
            f'<text x="82" y="{y + 6}" class="d" font-size="18" fill="{t["ink"]}">{escape(verb)}</text>'
            f'<text x="{rx:.0f}" y="{y + 6}" class="tx" font-size="18" fill="{t["ink"]}">{escape(repo)}</text>'
            + (f'<text x="{dx:.0f}" y="{y + 6}" class="tx" font-size="15" fill="{t["muted"]}">{escape(detail)}</text>' if detail else "")
            + f'<text x="{W - 50}" y="{y + 5}" text-anchor="end" class="mo" font-size="11.5" fill="{t["muted"]}">{escape(e["ago"].upper())}</text>'
            + (f'<line x1="82" y1="{y + 25}" x2="{W - 50}" y2="{y + 25}" stroke="{t["line"]}" stroke-opacity=".12" stroke-width="1.5"/>'
               if i < len(entries) - 1 else "")
            + "</g>"
        )
    return svg(W, H, "Recent public activity on GitHub", "".join(body))


# ── Static pages ──────────────────────────────────────────────────────────────────────────


def cover(t: dict) -> str:
    W, H = 1200, 420
    roles = ["IT & Project Manager", "Sales Manager", "Software Enthusiast"]
    extra = (".role{opacity:0;animation:role 12s ease-in-out infinite}"
             "@keyframes role{0%{opacity:0;transform:translateY(8px)}5%,28%{opacity:1;transform:none}33%,100%{opacity:0;transform:translateY(-8px)}}"
             "@media (prefers-reduced-motion:reduce){.role{opacity:0}.r0{opacity:1}}")
    body = [
        panel(4, 4, W - 18, H - 18, t),
        clipped("pc", 4, 4, W - 18, H - 18,
                f'<circle cx="975" cy="236" r="160" fill="{t["amber"]}" fill-opacity=".16"/>'
                + halftone("ht", 4, 4, W - 18, H - 18, 975, 236, 330, t["amber"], 1, 11)),
        f'<text x="36" y="44" class="mo fade" font-size="13" fill="{t["ink"]}">PASSIMORITZ COMICS</text>',
        f'<text x="{W - 50}" y="44" text-anchor="end" class="mo fade" font-size="13" fill="{t["muted"]}">ISSUE 01 · GITHUB EDITION · 2026</text>',
        f'<line x1="4" y1="64" x2="{W - 14}" y2="64" stroke="{t["line"]}" stroke-width="2.5"/>',
        caption(36, 96, "Servers, sales and Spotify themes", t, style="animation-delay:.1s"),
        f'<text x="30" y="226" class="d up" font-size="100" letter-spacing="-3" fill="{t["ink"]}" style="animation-delay:.18s">Pascal Moritz</text>',
        f'<rect x="36" y="248" width="80" height="6" rx="3" fill="{t["amber"]}" class="up" style="animation-delay:.3s"/>',
    ]
    for i, role in enumerate(roles):
        body.append(f'<text x="132" y="259" class="tx role r{i}" font-size="25" fill="{t["ink"]}" style="animation-delay:{i * 4}s">{escape(role)}</text>')
    body.append(bubble(806, 120, 330, 132, ["Hi! I steer IT projects, sell", "tech people believe in – and", "build tools at night, with a", "little help from AI."], t, 17,
                       tail=(-64, 38), style="animation-delay:.45s"))
    body.append(f'<line x1="36" y1="312" x2="{W - 50}" y2="312" stroke="{t["line"]}" stroke-width="1.5" stroke-opacity=".2"/>')
    body.append(f'<text x="36" y="346" class="mo up" font-size="11.5" fill="{t["muted"]}" style="animation-delay:.5s">IN THIS ISSUE</text>')
    x = 36
    for i, item in enumerate(["What I do", "In numbers", "Hostwerk", "Mirage", "Recent activity"]):
        body.append(f'<g class="up" style="animation-delay:{.55 + i * .05:.2f}s"><text x="{x}" y="378" class="mo" font-size="12" fill="{t["coral"]}">{i + 1:02d}</text>'
                    f'<text x="{x + 28}" y="379" class="tx" font-size="17" fill="{t["ink"]}">{escape(item)}</text></g>')
        x += 28 + width(item, 17, "tx") + 34
    return svg(W, H, "Passimoritz Comics, issue 1: Pascal Moritz – IT & Project Manager, Sales Manager, Software Enthusiast", "".join(body), extra)


CHAPTERS = [
    ("01", "What I do", "IT, projects, sales and building.", "amber"),
    ("02", "In numbers", "The last twelve months on GitHub.", "blue"),
    ("03", "Hostwerk", "The local server hub.", "teal"),
    ("04", "Mirage", "A living theme for Spotify.", "violet"),
    ("05", "Recent activity", "Live from GitHub.", "coral"),
]


def chapter(t: dict, num: str, name: str, narr: str, accent: str) -> str:
    W, H = 1200, 96
    tag = f"Chapter {num}"
    tw = caption_w(tag) + 3
    nw = width(name, 38, "d", -.8)
    end = tw + 16 + nw + 18 + width(narr, 17, "tx")
    body = [
        caption(4, 30, tag, t, fill=t[accent]),
        f'<text x="{tw + 16:.0f}" y="56" class="d up" font-size="38" letter-spacing="-.8" fill="{t["ink"]}" style="animation-delay:.08s">{escape(name)}</text>',
        f'<text x="{tw + 34 + nw:.0f}" y="55" class="tx up" font-size="17" fill="{t["muted"]}" style="animation-delay:.16s">{escape(narr)}</text>',
        f'<line x1="{end + 24:.0f}" y1="49" x2="{W - 30}" y2="49" stroke="{t["line"]}" stroke-width="2" stroke-opacity=".25" class="fade"/>',
        f'<rect x="{W - 24}" y="43" width="12" height="12" rx="2" fill="{t[accent]}" stroke="{t["line"]}" stroke-width="2" class="fade"/>',
    ]
    return svg(W, H, f"Chapter {num}: {name} – {narr}", "".join(body))


def origin(t: dict) -> str:
    """2×2 grid: what I do."""
    W, H = 1200, 540
    panels = [
        ("By day …", "IT & projects", "Digital initiatives, IT infrastructure and security governance – end to end.", "blue"),
        ("… and then", "Sales", "Turning technical solutions into clear, scalable business value.", "amber"),
        ("By night …", "AI-assisted building", "Apps, internal tools, themes and automations – prototyped fast, shipped for real.", "violet"),
        ("In the basement …", "Self-hosting", "Docker, Nginx and Linux servers for my own projects and services.", "teal"),
    ]
    pw, ph = 576, 248
    body = []
    for i, (narr, head, text, accent) in enumerate(panels):
        x, y = 4 + (i % 2) * (pw + 26), 4 + (i // 2) * (ph + 26)
        d, a = i * .1, t[accent]
        body.append(
            f'<g class="up" style="animation-delay:{d:.2f}s">{panel(x, y, pw, ph, t)}'
            + clipped(f"c{i}", x, y, pw, ph, halftone(f"h{i}", x, y, pw, ph, x + pw, y, 320, a, .8) + f'<rect x="{x}" y="{y}" width="8" height="{ph}" fill="{a}"/>')
            + f'<line x1="{x + 8}" y1="{y}" x2="{x + 8}" y2="{y + ph}" stroke="{t["line"]}" stroke-width="2"/>'
            f'<text x="{x + pw - 30}" y="{y + ph - 28}" text-anchor="end" class="d" font-size="84" fill="none" stroke="{a}" stroke-width="2" letter-spacing="-2">{i + 1:02d}</text></g>'
        )
        body.append(caption(x + 32, y + 28, narr, t, fill=a, style=f"animation-delay:{d + .08:.2f}s"))
        body.append(f'<text x="{x + 30}" y="{y + 110}" class="d up" font-size="{fit_size(head, 36, pw - 80):.0f}" letter-spacing="-.8" fill="{t["ink"]}" style="animation-delay:{d + .12:.2f}s">{escape(head)}</text>')
        for j, line in enumerate(wrap(text, 18, 370)):
            body.append(f'<text x="{x + 32}" y="{y + 150 + j * 26}" class="tx up" font-size="18" fill="{t["muted"]}" style="animation-delay:{d + .18:.2f}s">{escape(line)}</text>')
    return svg(W, H, "What I do: IT & projects, sales, AI-assisted building, self-hosting", "".join(body))


def footer(t: dict) -> str:
    W, H = 1200, 200
    body = [
        panel(4, 4, W - 18, H - 18, t),
        clipped("pc", 4, 4, W - 18, H - 18, halftone("ht", 4, 4, W - 18, H - 18, 4, H - 14, 380, t["amber"], .6)
                + halftone("hu", 4, 4, W - 18, H - 18, W - 14, 4, 380, t["amber"], .6)),
        f'<text x="595" y="56" text-anchor="middle" class="mo fade" font-size="12" fill="{t["muted"]}">END OF ISSUE 01</text>',
        f'<text x="595" y="116" text-anchor="middle" class="d up" font-size="52" letter-spacing="-1.5" fill="{t["ink"]}">To be continued …</text>',
        f'<text x="595" y="152" text-anchor="middle" class="tx up" font-size="17" fill="{t["muted"]}" style="animation-delay:.15s">'
        "Thanks for reading – a ★ on a repo is always appreciated.</text>",
    ]
    return svg(W, H, "To be continued – thanks for reading", "".join(body))


def main() -> None:
    write_themed("assets/cover", cover)
    write_themed("assets/origin", origin)
    write_themed("assets/footer", footer)
    for num, name, narr, accent in CHAPTERS:
        write_themed(f"assets/ch-{int(num)}", lambda t, a=(num, name, narr, accent): chapter(t, *a))
    print("comic pages written")


if __name__ == "__main__":
    main()
