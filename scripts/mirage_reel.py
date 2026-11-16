#!/usr/bin/env python3
"""Build assets/mirage-reel.webp: ONE animated comic strip of every Mirage screenshot and clip.

The pictures are read live from the public Mirage repository (assets/shots and assets/clips),
so new or changed screenshots show up on the profile on the next workflow run. The reel is only
rebuilt when the folders' git hashes change (stored in assets/mirage-reel.json).

Screenshots are held still and change with a comic panel wipe; the party clips play as recorded
(no zoom or camera move). German variants (*-de.*) are skipped.

Usage: [GITHUB_TOKEN=...] python scripts/mirage_reel.py [--force]
Needs Pillow (pip install pillow).
"""
import io
import json
import os
import re
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comic  # noqa: E402

REPO = "Passimoritz/spicetify-mirage"
OUT = "assets/mirage-reel.webp"
STATE = "assets/mirage-reel.json"
VERSION = 1  # bump to force a rebuild after changing this script

W, H = 960, 540
PX, PY, PW, PH = 14, 14, 924, 504  # panel box (shadow +8 is drawn outside)
HOLD_MS = 2000  # how long a screenshot stays
CLIP_MS = 2800  # how much of each clip is played
WIPE_FRAMES, WIPE_MS = 6, 45

# Known file names → comic caption; anything new gets a caption from its file name.
CAPTIONS = {
    "playlist": "PLAYLISTS · THE COVER PAINTS EVERYTHING",
    "album": "ALBUMS · THE HEADER MELTS INTO GLASS",
    "visualizer": "IMMERSIVE · A VISUALIZER ON THE BEAT",
    "mode-cover": "NOW PLAYING · COVER MODE",
    "mode-lyrics": "SING ALONG · LYRICS MODE",
    "mode-mix": "LYRICS + VISUALIZER · MIX MODE",
    "mode-viz": "VISUALIZER MODE",
    "mode-party": "PARTY MODE · LIGHTS AND CROWD",
    "venues": "PICK YOUR VENUE",
    "instruments": "INSTRUMENTS ON STAGE",
    "settings": "EVERYTHING ADJUSTABLE",
    "phone": "REMOTE ON YOUR PHONE",
    "edm": "PARTY · EDM",
    "house": "PARTY · HOUSE",
    "rock": "PARTY · ROCK",
    "techno": "PARTY · TECHNO",
    "karaoke": "PARTY · KARAOKE",
    "finale": "PARTY · THE FINALE",
}
SFX = ["BOOM!", "WUMM!", "BAM!", "WHOOSH!", "POW!", "ZING!"]
ORDER = ["playlist", "album", "edm", "mode-cover", "mode-lyrics", "house", "mode-mix", "mode-viz", "rock",
         "visualizer", "mode-party", "techno", "venues", "instruments", "karaoke", "settings", "phone", "finale"]


def get(url: str, raw: bool = False):
    headers = {"User-Agent": "profile-readme"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as resp:
        data = resp.read()
    return data if raw else json.loads(data)


def source_items() -> tuple[str, list[dict]]:
    """(state key, [{"name", "kind", "url"}]) from the Mirage repo."""
    root = get(f"https://api.github.com/repos/{REPO}/contents/assets")
    dirs = {e["name"]: e for e in root if e["type"] == "dir"}
    key = f"v{VERSION}:" + ":".join(dirs[d]["sha"] for d in ("shots", "clips") if d in dirs)
    items = []
    for folder, kind in (("shots", "shot"), ("clips", "clip")):
        if folder not in dirs:
            continue
        for entry in get(f"https://api.github.com/repos/{REPO}/contents/assets/{folder}"):
            stem, ext = os.path.splitext(entry["name"])
            if entry["type"] != "file" or ext.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".gif") or re.search(r"-de$", stem):
                continue
            items.append({"name": stem, "kind": kind, "url": entry["download_url"]})
    rank = {n: i for i, n in enumerate(ORDER)}
    items.sort(key=lambda it: (rank.get(it["name"], len(ORDER)), it["name"]))
    return key, items


def font(key: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(comic.FONT_DIR, comic.FONTS[key]), size)


def hexrgb(value: str) -> tuple:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


INK, PAPER, YELLOW = hexrgb(comic.INK), hexrgb(comic.PAPER), hexrgb(comic.YELLOW)
ACCENTS = [hexrgb(c) for c in (comic.VIOLET, comic.PINK, comic.CYAN, comic.GREEN, comic.ORANGE)]


