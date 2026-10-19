"""The stamp on every photo taken through the system (trip photos,
attendance and kiosk selfies): a panel in the lower-right corner of the
photo with the Tytan Prime logo, the date and time, the GPS, and
"Captured By: Tytan Prime System".

    ┌────────┬───────────────────────────────┐
    │  LOGO  │ Oct 15, 2026 02:14 PM PHT     │
    │        │ GPS: 10.317912, 123.993630    │
    │        │ Captured By: Tytan Prime System│
    └────────┴───────────────────────────────┘

Edit the look here (WATERMARK below); every upload uses it. Changes
apply to new photos only -- stored photos keep the stamp they got.
"""

import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

WATERMARK = {
    # Bottom line of the panel.
    "caption": "Captured By: Tytan Prime System",
    # The login screen's logo (copied from the web app's assets).
    "logo_path": os.path.join(os.path.dirname(__file__), "..", "assets", "watermark-logo.jpg"),
    # Text size as a share of the photo's shorter side.
    "font_scale": 0.032,
    "min_font_px": 14,
    # Panel: light, slightly see-through, so the photo shows around it.
    "panel_rgba": (255, 255, 255, 215),
    "text_rgb": (20, 20, 20),
    "logo_background_rgb": (255, 255, 255),
    "corner_radius_scale": 0.25,  # of the font size
    "margin_scale": 0.02,  # gap from the photo's edges, of the shorter side
}

FONT_CANDIDATES = (
    "arial.ttf",
    "Arial.ttf",
    "DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "LiberationSans-Regular.ttf",
)


def _font(size: int):
    for name in FONT_CANDIDATES:
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


def stamp(image: Image.Image, lines: list[str]) -> Image.Image:
    """Returns an RGB copy of `image` with the panel in its lower-right
    corner. `lines` are the info lines (date, GPS, location); the caption
    is added as the last line."""
    cfg = WATERMARK
    base = image.convert("RGBA")
    short_side = min(base.width, base.height)
    font_px = max(cfg["min_font_px"], int(short_side * cfg["font_scale"]))
    font = _font(font_px)
    caption_font = _font(max(cfg["min_font_px"] - 2, int(font_px * 0.85)))

    all_lines = [(text, font) for text in lines if text] + [(cfg["caption"], caption_font)]
    probe = ImageDraw.Draw(base)
    sizes = []
    for text, f in all_lines:
        box = probe.textbbox((0, 0), text, font=f)
        sizes.append((box[2] - box[0], box[3] - box[1]))

    gap = max(4, font_px // 3)
    pad = max(8, font_px // 2)
    text_w = max(w for w, _ in sizes)
    text_h = sum(h for _, h in sizes) + gap * (len(sizes) - 1)

    # Logo square as tall as the text block.
    logo = _logo()
    logo_side = text_h + pad if logo else 0
    inner_gap = pad if logo else 0

    panel_w = pad + logo_side + inner_gap + text_w + pad
    panel_h = pad + max(text_h, logo_side) + pad
    # Never wider than the photo (very small images): shrink to fit.
    margin = max(6, int(short_side * cfg["margin_scale"]))
    if panel_w + margin * 2 > base.width:
        scale = (base.width - margin * 2) / panel_w
        if scale < 0.5:
            return image.convert("RGB")
        return stamp(image.resize((int(image.width / scale), int(image.height / scale))), lines).resize(
            image.size
        )

    x0 = base.width - margin - panel_w
    y0 = base.height - margin - panel_h
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(
        [x0, y0, x0 + panel_w, y0 + panel_h],
        radius=max(4, int(font_px * cfg["corner_radius_scale"])),
        fill=cfg["panel_rgba"],
    )

    if logo:
        lx, ly = x0 + pad, y0 + (panel_h - logo_side) // 2
        draw.rectangle([lx, ly, lx + logo_side, ly + logo_side], fill=cfg["logo_background_rgb"] + (255,))
        overlay.paste(logo.resize((logo_side, logo_side)), (lx, ly))

    tx = x0 + pad + logo_side + inner_gap
    ty = y0 + (panel_h - text_h) // 2
    for (text, f), (_, h) in zip(all_lines, sizes):
        # textbbox has a top offset; draw from the box's own top.
        top = probe.textbbox((0, 0), text, font=f)[1]
        draw.text((tx, ty - top), text, font=f, fill=cfg["text_rgb"] + (255,))
        ty += h + gap

    return Image.alpha_composite(base, overlay).convert("RGB")
