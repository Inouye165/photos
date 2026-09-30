"""
Non-destructive Thumbnail & HD Preview Generator for LuminaPhoto.
Creates and caches WebP thumbnails in a dedicated local cache directory without modifying original files.
Automatically respects EXIF rotation orientation.
"""

import os
import logging
import uuid
from typing import Optional
from PIL import Image, ImageOps
from backend.image_loader import open_image_with_retry

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".lumina_cache", "thumbnails")
logger = logging.getLogger(__name__)

def ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)

def get_thumbnail_path(photo_id: int, size_type: str = "thumb") -> str:
    """Returns the cached path for a given photo ID and size ('thumb' = 300px, 'preview' = 1200px)."""
    ensure_cache_dir()
    return os.path.join(CACHE_DIR, f"{photo_id}_{size_type}.webp")

def generate_thumbnail(
    file_path: str,
    photo_id: int,
    size_type: str = "thumb",
    force: bool = False,
) -> Optional[str]:
    """
    Generates a cached WebP thumbnail/preview for a photo.
    Non-destructive: original file is only read.
    """
    out_path = get_thumbnail_path(photo_id, size_type)
    if os.path.exists(out_path) and not force:
        return out_path

    max_dim = 320 if size_type == "thumb" else (4096 if size_type == "full" else 1920)
    quality = 82 if size_type == "thumb" else (92 if size_type == "full" else 88)
    temp_path = f"{out_path}.{uuid.uuid4().hex}.tmp"

    try:
        with open_image_with_retry(file_path) as source:
            # Auto-rotate image according to EXIF orientation tag
            img = ImageOps.exif_transpose(source)
            
            # Convert to RGB if RGBA/P/CMYK
            if img.mode in ("RGBA", "LA", "P"):
                # Use a clean dark background for transparent graphics if needed
                rgb_img = Image.new("RGB", img.size, (18, 18, 24))
                if img.mode == "P":
                    img = img.convert("RGBA")
                rgb_img.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
                img = rgb_img
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # High quality downsampling
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            img.save(temp_path, format="WEBP", quality=quality, method=4)
            os.replace(temp_path, out_path)
            return out_path
    except Exception as exc:
        logger.warning(
            "Could not generate %s thumbnail for photo %s (%s): %s",
            size_type,
            photo_id,
            file_path,
            exc,
            exc_info=True,
        )
        return None
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