def paper() -> Image.Image:
    """Cream page with a halftone dot screen."""
    page = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(page)
    for y in range(0, H, 12):
        for x in range((y // 12 % 2) * 6, W, 12):
            d.ellipse((x - 1.6, y - 1.6, x + 1.6, y + 1.6), fill=(240, 222, 186))
    d.rectangle((PX + 8, PY + 8, PX + PW + 8, PY + PH + 8), fill=INK)  # hard shadow
    return page


PAGE = None


def fit(img: Image.Image, w: int, h: int, accent: tuple) -> Image.Image:
    """Contain-fit the screenshot on a blurred, tinted copy of itself (no crop, no distortion)."""
    img = img.convert("RGB")
    bg = img.copy()
    scale = max(w / bg.width, h / bg.height)
    bg = bg.resize((int(bg.width * scale) + 1, int(bg.height * scale) + 1)).crop((0, 0, w, h))
    bg = bg.filter(ImageFilter.GaussianBlur(24))
    bg = Image.blend(bg, Image.new("RGB", (w, h), accent), .25)
    scale = min(w / img.width, h / img.height)
    fg = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    bg.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
    return bg


def caption(d: ImageDraw.ImageDraw, x: int, y: int, text: str, size: int, fill: tuple, color: tuple) -> None:
    f = font("bang", size)
    tw = d.textlength(text, font=f)
    w, h = tw + 24, size + 14
    d.rectangle((x + 5, y + 5, x + w + 5, y + h + 5), fill=INK)
    d.rectangle((x, y, x + w, y + h), fill=fill, outline=INK, width=4)
    d.text((x + 12, y + 6), text, font=f, fill=color)


def sfx(page: Image.Image, text: str, x: int, y: int, size: int, fill: tuple, angle: float) -> None:
    f = font("bang", size)
    box = ImageDraw.Draw(page).textbbox((0, 0), text, font=f, stroke_width=6)
    layer = Image.new("RGBA", (box[2] + 30, box[3] + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((14, 14), text, font=f, fill=INK, stroke_width=6, stroke_fill=INK)
    d.text((8, 8), text, font=f, fill=fill, stroke_width=6, stroke_fill=INK)
    layer = layer.rotate(angle, expand=True, resample=Image.BICUBIC)
    page.paste(layer, (x - layer.width // 2, y - layer.height // 2), layer)


def scene_frame(content: Image.Image, label: str, index: int, total: int, is_clip: bool) -> Image.Image:
    page = PAGE.copy()
    page.paste(content, (PX, PY))
    d = ImageDraw.Draw(page)
    d.rectangle((PX, PY, PX + PW, PY + PH), outline=INK, width=6)
    caption(d, PX + 18, PY + 16, label, 26, YELLOW, INK)
    tag = f"PANEL {index + 1}/{total}"
    tf = font("bang", 18)
    tw = d.textlength(tag, font=tf)
    d.rectangle((PX + PW - tw - 40, PY + PH - 44, PX + PW - 16, PY + PH - 16), fill=INK)
    d.text((PX + PW - tw - 28, PY + PH - 42), tag, font=tf, fill=YELLOW)
    if is_clip:
        sfx(page, SFX[index % len(SFX)], PX + 120, PY + PH - 70, 64, ACCENTS[index % len(ACCENTS)], 10)
    return page


def clip_frames(data: bytes, accent: tuple) -> list[tuple[Image.Image, int]]:
    im = Image.open(io.BytesIO(data))
    frames, spent = [], 0
    for i in range(getattr(im, "n_frames", 1)):
        im.seek(i)
        dur = im.info.get("duration") or 80
        frames.append((fit(im.copy(), PW, PH, accent), dur))
        spent += dur
        if spent >= CLIP_MS:
            break
    return frames


def build(items: list[dict]) -> tuple[list[Image.Image], list[int]]:
    global PAGE
    PAGE = paper()
    out, durs = [], []
    total = len(items)
    prev = None
    for index, item in enumerate(items):
        print(f"  {item['kind']:4} {item['name']}")
        data = get(item["url"], raw=True)
        accent = ACCENTS[index % len(ACCENTS)]
        label = CAPTIONS.get(item["name"], item["name"].replace("-", " ").replace("_", " ").upper())
        if item["kind"] == "clip":
            scenes = [(scene_frame(fr, label, index, total, True), d) for fr, d in clip_frames(data, accent)]
        else:
            scenes = [(scene_frame(fit(Image.open(io.BytesIO(data)), PW, PH, accent), label, index, total, False), HOLD_MS)]
        if prev is not None:
            # comic wipe: the new panel slides in from the right with an ink edge
            first = scenes[0][0]
            for step in range(1, WIPE_FRAMES + 1):
                t = 1 - (1 - step / (WIPE_FRAMES + 1)) ** 3
                cut = int(W * (1 - t))
                frame = prev.copy()
                frame.paste(first.crop((cut, 0, W, H)), (cut, 0))
                ImageDraw.Draw(frame).rectangle((cut - 6, 0, cut, H), fill=INK)
                out.append(frame)
                durs.append(WIPE_MS)
        for frame, dur in scenes:
            out.append(frame)
            durs.append(dur)
        prev = scenes[-1][0]
    return out, durs


def main() -> None:
    force = "--force" in sys.argv
    key, items = source_items()
    state = {}
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as handle:
            state = json.load(handle)
    if not force and state.get("source") == key and os.path.exists(OUT):
        print("mirage reel: up to date")
        return
    if not items:
        print("mirage reel: no pictures found, keeping the old reel")
        return
    print(f"mirage reel: building from {len(items)} pictures")
    frames, durs = build(items)
    frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=durs, loop=0,
                   quality=72, method=6, minimize_size=True, allow_mixed=True)
    with open(STATE, "w", encoding="utf-8") as handle:
        json.dump({"source": key, "pictures": [i["name"] for i in items], "frames": len(frames),
                   "seconds": round(sum(durs) / 1000, 1)}, handle, indent=2)
    print(f"mirage reel: {OUT} – {len(frames)} frames, {sum(durs) / 1000:.1f}s, {os.path.getsize(OUT) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
