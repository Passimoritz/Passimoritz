#!/usr/bin/env python3
"""Comic-book design kit for the profile: fonts, palette and drawing helpers shared by every SVG.

The profile reads like a comic issue: cover, chapters, panels, caption boxes, speech bubbles and
sound effects, drawn with thick ink lines and hard offset shadows on printed paper.

Fonts (SIL Open Font License, see scripts/fonts/OFL-*.txt) are embedded as base64 WOFF2 because
SVGs inside <img> cannot load external files. The subset lives in scripts/fonts/embedded.json, so
CI needs nothing beyond the standard library; it is rebuilt with fontTools when missing.

Run directly to (re)build the static comic assets:
  python scripts/comic.py            → assets/cover.svg, assets/ch-*.svg, assets/origin.svg, assets/footer.svg
"""
import base64
import json
import math
import os
from html import escape

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")
FONTS = {"bang": "Bangers-Regular.ttf", "cn": "ComicNeue-Bold.ttf"}
CHARS = "".join(chr(c) for c in range(32, 127)) + "·–—…’“”★✓→←äöüÄÖÜß€©×"

# Palette – a printed comic looks the same in light and dark mode
INK = "#14121f"
PAPER = "#fff7e3"
YELLOW = "#ffd23f"
CYAN = "#38bdf8"
VIOLET = "#a78bfa"
PINK = "#f472b6"
RED = "#ff5a5f"
GREEN = "#3ddc97"
ORANGE = "#ff9f1c"

_cache: dict = {}


def _fonts() -> dict:
    """{key: {"b64": woff2 base64, "upm": units per em, "adv": {char: advance}}}"""
    if "fonts" in _cache:
        return _cache["fonts"]
    path = os.path.join(FONT_DIR, "embedded.json")
    if not os.path.exists(path):
        from io import BytesIO

        from fontTools import subset
        from fontTools.ttLib import TTFont

        data = {}
        for key, name in FONTS.items():
            font = TTFont(os.path.join(FONT_DIR, name))
            opts = subset.Options()
            opts.flavor = "woff2"
            opts.layout_features = ["kern", "liga"]
            sub = subset.Subsetter(opts)
            sub.populate(text=CHARS)
            sub.subset(font)
            buf = BytesIO()
            font.flavor = "woff2"
            font.save(buf)
            full = TTFont(os.path.join(FONT_DIR, name))
            cmap, hmtx = full.getBestCmap(), full["hmtx"]
            adv = {ch: hmtx[cmap[ord(ch)]][0] for ch in CHARS if ord(ch) in cmap}
            data[key] = {"b64": base64.b64encode(buf.getvalue()).decode(), "upm": full["head"].unitsPerEm, "adv": adv}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
    with open(path, encoding="utf-8") as handle:
        _cache["fonts"] = json.load(handle)
    return _cache["fonts"]


def width(text: str, size: float, font: str = "bang", spacing: float = 0) -> float:
    """Rendered width of text in px (exact advances from the font)."""
    f = _fonts()[font]
    fallback = f["upm"] * 0.55
    return sum(f["adv"].get(ch, fallback) for ch in text) * size / f["upm"] + spacing * max(len(text) - 1, 0)


def font_css(*keys: str) -> str:
    fam = {"bang": "Bangers", "cn": "Comic Neue"}
    return "".join(
        f"@font-face{{font-family:'{fam[k]}';src:url(data:font/woff2;base64,{_fonts()[k]['b64']}) format('woff2')}}"
        for k in keys
    )


BASE_CSS = f"""
.bang{{font-family:'Bangers',Impact,'Arial Black',sans-serif;letter-spacing:1px}}
.cn{{font-family:'Comic Neue','Comic Sans MS','Segoe Print',sans-serif;font-weight:700}}
.ink{{stroke:{INK};stroke-linejoin:round;stroke-linecap:round}}
.pop{{transform-box:fill-box;transform-origin:center;animation:pop .55s cubic-bezier(.3,1.6,.5,1) both}}
.up{{animation:up .7s cubic-bezier(.2,.8,.2,1) both}}
.slide{{animation:slide .7s cubic-bezier(.2,.8,.2,1) both}}
.wig{{transform-box:fill-box;transform-origin:center;animation:wig 2.4s ease-in-out infinite}}
.pulse{{transform-box:fill-box;transform-origin:center;animation:pulse 1.8s ease-in-out infinite}}
.spin{{animation:spin 60s linear infinite}}
.drift{{animation:drift 12s linear infinite}}
@keyframes pop{{0%{{opacity:0;transform:scale(.2) rotate(-8deg)}}100%{{opacity:1;transform:none}}}}
@keyframes up{{from{{opacity:0;transform:translateY(16px)}}to{{opacity:1;transform:none}}}}
@keyframes slide{{from{{opacity:0;transform:translateX(-40px)}}to{{opacity:1;transform:none}}}}
@keyframes wig{{0%,100%{{transform:rotate(-4deg) scale(1)}}50%{{transform:rotate(4deg) scale(1.08)}}}}
@keyframes pulse{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.25)}}}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
@keyframes drift{{to{{transform:translate(22px,22px)}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
"""


