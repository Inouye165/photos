"""
LuminaPhoto Icon Generator.
Generates and caches high-quality system tray and window icons matching the LuminaPhoto brand.
"""

import os
from PIL import Image, ImageDraw

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".lumina_cache")
ICON_ICO_PATH = os.path.join(CACHE_DIR, "lumina.ico")
ICON_PNG_PATH = os.path.join(CACHE_DIR, "lumina.png")

def create_lumina_icon_image(size: int = 128) -> Image.Image:
    """
    Renders a sleek LuminaPhoto brand icon with dark backdrop,
    emerald-cyan camera body, glowing lens aperture, and flash dot.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = size * 0.08
    # Rounded dark slate squircle base
    rect_coords = [pad, pad, size - pad, size - pad]
    radius = size * 0.22
    draw.rounded_rectangle(rect_coords, radius=radius, fill=(15, 23, 42, 255))

    # Camera top bump / viewfinder
    top_w = size * 0.35
    top_h = size * 0.12
    top_left = (size - top_w) / 2
    draw.rounded_rectangle(
        [top_left, pad * 1.5, top_left + top_w, pad * 1.5 + top_h],
        radius=size * 0.04,
        fill=(16, 185, 129, 230)
    )

    # Outer lens ring (emerald gradient effect)
    center = size / 2
    outer_r = size * 0.28
    draw.ellipse(
        [center - outer_r, center - outer_r + (size * 0.04),
         center + outer_r, center + outer_r + (size * 0.04)],
        outline=(16, 185, 129, 255),
        width=int(max(2, size * 0.06))
    )

    # Inner lens ring (cyan)
    inner_r = size * 0.18
    draw.ellipse(
        [center - inner_r, center - inner_r + (size * 0.04),
         center + inner_r, center + inner_r + (size * 0.04)],
        fill=(6, 182, 212, 220)
    )

    # Center lens aperture core (deep indigo)
    core_r = size * 0.09
    draw.ellipse(
        [center - core_r, center - core_r + (size * 0.04),
         center + core_r, center + core_r + (size * 0.04)],
        fill=(99, 102, 241, 255)
    )

    # Flash / indicator dot
    flash_r = size * 0.05
    flash_x = size - pad * 2.2
    flash_y = pad * 2.2
    draw.ellipse(
        [flash_x - flash_r, flash_y - flash_r, flash_x + flash_r, flash_y + flash_r],
        fill=(52, 211, 153, 255)
    )

    return img

def get_lumina_icon_image(size: int = 64) -> Image.Image:
    """Returns a PIL Image suitable for pystray or window icon."""
    return create_lumina_icon_image(size)

def ensure_icon_files() -> str:
    """Ensures .ico and .png are generated and returns the path to the .ico file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    if not os.path.exists(ICON_ICO_PATH) or not os.path.exists(ICON_PNG_PATH):
        img_large = create_lumina_icon_image(256)
        img_large.save(ICON_PNG_PATH, format="PNG")
        # Save multi-size ICO
        img_large.save(
            ICON_ICO_PATH,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        )
    return ICON_ICO_PATH
