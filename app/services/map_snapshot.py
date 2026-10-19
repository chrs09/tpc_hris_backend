"""Map thumbnail with a pin, and the street address, for a GPS point --
used by the photo watermark (app/services/watermark.py).

Source: OpenStreetMap (free, no key). Their usage policies ask for a real
User-Agent, at most ~1 address lookup per second, and caching -- so map
tiles and addresses are cached on disk and lookups are spaced out. Any
failure (offline, slow, refused) returns None and the photo is stamped
without the map / address; it never blocks an upload.
"""

import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from io import BytesIO

import requests
from PIL import Image, ImageDraw

from app.core.config import settings

USER_AGENT = "TytanPrimeHRIS/1.0 (photo watermark; contact: tytanprime.system@gmail.com)"
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
GEOCODE_URL = "https://nominatim.openstreetmap.org/reverse"
ZOOM = 17
TIMEOUT_S = 4
# All map tiles for one photo must arrive within this, or no map.
MAP_BUDGET_S = 5
CACHE_DIR = os.path.join(settings.UPLOAD_FOLDER, ".map-cache")

_geocode_lock = threading.Lock()
_last_geocode = [0.0]


def _cache_path(*parts) -> str:
    path = os.path.join(CACHE_DIR, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _tile(z: int, x: int, y: int):
    path = _cache_path("tiles", str(z), str(x), f"{y}.png")
    if os.path.exists(path):
        try:
            return Image.open(path).convert("RGB")
        except Exception:
            pass
    resp = requests.get(
        TILE_URL.format(z=z, x=x, y=y),
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_S,
    )
    resp.raise_for_status()
    with open(path, "wb") as fh:
        fh.write(resp.content)
    return Image.open(BytesIO(resp.content)).convert("RGB")


def _draw_pin(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int):
    """A red map pin whose tip touches (cx, cy)."""
    r = size // 2
    top = cy - size - r // 2
    draw.ellipse([cx - r, top, cx + r, top + 2 * r], fill=(220, 38, 38), outline=(120, 10, 10), width=2)
    draw.polygon([(cx - int(r * 0.75), top + int(r * 1.5)), (cx + int(r * 0.75), top + int(r * 1.5)), (cx, cy)], fill=(220, 38, 38))
    hole = max(2, r // 3)
    draw.ellipse([cx - hole, top + r - hole, cx + hole, top + r + hole], fill=(110, 10, 10))


def map_thumbnail(lat: float, lng: float, size: int = 256):
    """Square map centered on the point with a pin, or None."""
    try:
        n = 2 ** ZOOM
        px = (lng + 180.0) / 360.0 * n * 256
        lat_rad = math.radians(lat)
        py = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n * 256
        tx, ty = int(px // 256), int(py // 256)

        canvas = Image.new("RGB", (768, 768))
        cells = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        # In parallel, within MAP_BUDGET_S total (cached tiles are instant).
        pool = ThreadPoolExecutor(max_workers=len(cells))
        futures = {
            pool.submit(_tile, ZOOM, (tx + dx) % n, ty + dy): (dx, dy) for dx, dy in cells
        }
        done, pending = wait(futures, timeout=MAP_BUDGET_S)
        pool.shutdown(wait=False, cancel_futures=True)
        if pending:
            return None
        for future in done:
            dx, dy = futures[future]
            canvas.paste(future.result(), ((dx + 1) * 256, (dy + 1) * 256))

        # The point inside the 3x3 canvas, then a square around it.
        cx = int(px - (tx - 1) * 256)
        cy = int(py - (ty - 1) * 256)
        half = 128
        crop = canvas.crop((cx - half, cy - half, cx + half, cy + half))
        draw = ImageDraw.Draw(crop)
        _draw_pin(draw, half, half, 30)
        # Required credit for OpenStreetMap data.
        draw.rectangle([0, 256 - 14, 256, 256], fill=(255, 255, 255))
        draw.text((4, 256 - 13), "© OpenStreetMap", fill=(60, 60, 60))
        return crop.resize((size, size))
    except Exception:
        return None


def reverse_geocode(lat: float, lng: float):
    """{"title": "Consolacion, Central Visayas, Philippines",
    "address": "Maglasang Avenue, Tayud, Consolacion, ..."} or None.
    Cached per ~11 m (4 decimals)."""
    key = f"{lat:.4f},{lng:.4f}"
    path = _cache_path("geocode", key.replace(",", "_") + ".json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    try:
        with _geocode_lock:
            wait = 1.1 - (time.monotonic() - _last_geocode[0])
            if wait > 0:
                time.sleep(wait)
            resp = requests.get(
                GEOCODE_URL,
                params={"format": "jsonv2", "lat": lat, "lon": lng, "zoom": 18, "addressdetails": 1},
                headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
                timeout=TIMEOUT_S,
            )
            _last_geocode[0] = time.monotonic()
        resp.raise_for_status()
        data = resp.json()
        addr = data.get("address") or {}
        town = (
            addr.get("city")
            or addr.get("town")
            or addr.get("municipality")
            or addr.get("village")
            or addr.get("suburb")
        )
        region = addr.get("state") or addr.get("region") or addr.get("province")
        title = ", ".join(p for p in (town, region, addr.get("country")) if p) or None
        result = {"title": title, "address": data.get("display_name")}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(result, fh)
        return result
    except Exception:
        return None
