"""Shared, retrying image loading for local and cloud-synced media."""

import time
from typing import Optional

from PIL import Image

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass


def open_image_with_retry(
    file_path: str,
    attempts: int = 3,
    retry_delay: float = 0.2,
) -> Image.Image:
    """Open and fully load an image, retrying transient cloud-file read failures."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        image: Optional[Image.Image] = None
        try:
            image = Image.open(file_path)
            image.load()
            return image
        except (OSError, ValueError) as exc:
            last_error = exc
            if image is not None:
                image.close()
            if attempt + 1 < attempts and retry_delay > 0:
                time.sleep(retry_delay * (attempt + 1))

    if last_error is not None:
        raise last_error
    raise OSError(f"Could not open image: {file_path}")