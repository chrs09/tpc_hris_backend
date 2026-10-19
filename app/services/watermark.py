"""The stamp on every photo taken through the system (trip photos,
attendance and kiosk selfies), in the style of a GPS map camera:

                                              ┌──────────────┐
                                              │ [T] Tytan Prime│
    ┌────────┐ ┌──────────────────────────────┴──────────────┐
    │  map   │ │ Consolacion, Central Visayas, Philippines    │
    │  with  │ │ Maglasang Avenue, Tayud, Consolacion, ...    │
    │  pin   │ │ Lat 10.359618, Long 123.973424               │
    │        │ │ Monday, 05/10/2026 08:08 AM GMT+08:00        │
    │        │ │ Note : Captured by Tytan Prime System · Ref  │
    └────────┘ └─────────────────────────────────────────────┘

plus a faint diagonal pattern of the photo's reference code over the
whole picture, so the stamp can't be cropped off or pasted onto another
photo. Each stamped photo is recorded (PhotoSeal: code + SHA-256 +
time/GPS) for Administrator -> Verify Photo. The map and address come
from OpenStreetMap (app/services/map_snapshot.py); without them the logo
takes the map's place.

Edit the look here (WATERMARK); every upload uses it. Changes apply to
new photos only -- stored photos keep the stamp they got.
"""

import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

WATERMARK = {
    "brand": "Tytan Prime",
    "note": "Note : Captured by Tytan Prime System",
    "logo_path": os.path.join(os.path.dirname(__file__), "..", "assets", "watermark-logo.jpg"),
    # Text size as a share of the photo's shorter side.
    "font_scale": 0.026,
    "title_scale": 1.3,  # the place line, relative to the text size
    "min_font_px": 13,
    # Dark see-through panels, white text.
    "panel_rgba": (20, 20, 20, 150),
    "text_rgb": (255, 255, 255),
    "subtle_rgb": (225, 225, 225),
    "corner_radius_scale": 0.6,  # of the text size
    "margin_scale": 0.02,  # gap from the photo's edges, of the shorter side
    "map_scale": 0.24,  # map square, of the shorter side
    # Anti-crop: the reference code (and time) repeated diagonally over the
    # WHOLE photo, faintly. 0 = off.
    "tile_opacity": 30,  # of 255 (~12%)
    "tile_rgb": (255, 255, 255),
    "tile_shadow_rgb": (0, 0, 0),
    "tile_angle": 30,  # degrees
    "tile_font_scale": 0.028,  # of the shorter side
}

FONTS = {
    "regular": (
        "arial.ttf",
        "Arial.ttf",
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "LiberationSans-Regular.ttf",
    ),
    "bold": (
        "arialbd.ttf",
        "Arial Bold.ttf",
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "LiberationSans-Bold.ttf",
    ),
}


