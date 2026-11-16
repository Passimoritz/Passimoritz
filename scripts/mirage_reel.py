#!/usr/bin/env python3
"""Build assets/mirage-reel.webp: ONE animated panel of every Mirage screenshot and clip.

The pictures are read live from the public Mirage repository (assets/shots and assets/clips),
so new or changed screenshots show up on the profile on the next workflow run. The reel is only
rebuilt when the folders' git hashes change (stored in assets/mirage-reel.json).

The panel has a neutral ink border and no paper around it, so it sits well on both the light and
the dark GitHub theme. Screenshots hold still and cross-fade; the party clips play as
recorded (no zoom or camera move). German variants (*-de.*) are skipped.

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
VERSION = 3  # bump to force a rebuild after changing this script

W, H = 960, 540
BORDER = 4
HOLD_MS = 2200  # how long a screenshot stays
CLIP_MS = 2800  # how much of each clip is played
FADE_FRAMES, FADE_MS = 3, 70

# Known file names → caption; anything new gets a caption from its file name.
CAPTIONS = {
    "playlist": "Playlists · the cover paints everything",
    "album": "Albums · the header melts into glass",
    "visualizer": "Immersive · a visualizer on the beat",
    "mode-cover": "Now playing · cover mode",
    "mode-lyrics": "Sing along · lyrics mode",
    "mode-mix": "Lyrics + visualizer · mix mode",
    "mode-viz": "Visualizer mode",
    "mode-party": "Party mode · lights and crowd",
    "venues": "Pick your venue",
    "instruments": "Instruments on stage",
    "settings": "Everything adjustable",
    "phone": "Remote on your phone",
    "edm": "Party · EDM",
    "house": "Party · house",
    "rock": "Party · rock",
    "techno": "Party · techno",
    "karaoke": "Party · karaoke",
    "finale": "Party · the finale",
}
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


def hexrgb(value: str) -> tuple:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


INK = hexrgb(comic.LIGHT["ink"])
AMBER = hexrgb(comic.LIGHT["amber"])
TINTS = [hexrgb(comic.LIGHT[k]) for k in ("violet", "coral", "blue", "teal", "amber")]
MONO = ImageFont.truetype(os.path.join(comic.FONT_DIR, comic.FONTS["PMMono"][0]), 17)
MONO_S = ImageFont.truetype(os.path.join(comic.FONT_DIR, comic.FONTS["PMMono"][0]), 13)


def fit(img: Image.Image, accent: tuple) -> Image.Image:
    """Contain-fit the screenshot on a blurred, tinted copy of itself (no crop, no distortion)."""
    img = img.convert("RGB")
    scale = max(W / img.width, H / img.height)
    bg = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1)).crop((0, 0, W, H))
    bg = Image.blend(bg.filter(ImageFilter.GaussianBlur(28)), Image.new("RGB", (W, H), (16, 14, 24)), .45)
    bg = Image.blend(bg, Image.new("RGB", (W, H), accent), .08)
    scale = min(W / img.width, H / img.height)
    fg = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    return bg


def label(d: ImageDraw.ImageDraw, x: int, y: int, text: str) -> None:
    """Amber narrator caption with a hard ink shadow – the same caption box as the SVG pages."""
    text = text.upper()
    tw = sum(d.textlength(ch, font=MONO) + 1.2 for ch in text)
    w, h = tw + 24, 34
    d.rounded_rectangle((x + 3, y + 3, x + w + 3, y + h + 3), 3, fill=INK)
    d.rounded_rectangle((x, y, x + w, y + h), 3, fill=AMBER, outline=INK, width=2)
    cx = x + 13
    for ch in text:  # manual tracking, matches the SVG captions
        d.text((cx, y + 8), ch, font=MONO, fill=INK)
        cx += d.textlength(ch, font=MONO) + 1.2


def scene_frame(content: Image.Image, text: str, index: int, total: int) -> Image.Image:
    frame = content.convert("RGBA")
    d = ImageDraw.Draw(frame)
    label(d, 22, 20, text)
    tag = f"{index + 1:02d} / {total:02d}"
    tw = d.textlength(tag, font=MONO_S)
    d.rounded_rectangle((W - tw - 44, H - 46, W - 20, H - 20), 3, fill=INK)
    d.text((W - tw - 32, H - 41), tag, font=MONO_S, fill=AMBER)
    d.rectangle((0, 0, W - 1, H - 1), outline=INK, width=BORDER)
    return frame.convert("RGB")


def clip_frames(data: bytes, accent: tuple) -> list[tuple[Image.Image, int]]:
    im = Image.open(io.BytesIO(data))
    frames, spent = [], 0
    for i in range(getattr(im, "n_frames", 1)):
        im.seek(i)
        dur = im.info.get("duration") or 80
        frames.append((fit(im.copy(), accent), dur))
        spent += dur
        if spent >= CLIP_MS:
            break
    return frames


def build(items: list[dict]) -> tuple[list[Image.Image], list[int]]:
    out, durs = [], []
    total = len(items)
    prev = None
    for index, item in enumerate(items):
        print(f"  {item['kind']:4} {item['name']}")
        data = get(item["url"], raw=True)
        accent = TINTS[index % len(TINTS)]
        text = CAPTIONS.get(item["name"], item["name"].replace("-", " ").replace("_", " "))
        if item["kind"] == "clip":
            scenes = [(scene_frame(fr, text, index, total), d) for fr, d in clip_frames(data, accent)]
        else:
            scenes = [(scene_frame(fit(Image.open(io.BytesIO(data)), accent), text, index, total), HOLD_MS)]
        if prev is not None:  # soft cross-fade between panels
            first = scenes[0][0]
            for step in range(1, FADE_FRAMES + 1):
                out.append(Image.blend(prev, first, step / (FADE_FRAMES + 1)))
                durs.append(FADE_MS)
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
                   quality=62, method=4, minimize_size=True)
    with open(STATE, "w", encoding="utf-8") as handle:
        json.dump({"source": key, "pictures": [i["name"] for i in items], "frames": len(frames),
                   "seconds": round(sum(durs) / 1000, 1)}, handle, indent=2)
    print(f"mirage reel: {OUT} - {len(frames)} frames, {sum(durs) / 1000:.1f}s, {os.path.getsize(OUT) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