def svg(w: int, h: int, label: str, body: str, extra_css: str = "", fonts: tuple = ("bang", "cn")) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="{escape(label)}"><style>{font_css(*fonts)}{BASE_CSS}{extra_css}</style>'
        f"{body}</svg>"
    )


def halftone(pid: str, color: str, size: int = 12, r: float = 2.2, opacity: float = 0.35) -> str:
    return (
        f'<pattern id="{pid}" width="{size}" height="{size}" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<circle cx="{size / 2}" cy="{size / 2}" r="{r}" fill="{color}" fill-opacity="{opacity}"/></pattern>'
    )


def panel(x, y, w, h, fill=PAPER, shadow=8, stroke=5, rx=6, cls="", style="") -> str:
    """Comic panel: hard ink shadow, then the panel with a thick ink border."""
    return (
        f'<g class="{cls}" style="{style}"><rect x="{x + shadow}" y="{y + shadow}" width="{w}" height="{h}" rx="{rx}" fill="{INK}"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" class="ink" stroke-width="{stroke}"/></g>'
    )


def caption_width(text, size=22, pad=12, font="bang") -> float:
    return width(text, size, font, 1 if font == "bang" else 0) + pad * 2 + 4


def caption(x, y, text, size=22, fill=YELLOW, color=INK, pad=12, font="bang", cls="", style="", skew=-4) -> str:
    """Narrator caption box (yellow rectangle, slightly skewed)."""
    w, h = caption_width(text, size, pad, font) - 4, size + pad * 1.3
    return (
        f'<g class="{cls}" style="{style}"><g transform="translate({x} {y}) skewX({skew})">'
        f'<rect x="4" y="4" width="{w:.0f}" height="{h:.0f}" fill="{INK}"/>'
        f'<rect width="{w:.0f}" height="{h:.0f}" fill="{fill}" class="ink" stroke-width="3.5"/>'
        f'<text x="{pad}" y="{h / 2 + size * 0.36:.1f}" class="{font}" font-size="{size}" fill="{color}">{escape(text)}</text></g></g>'
    )