def _font(size: int, weight: str = "regular"):
    for name in FONTS[weight] + FONTS["regular"]:
        try:
            return ImageFont.truetype(name, size=size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow 10.1+
    except Exception:
        return ImageFont.load_default()


@lru_cache(maxsize=1)
def _logo():
    try:
        return Image.open(WATERMARK["logo_path"]).convert("RGB")
    except Exception:
        return None


def _rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def _wrap(draw, text: str, font, width: int, max_lines: int = 3) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(",") + "…"
    return lines


def _tile(base: Image.Image, text: str) -> Image.Image:
    """The faint diagonal pattern over the whole photo (see tile_opacity).
    Drawn at up to 1400 px and scaled up -- full-size phone photos would
    take seconds otherwise; the pattern is faint, so it looks the same."""
    cfg = WATERMARK
    if not text or not cfg["tile_opacity"]:
        return base
    scale = min(1.0, 1400 / max(base.width, base.height))
    w, h = max(1, int(base.width * scale)), max(1, int(base.height * scale))
    short_side = min(w, h)
    font = _font(max(9, int(short_side * cfg["tile_font_scale"])))
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = probe.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    step_x, step_y = tw + th * 3, th * 5

    side = int((w ** 2 + h ** 2) ** 0.5) + step_x
    layer = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    alpha = cfg["tile_opacity"]
    shadow = max(1, th // 14)
    for row, y in enumerate(range(0, side, step_y)):
        offset = (row % 2) * (step_x // 2)
        for x in range(-step_x + offset, side, step_x):
            draw.text((x + shadow, y + shadow), text, font=font, fill=cfg["tile_shadow_rgb"] + (alpha,))
            draw.text((x, y), text, font=font, fill=cfg["tile_rgb"] + (alpha,))
    layer = layer.rotate(cfg["tile_angle"], resample=Image.BICUBIC)
    left, top = (side - w) // 2, (side - h) // 2
    layer = layer.crop((left, top, left + w, top + h))
    if layer.size != base.size:
        layer = layer.resize(base.size, Image.BICUBIC)
    return Image.alpha_composite(base, layer)


def stamp(image: Image.Image, info: dict) -> Image.Image:
    """Returns an RGB copy of `image` with the pattern and the GPS-camera
    style stamp. `info` keys (all optional): title, address, lat, lng,
    when (e.g. "Monday, 05/10/2026 08:08 AM GMT+08:00"), label (location
    check), ref, tile_text, map (PIL image of the map with its pin)."""
    cfg = WATERMARK
    base = _tile(image.convert("RGBA"), info.get("tile_text"))
    W, H = base.size
    short = min(W, H)
    font_px = max(cfg["min_font_px"], int(short * cfg["font_scale"]))
    body = _font(font_px)
    title_font = _font(int(font_px * cfg["title_scale"]), "bold")
    small = _font(max(cfg["min_font_px"] - 2, int(font_px * 0.85)))
    margin = max(6, int(short * cfg["margin_scale"]))
    pad = max(8, int(font_px * 0.7))
    gap = max(3, font_px // 4)
    radius = max(6, int(font_px * cfg["corner_radius_scale"]))
    probe = ImageDraw.Draw(base)

    map_side = int(short * cfg["map_scale"])
    panel_x1 = W - margin
    text_w = panel_x1 - (margin + map_side + pad) - pad * 2
    if text_w < font_px * 10:  # narrow photo: no side map
        map_side = 0
        text_w = W - margin * 2 - pad * 2

    # Lines: (text, font, color)
    lines = []
    if info.get("title"):
        lines += [(t, title_font, cfg["text_rgb"]) for t in _wrap(probe, info["title"], title_font, text_w, 2)]
    if info.get("address"):
        lines += [(t, body, cfg["text_rgb"]) for t in _wrap(probe, info["address"], body, text_w, 2)]
    if info.get("lat") is not None and info.get("lng") is not None:
        lines.append((f"Lat {info['lat']:.6f}, Long {info['lng']:.6f}", body, cfg["text_rgb"]))
    if info.get("when"):
        lines.append((info["when"], body, cfg["text_rgb"]))
    if info.get("label"):
        lines += [(t, body, cfg["subtle_rgb"]) for t in _wrap(probe, info["label"], body, text_w, 2)]
    note = cfg["note"] + (f" · Ref: {info['ref']}" if info.get("ref") else "")
    lines += [(t, small, cfg["subtle_rgb"]) for t in _wrap(probe, note, small, text_w, 2)]

    heights = []
    for text, font, _ in lines:
        box = probe.textbbox((0, 0), text, font=font)
        heights.append((box[1], box[3] - box[1]))
    text_h = sum(h for _, h in heights) + gap * (len(lines) - 1)
    panel_h = text_h + pad * 2
    if map_side:
        map_side = min(map_side, max(panel_h, int(short * 0.16)))
        panel_h = max(panel_h, map_side)

    y0 = H - margin - panel_h
    panel_x0 = margin + (map_side + pad if map_side else 0)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle([panel_x0, y0, panel_x1, y0 + panel_h], radius=radius, fill=cfg["panel_rgba"])

    # Left square: the map with its pin, else the logo.
    if map_side:
        square = info.get("map") or _logo()
        if square is not None:
            tile = square.convert("RGB").resize((map_side, map_side))
            overlay.alpha_composite(_rounded(tile, radius), (margin, y0 + panel_h - map_side))

    # Brand badge above the panel's right end: logo + "Tytan Prime".
    badge_font = _font(max(cfg["min_font_px"], int(font_px * 0.95)), "bold")
    bb = probe.textbbox((0, 0), cfg["brand"], font=badge_font)
    badge_h = (bb[3] - bb[1]) + pad
    logo = _logo()
    logo_side = badge_h - pad // 2 if logo else 0
    badge_w = pad + (logo_side + pad // 2 if logo else 0) + (bb[2] - bb[0]) + pad
    bx0, by1 = panel_x1 - badge_w, y0 - max(2, gap)
    by0 = by1 - badge_h
    if by0 > margin:
        draw.rounded_rectangle([bx0, by0, panel_x1, by1], radius=radius, fill=cfg["panel_rgba"])
        lx = bx0 + pad
        if logo:
            overlay.alpha_composite(
                _rounded(logo.resize((logo_side, logo_side)), max(3, logo_side // 5)),
                (lx, by0 + (badge_h - logo_side) // 2),
            )
            lx += logo_side + pad // 2
        draw.text((lx, by0 + (badge_h - (bb[3] - bb[1])) // 2 - bb[1]), cfg["brand"], font=badge_font, fill=cfg["text_rgb"] + (255,))

    tx, ty = panel_x0 + pad, y0 + (panel_h - text_h) // 2
    for (text, font, color), (top, h) in zip(lines, heights):
        draw.text((tx, ty - top), text, font=font, fill=color + (255,))
        ty += h + gap

    return Image.alpha_composite(base, overlay).convert("RGB")
