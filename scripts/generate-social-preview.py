#!/usr/bin/env python3
"""Build the GitHub social preview from the real fictional-data screenshots."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "social-preview.png"
WIDTH, HEIGHT = 1280, 640


def font(size, bold=False):
    candidates = [
        "/System/Library/Fonts/SFNS.ttf" if not bold else "/System/Library/Fonts/SFNSBold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def rounded_screenshot(path, size, radius=18):
    source = Image.open(path).convert("RGB")
    crop_height = min(760, source.height)
    source = source.crop((0, 0, source.width, crop_height))
    source.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "#0b0d12")
    x = (size[0] - source.width) // 2
    y = (size[1] - source.height) // 2
    canvas.paste(source, (x, y))
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    canvas.putalpha(mask)
    return canvas


image = Image.new("RGB", (WIDTH, HEIGHT), "#090b10")
pixels = image.load()
for y in range(HEIGHT):
    for x in range(WIDTH):
        glow = max(0.0, 1.0 - (((x - 640) / 760) ** 2 + ((y - 150) / 520) ** 2))
        pixels[x, y] = (
            int(8 + 8 * glow),
            int(10 + 12 * glow),
            int(16 + 23 * glow),
        )

draw = ImageDraw.Draw(image)
draw.text((64, 43), "CHAT SESSION MANAGERS", font=font(50, bold=True), fill="#f7f8fb")
draw.text((66, 105), "Codex  ·  Claude Code  ·  Grok", font=font(25), fill="#aeb7c9")

badge_text = "LOCAL-FIRST   ·   UNIVERSAL 2   ·   ENGLISH + CHINESE"
badge_font = font(17, bold=True)
box = draw.textbbox((0, 0), badge_text, font=badge_font)
badge_w = box[2] - box[0] + 34
draw.rounded_rectangle((WIDTH - badge_w - 66, 64, WIDTH - 66, 105), radius=20, fill="#182035", outline="#34466e", width=2)
draw.text((WIDTH - badge_w - 49, 75), badge_text, font=badge_font, fill="#cbd8ff")

cards = [
    ("codex.png", "CODEX", "#4b8cff"),
    ("claude-code.png", "CLAUDE CODE", "#ff956c"),
    ("grok.png", "GROK", "#a98cff"),
]
card_w, card_h = 354, 306
start_x, gap, top = 64, 44, 178

for index, (filename, label, accent) in enumerate(cards):
    x = start_x + index * (card_w + gap)
    shadow = Image.new("RGBA", (card_w + 30, card_h + 30), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((15, 15, card_w + 14, card_h + 14), radius=22, fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(11))
    image.paste(shadow, (x - 15, top - 8), shadow)

    draw.rounded_rectangle((x - 2, top - 2, x + card_w + 1, top + card_h + 1), radius=21, fill=accent)
    shot = rounded_screenshot(ROOT / "docs" / "screenshots" / "en" / filename, (card_w, card_h))
    image.paste(shot, (x, top), shot)
    draw.text((x, top + card_h + 20), label, font=font(22, bold=True), fill=accent)

draw.text((64, 570), "Browse, search, archive, restore, and safely delete local AI coding sessions.", font=font(23), fill="#d9deea")
draw.text((64, 607), "Private by design · No cloud database · macOS 13+", font=font(17), fill="#7f8ba3")

OUT.parent.mkdir(parents=True, exist_ok=True)
image.save(OUT, optimize=True, compress_level=9)
print(OUT)