def burst_points(cx, cy, r_out, r_in, n=14, jitter=(1, .86, 1.08, .92)) -> str:
    pts = []
    for i in range(n * 2):
        a = math.pi * i / n - math.pi / 2
        r = (r_out * jitter[(i // 2) % len(jitter)]) if i % 2 == 0 else r_in
        pts.append(f"{cx + r * math.cos(a):.1f},{cy + r * math.sin(a):.1f}")
    return " ".join(pts)


def burst(cx, cy, r, text, size=34, fill=YELLOW, color=INK, n=14, style="", sub="", sub_size=14) -> str:
    """Starburst sound effect with lettering (pops in, then wiggles)."""
    ty = cy + size * 0.36 - (sub_size * 0.6 if sub else 0)
    out = (
        f'<g class="pop" style="{style}"><g class="wig"><polygon points="{burst_points(cx + 5, cy + 5, r, r * .72, n)}" fill="{INK}"/>'
        f'<polygon points="{burst_points(cx, cy, r, r * .72, n)}" fill="{fill}" class="ink" stroke-width="4"/>'
        f'<text x="{cx}" y="{ty:.1f}" text-anchor="middle" class="bang" font-size="{size}" fill="{color}">{escape(text)}</text>'
    )
    if sub:
        out += f'<text x="{cx}" y="{ty + sub_size + 6:.1f}" text-anchor="middle" class="cn" font-size="{sub_size}" fill="{color}">{escape(sub)}</text>'
    return out + "</g></g>"


def sfx(x, y, text, size=56, fill=YELLOW, rotate=-8, style="") -> str:
    """Outlined sound-effect lettering (KA-CHING!, ZAP!) with a hard shadow."""
    return (
        f'<g class="pop" style="{style}"><g transform="translate({x} {y}) rotate({rotate})">'
        f'<text x="5" y="5" class="bang" font-size="{size}" fill="{INK}" stroke="{INK}" stroke-width="8" stroke-linejoin="round">{escape(text)}</text>'
        f'<text class="bang" font-size="{size}" fill="{fill}" stroke="{INK}" stroke-width="7" stroke-linejoin="round" paint-order="stroke">{escape(text)}</text>'
        f"</g></g>"
    )


def title(x, y, text, size=96, fill=YELLOW, anchor="start", shadow=7, cls="", style="", grad="") -> str:
    """Big outlined comic title with a 3D ink drop."""
    f = f"url(#{grad})" if grad else fill
    sw = max(size / 11, 4)
    return (
        f'<g class="{cls}" style="{style}">'
        f'<text x="{x + shadow}" y="{y + shadow}" text-anchor="{anchor}" class="bang" font-size="{size}" fill="{INK}" stroke="{INK}" stroke-width="{sw:.1f}" stroke-linejoin="round">{escape(text)}</text>'
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="bang" font-size="{size}" fill="{f}" stroke="{INK}" stroke-width="{sw:.1f}" stroke-linejoin="round" paint-order="stroke">{escape(text)}</text></g>'
    )


def bubble(x, y, w, h, lines, size=19, tail=(-40, 40), style="", fill="#ffffff") -> str:
    """Speech bubble with a tail; tail = (dx, dy) of the tip from the bubble's lower-left third."""
    tx, ty = x + w * 0.28, y + h
    tip_x, tip_y = tx + tail[0], ty + tail[1]
    path = (
        f"M{x + 22},{y} H{x + w - 22} Q{x + w},{y} {x + w},{y + 22} V{y + h - 22} Q{x + w},{y + h} {x + w - 22},{y + h} "
        f"H{tx + 34} L{tip_x},{tip_y} L{tx + 6},{ty} H{x + 22} Q{x},{y + h} {x},{y + h - 22} V{y + 22} Q{x},{y} {x + 22},{y} Z"
    )
    out = [f'<g class="pop" style="{style}">', f'<path d="{path}" fill="{INK}" transform="translate(6 6)"/>',
           f'<path d="{path}" fill="{fill}" class="ink" stroke-width="4"/>']
    lh = size * 1.3
    top = y + h / 2 - lh * (len(lines) - 1) / 2 + size * 0.35
    for i, line in enumerate(lines):
        out.append(f'<text x="{x + w / 2}" y="{top + i * lh:.1f}" text-anchor="middle" class="cn" font-size="{size}" fill="{INK}">{escape(line)}</text>')
    return "".join(out) + "</g>"


def rays(cx, cy, n, r, color, opacity=0.5) -> str:
    """Sunburst speed rays (every second wedge filled)."""
    out = []
    for i in range(0, n * 2, 2):
        a1, a2 = math.pi * i / n, math.pi * (i + 1) / n
        out.append(f"M{cx},{cy} L{cx + r * math.cos(a1):.0f},{cy + r * math.sin(a1):.0f} L{cx + r * math.cos(a2):.0f},{cy + r * math.sin(a2):.0f}Z")
    return f'<path d="{" ".join(out)}" fill="{color}" fill-opacity="{opacity}"/>'


def spin_rays(cx, cy, n, r, color, opacity, dur=60) -> str:
    return (f'<g transform="translate({cx} {cy})"><g class="spin" style="animation-duration:{dur}s">'
            f'{rays(0, 0, n, r, color, opacity)}</g></g>')


def wrap(text: str, size: float, max_w: float, font: str = "cn") -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        cand = f"{cur} {word}".strip()
        if width(cand, size, font) > max_w and cur:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


# ── Shared project spread (Hostwerk and Mirage use the same layout) ─────────────────────────


def project_card(name: str, issue: str, narrator: str, pitch: str, pills: list[str], badge_top: str,
                 badge_main: str, badge_sub: str, url_text: str, accent: str, accent2: str, sfx_text: str,
                 badge_colors: list[str] | None = None) -> str:
    """1200×330 comic splash panel for a project – the same layout for every project."""
    W, H = 1200, 330
    body = [
        "<defs>",
        halftone("ht", accent, 14, 2.6, .5),
        f'<linearGradient id="tg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{accent}"/><stop offset="1" stop-color="{accent2}"/></linearGradient>',
        f'<clipPath id="pc"><rect x="6" y="6" width="{W - 22}" height="{H - 22}" rx="6"/></clipPath>',
        "</defs>",
        panel(6, 6, W - 22, H - 22),
        '<g clip-path="url(#pc)">',
        f'<g class="drift"><rect x="-30" y="-30" width="{W + 60}" height="{H + 60}" fill="url(#ht)"/></g>',
        spin_rays(960, 165, 18, 760, accent, .2),
        "</g>",
        caption(30, 26, narrator, 20, cls="slide"),
        caption(30 + caption_width(narrator, 20) + 12, 26, issue, 20, fill=INK, color=PAPER, cls="slide", style="animation-delay:.1s"),
        title(34, 158, name, 104, grad="tg", cls="up", style="animation-delay:.15s"),
    ]
    for i, line in enumerate(wrap(pitch, 21, 640)[:2]):
        body.append(f'<text x="38" y="{202 + i * 28}" class="cn up" font-size="21" fill="{INK}" style="animation-delay:{.3 + i * .05:.2f}s">{escape(line)}</text>')
    x = 38
    for i, label in enumerate(pills):
        w = width(label, 15, "cn") + 30
        body.append(
            f'<g class="pop" style="animation-delay:{.5 + i * .1:.2f}s"><rect x="{x + 3}" y="{258}" width="{w:.0f}" height="34" rx="17" fill="{INK}"/>'
            f'<rect x="{x}" y="255" width="{w:.0f}" height="34" rx="17" fill="{YELLOW if i == 0 else PAPER}" class="ink" stroke-width="3"/>'
            f'<text x="{x + w / 2:.0f}" y="277" text-anchor="middle" class="cn" font-size="15" fill="{INK}">{escape(label)}</text></g>'
        )
        x += w + 12
    body.append(f'<text x="{x + 6}" y="277" class="cn up" font-size="14" fill="{INK}" fill-opacity=".7" style="animation-delay:.9s">→ {escape(url_text)}</text>')
    # right: starburst with the live number; its colour can cycle through the project's schemes
    fill_anim = ""
    if badge_colors:
        vals = ";".join(badge_colors + badge_colors[:1])
        fill_anim = f'<animate attributeName="fill" values="{vals}" dur="{len(badge_colors) * 2.5}s" repeatCount="indefinite"/>'
    size = 64 if width(badge_main, 64) < 140 else int(64 * 140 / width(badge_main, 64))
    sub_size = 15 if width(badge_sub, 15, "cn") < 150 else 15 * 150 / width(badge_sub, 15, "cn")
    body.append(
        f'<g class="pop" style="animation-delay:.35s"><g class="wig" style="animation-duration:3.2s">'
        f'<polygon points="{burst_points(965, 170, 132, 98, 16)}" fill="{INK}"/>'
        f'<polygon points="{burst_points(960, 165, 132, 98, 16)}" fill="{YELLOW}" class="ink" stroke-width="5">{fill_anim}</polygon>'
        f'<text x="960" y="128" text-anchor="middle" class="bang" font-size="21" fill="{INK}">{escape(badge_top)}</text>'
        f'<text x="960" y="{166 + size * .32:.0f}" text-anchor="middle" class="bang" font-size="{size}" fill="{INK}">{escape(badge_main)}</text>'
        f'<text x="960" y="{200 + size * .3:.0f}" text-anchor="middle" class="cn" font-size="{sub_size:.1f}" fill="{INK}">{escape(badge_sub)}</text>'
        "</g></g>"
    )
    body.append(sfx(1180 - width(sfx_text, 42) - 30, 296, sfx_text, 42, fill=accent, rotate=-8, style="animation-delay:.8s"))
    return svg(W, H, f"{name} – {pitch}", "".join(body))


def tile(inner: str, label: str, index: int) -> str:
    """64×64 sticker tile for an extension icon (hard shadow, ink border)."""
    return svg(64, 64, label, (
        f'<g class="pop" style="animation-delay:{0.2 + index * 0.04:.2f}s">'
        f'<rect x="7" y="7" width="53" height="53" rx="10" fill="{INK}"/>'
        f'<rect x="3" y="3" width="53" height="53" rx="10" fill="{PAPER}" class="ink" stroke-width="3"/>'
        f"{inner}</g>"
    ), fonts=("bang",) if 'class="bang"' in inner else ())


BUTTON_ICONS = {
    "arrow": '<path d="M0 -11v16M-7 -2l7 7 7-7M-11 11h22" fill="none" class="ink" stroke-width="3.2"/>',
    "windows": f'<g fill="{INK}"><rect x="-11" y="-11" width="10" height="10" rx="1.5"/><rect x="1" y="-11" width="10" height="10" rx="1.5"/>'
               '<rect x="-11" y="1" width="10" height="10" rx="1.5"/><rect x="1" y="1" width="10" height="10" rx="1.5"/></g>',
    "linux": '<g fill="none" class="ink" stroke-width="3"><rect x="-12" y="-11" width="24" height="22" rx="3"/><path d="M-7 -3l5 4-5 4M1 6h7"/></g>',
    "code": '<path d="M-5 -9l-8 9 8 9M5 -9l8 9-8 9" fill="none" class="ink" stroke-width="3.2"/>',
    "store": '<g fill="none" class="ink" stroke-width="3"><path d="M-12 -4h24l-2 15h-20z"/><path d="M-6 -4v-4a6 6 0 0 1 12 0v4"/></g>',
}


def button(title_text: str, sub: str, fill: str = YELLOW, icon: str = "arrow") -> str:
    """320×80 comic button: chunky ink border, hard shadow, Bangers label."""
    size = 25 if width(title_text, 25) < 222 else int(25 * 222 / width(title_text, 25))
    body = (
        f'<g class="pop"><rect x="9" y="9" width="306" height="66" rx="12" fill="{INK}"/>'
        f'<rect x="3" y="3" width="306" height="66" rx="12" fill="{fill}" class="ink" stroke-width="4"/>'
        f'<circle cx="40" cy="36" r="22" fill="{PAPER}" class="ink" stroke-width="3"/>'
        f'<g transform="translate(40 36)">{BUTTON_ICONS.get(icon, BUTTON_ICONS["arrow"])}</g>'
        f'<text x="74" y="37" class="bang" font-size="{size}" fill="{INK}">{escape(title_text)}</text>'
        f'<text x="75" y="57" class="cn" font-size="14" fill="{INK}">{escape(sub)}</text></g>'
    )
    return svg(320, 80, f"{title_text} – {sub}", body)


# ── Static pages ──────────────────────────────────────────────────────────────────────────


def cover() -> str:
    W, H = 1200, 440
    roles = [("THE IT & PROJECT MANAGER!", CYAN), ("THE SALES MANAGER!", PINK), ("THE SOFTWARE ENTHUSIAST!", GREEN)]
    css = (".role{opacity:0;animation:role 9s infinite}"
           "@keyframes role{0%{opacity:0;transform:translateX(-30px)}4%,30%{opacity:1;transform:none}34%,100%{opacity:0;transform:translateX(30px)}}"
           "@media (prefers-reduced-motion:reduce){.role{opacity:0}.r0{opacity:1}}")
    body = [
        "<defs>", halftone("ht", "#1d4ed8", 13, 2.6, .3),
        f'<linearGradient id="tg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{YELLOW}"/><stop offset="1" stop-color="{ORANGE}"/></linearGradient>',
        f'<clipPath id="pc"><rect x="6" y="6" width="{W - 22}" height="{H - 22}" rx="6"/></clipPath></defs>',
        panel(6, 6, W - 22, H - 22, fill=CYAN),
        '<g clip-path="url(#pc)">',
        spin_rays(330, 250, 22, 1100, "#ffffff", .3, 90),
        f'<g class="drift"><rect x="-30" y="-30" width="{W + 60}" height="{H + 60}" fill="url(#ht)"/></g>',
        f'<rect x="0" y="0" width="{W}" height="60" fill="{INK}"/>',
        f'<text x="30" y="43" class="bang" font-size="32" fill="{YELLOW}" letter-spacing="2">PASSIMORITZ COMICS</text>',
        f'<text x="{W - 40}" y="41" text-anchor="end" class="bang" font-size="22" fill="{PAPER}" letter-spacing="2">ISSUE #01 · GITHUB EDITION · FREE!</text>',
        "</g>",
        caption(34, 92, "IN A WORLD OF SERVERS, SALES AND SPOTIFY THEMES…", 21, cls="slide", style="animation-delay:.1s"),
        title(30, 252, "PASCAL MORITZ", 132, grad="tg", cls="up", style="animation-delay:.2s", shadow=9),
    ]
    for i, (text, color) in enumerate(roles):
        body.append(f'<g class="role r{i}" style="animation-delay:{i * 3}s">{caption(36, 282, text, 30, fill=color)}</g>')
    body += [
        bubble(770, 96, 380, 150, ["Hi! I steer IT projects,", "sell tech people believe in", "and build tools at night –", "with a little help from AI."], 19,
               tail=(-80, 46), style="animation-delay:.6s"),
        f'<g class="up" style="animation-delay:.8s"><rect x="40" y="366" width="700" height="44" fill="{INK}"/>'
        f'<rect x="36" y="362" width="700" height="44" fill="{PAPER}" class="ink" stroke-width="3.5"/>'
        f'<text x="52" y="392" class="bang" font-size="21" fill="{INK}">IN THIS ISSUE:</text>'
        f'<text x="182" y="391" class="cn" font-size="16" fill="{INK}">Origin story · Power levels · The Hostwerk saga · Mirage</text></g>',
        sfx(800, 380, "BOOM!", 62, fill=YELLOW, rotate=-10, style="animation-delay:1.1s"),
        burst(1075, 340, 68, "NEW!", 32, fill=PINK, sub="Mirage", sub_size=15, style="animation-delay:.9s", n=12),
    ]
    return svg(W, H, "Passimoritz Comics, issue 1: Pascal Moritz – IT & Project Manager, Sales Manager, Software Enthusiast", "".join(body), css)


CHAPTERS = [
    ("1", "ORIGIN STORY", "Every hero starts somewhere…", YELLOW),
    ("2", "POWER LEVELS", "The numbers never lie.", CYAN),
    ("3", "THE HOSTWERK SAGA", "Meanwhile, on a local server…", GREEN),
    ("4", "MIRAGE", "Meanwhile, inside Spotify…", VIOLET),
    ("5", "PREVIOUSLY ON GITHUB", "What happened lately.", PINK),
]


def chapter(num: str, name: str, narr: str, color: str) -> str:
    W, H = 1200, 110
    tag = f"CHAPTER {num}"
    tw = caption_width(tag, 24)
    nw = width(name, 48, spacing=1)
    body = [
        caption(8, 30, tag, 24, fill=YELLOW, color=INK, cls="slide"),
        title(tw + 26, 80, name, 48, fill=color, cls="slide", style="animation-delay:.1s", shadow=4),
        f'<text x="{tw + 50 + nw:.0f}" y="76" class="cn up" font-size="19" fill="{color}" style="animation-delay:.35s">{escape(narr)}</text>',
        f'<g class="up" style="animation-delay:.4s"><path d="M10 100 H{W - 34}" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-dasharray="2 12"/>'
        f'<circle cx="{W - 20}" cy="100" r="7" fill="{color}" class="pulse"/></g>',
    ]
    return svg(W, H, f"Chapter {num}: {name.title()} – {narr}", "".join(body))


def origin() -> str:
    """2×2 comic grid: what I do."""
    W, H = 1200, 600
    panels = [
        ("BY DAY…", "IT & PROJECTS", "Digital initiatives, IT infrastructure and security governance – end to end.", "CLICK!", CYAN),
        ("…AND THEN", "SALES", "Turning technical solutions into clear, scalable business value.", "KA-CHING!", YELLOW),
        ("BY NIGHT…", "AI-ASSISTED BUILDING", "Apps, internal tools, themes and automations – prototyped fast, shipped for real.", "ZAP!", PINK),
        ("IN THE BASEMENT…", "SELF-HOSTING", "Docker, Nginx and Linux servers for my own projects and services.", "VRRRM!", GREEN),
    ]
    pw, ph = 568, 270
    body = ["<defs>", halftone("hd", INK, 11, 1.6, .13)]
    for i in range(4):
        body.append(f'<clipPath id="c{i}"><rect x="{18 + (i % 2) * (pw + 30)}" y="{18 + (i // 2) * (ph + 30)}" width="{pw}" height="{ph}" rx="6"/></clipPath>')
    body.append("</defs>")
    for i, (narr, head, text, fx, color) in enumerate(panels):
        x, y = 18 + (i % 2) * (pw + 30), 18 + (i // 2) * (ph + 30)
        d = i * 0.18
        body.append(f'<g class="pop" style="animation-delay:{d:.2f}s">')
        body.append(panel(x, y, pw, ph, fill=color))
        body.append(f'<g clip-path="url(#c{i})">'
                    f'<g class="drift" style="animation-duration:{9 + i * 2}s"><rect x="{x - 30}" y="{y - 30}" width="{pw + 60}" height="{ph + 60}" fill="url(#hd)"/></g>'
                    f'{spin_rays(x + pw - 90, y + ph - 70, 12, 460, "#ffffff", .28, 70 + i * 10)}</g>')
        body.append(f'<rect x="{x}" y="{y}" width="{pw}" height="{ph}" rx="6" fill="none" class="ink" stroke-width="5"/></g>')
        body.append(caption(x + 18, y + 18, narr, 20, cls="slide", style=f"animation-delay:{d + .15:.2f}s"))
        hs = 46 if width(head, 46, spacing=1) < pw - 60 else 40
        body.append(title(x + 24, y + 112, head, hs, fill=PAPER, cls="up", style=f"animation-delay:{d + .25:.2f}s", shadow=4))
        lines = wrap(text, 20, 320)
        bh = 26 * len(lines) + 24
        bub = (f'<g class="up" style="animation-delay:{d + .35:.2f}s"><rect x="{x + 33}" y="{y + 143}" width="352" height="{bh}" rx="4" fill="{INK}"/>'
               f'<rect x="{x + 28}" y="{y + 138}" width="352" height="{bh}" rx="4" fill="{PAPER}" class="ink" stroke-width="3"/>')
        for j, line in enumerate(lines):
            bub += f'<text x="{x + 44}" y="{y + 166 + j * 26}" class="cn" font-size="20" fill="{INK}">{escape(line)}</text>'
        body.append(bub + "</g>")
        body.append(sfx(x + pw - 34 - width(fx, 50), y + ph - 30, fx, 50, fill=PAPER, rotate=-10, style=f"animation-delay:{d + .6:.2f}s"))
    return svg(W, H, "What I do: IT & projects, sales, AI-assisted building, self-hosting", "".join(body))


def footer() -> str:
    W, H = 1200, 250
    body = [
        "<defs>", halftone("ht", INK, 12, 2, .14), f'<clipPath id="pc"><rect x="6" y="6" width="{W - 22}" height="{H - 22}" rx="6"/></clipPath></defs>',
        panel(6, 6, W - 22, H - 22, fill=YELLOW),
        f'<g clip-path="url(#pc)">{spin_rays(600, 125, 20, 900, "#ffffff", .38, 80)}'
        f'<g class="drift"><rect x="-30" y="-30" width="{W + 60}" height="{H + 60}" fill="url(#ht)"/></g></g>',
        title(600, 120, "TO BE CONTINUED…", 92, fill=PAPER, anchor="middle", cls="up", shadow=7),
        f'<g class="up" style="animation-delay:.3s"><text x="600" y="170" text-anchor="middle" class="cn" font-size="22" fill="{INK}">'
        "Liked this issue? Drop a ★ on a repo – it's the applause of GitHub.</text>"
        f'<text x="600" y="202" text-anchor="middle" class="cn" font-size="17" fill="{INK}" fill-opacity=".75">'
        "Next issue: whatever I ship next. Thanks for reading!</text></g>",
        burst(112, 125, 70, "THE", 28, fill=PINK, sub="END?", sub_size=22, style="animation-delay:.5s", n=12),
        burst(1078, 125, 70, "★", 54, fill=CYAN, style="animation-delay:.7s", n=12),
    ]
    return svg(W, H, "To be continued – thanks for reading", "".join(body))


def main() -> None:
    root = os.path.dirname(HERE)
    out = {"assets/cover.svg": cover(), "assets/origin.svg": origin(), "assets/footer.svg": footer()}
    for num, name, narr, color in CHAPTERS:
        out[f"assets/ch-{num}.svg"] = chapter(num, name, narr, color)
    for path, content in out.items():
        with open(os.path.join(root, path), "w", encoding="utf-8") as handle:
            handle.write(content)
        print(f"{path}: {len(content) // 1024} KB")


if __name__ == "__main__":
    main()
