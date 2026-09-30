"""
Intelligent Real Camera Photo vs Computer Graphic / Screenshot Classifier for LuminaPhoto.
Evaluates camera hardware EXIF, screenshot naming patterns, screen resolutions, and aspect ratios.
"""

import re
from typing import Dict, Any, Tuple

# Known camera and smartphone manufacturers
KNOWN_CAMERA_MAKES = {
    "apple", "canon", "nikon", "sony", "samsung", "google", "fujifilm", "fuji",
    "leica", "dji", "gopro", "olympus", "panasonic", "lumix", "pentax", "hasselblad",
    "ricoh", "phase one", "red", "motorola", "huawei", "xiaomi", "oneplus", "oppo",
    "vivo", "lg electronics", "lg", "htc", "nokia", "blackmagic design", "insta360"
}

# Standard computer and mobile screen resolutions (width x height or height x width)
COMMON_SCREEN_RESOLUTIONS = {
    (1920, 1080), (1080, 1920),
    (2560, 1440), (1440, 2560),
    (3840, 2160), (2160, 3840),
    (1366, 768),  (768, 1366),
    (1280, 720),  (720, 1280),
    (1440, 900),  (900, 1440),
    (1680, 1050), (1050, 1680),
    (1280, 800),  (800, 1280),
    (2880, 1800), (1800, 2880),
    (3024, 1964), (1964, 3024),
    (3456, 2234), (2234, 3456),
    (1170, 2532), (2532, 1170),
    (1290, 2796), (2796, 1290),
    (1179, 2556), (2556, 1179),
    (1080, 2400), (2400, 1080),
    (1080, 2340), (2340, 1080),
    (1440, 3120), (3120, 1440),
    (1440, 3088), (3088, 1440)
}

# Screenshot filename regex
SCREENSHOT_PATTERN = re.compile(
    r"(screenshot|screen[\s_-]?shot|captura|snip|screencap|capture[\s_-]|screen[\s_-]|pasted[\s_-]image|cleanshot|lightshot)",
    re.IGNORECASE
)

# Common web/system asset naming patterns
ASSET_PATTERN = re.compile(
    r"(icon|button|banner|sprite|logo|badge|avatar|thumbnail|favicon|asset|vector|graphic)",
    re.IGNORECASE
)

def classify_media(metadata: Dict[str, Any]) -> Tuple[str, float, str]:
    """
    Classifies media into:
    - 'VERIFIED_PHOTO': Definite camera photo with authentic EXIF camera/lens/GPS data.
    - 'LIKELY_PHOTO': Probable camera photo (e.g. social media stripped EXIF, JPEG/HEIC, photo dimensions).
    - 'SCREENSHOT': Screen capture or snip.
    - 'SYSTEM_ASSET': Small computer graphic, icon, banner, or UI element.
    - 'VIDEO': Video file.
    - 'UNSUPPORTED': Unsupported or unreadable file.

    Returns:
        (classification_str, score, reason_description)
    """
    ext = metadata.get("file_extension", "").lower()
    file_name = metadata.get("file_name", "")
    width = metadata.get("width")
    height = metadata.get("height")
    camera_make = metadata.get("camera_make")
    camera_model = metadata.get("camera_model")
    iso = metadata.get("iso")
    f_number = metadata.get("f_number")
    exposure_time = metadata.get("exposure_time")
    lens_model = metadata.get("lens_model")
    has_gps = metadata.get("latitude") is not None
    file_size = metadata.get("file_size", 0)

    # 1. Video check
    if metadata.get("format") == "VIDEO" or ext in {".mp4", ".mov", ".m4v", ".avi", ".mkv"}:
        return "VIDEO", 1.0, "Identified video media file"

    # 2. Excluded non-photo extensions (GIF, SVG, ICO, etc.)
    if ext in {".gif", ".ico", ".svg", ".cur", ".bmp"}:
        return "SYSTEM_ASSET", 0.95, f"Non-photo extension ({ext})"

    if metadata.get("format") == "UNREADABLE":
        return "UNSUPPORTED", 1.0, "Image could not be decoded"

    # 3. Definite Camera Photo via EXIF Hardware Fingerprint
    camera_make_lower = (camera_make or "").lower()
    is_known_camera = any(brand in camera_make_lower for brand in KNOWN_CAMERA_MAKES)
    has_optical_exif = (iso is not None or f_number is not None or exposure_time is not None or lens_model is not None)

    if (camera_make and is_known_camera) or (camera_model and has_optical_exif) or has_gps:
        details = []
        if camera_make or camera_model:
            details.append(f"Camera: {camera_make or ''} {camera_model or ''}".strip())
        if has_optical_exif:
            details.append("Optical exposure data")
        if has_gps:
            details.append("GPS geotag")
        return "VERIFIED_PHOTO", 0.99, "Verified camera hardware EXIF: " + ", ".join(details)

    # 4. Screenshot Detection (Filename pattern takes highest priority for screen grabs)
    is_screenshot_name = bool(SCREENSHOT_PATTERN.search(file_name))
    is_screen_res = (width, height) in COMMON_SCREEN_RESOLUTIONS if (width and height) else False

    if is_screenshot_name:
        return "SCREENSHOT", 0.95, f"Filename matches screenshot convention ({file_name})"

    if is_screen_res and ext == ".png" and not camera_make:
        return "SCREENSHOT", 0.90, f"Exact display resolution ({width}x{height}) in PNG format without camera EXIF"

    # 5. Asset filename patterns
    if ASSET_PATTERN.search(file_name):
        return "SYSTEM_ASSET", 0.85, f"Filename matches system/UI asset naming convention ({file_name})"

    # 6. Small computer graphics / icons
    if width and height:
        if width < 400 or height < 400:
            return "SYSTEM_ASSET", 0.92, f"Small dimensions ({width}x{height} px) typical of computer icons or UI assets"
        if file_size < 50 * 1024 and ext == ".png":
            return "SYSTEM_ASSET", 0.88, "Low file size PNG asset without EXIF"

    # 7. Real photo fallback (EXIF may have been stripped by messaging apps like WhatsApp/Signal/Telegram)
    if width and height and width >= 800 and height >= 600:
        aspect = width / max(height, 1)
        # Typical photo aspect ratios (3:2 = 1.5, 4:3 = 1.33, 16:9 = 1.77, or portrait equivalents)
        is_photo_aspect = (0.5 <= aspect <= 2.2)
        if ext in {".jpg", ".jpeg", ".heic", ".heif", ".cr2", ".nef", ".arw", ".dng"}:
            if is_photo_aspect:
                return "LIKELY_PHOTO", 0.75, "High-resolution photographic format and aspect ratio (EXIF stripped or edited)"
            else:
                return "LIKELY_PHOTO", 0.65, "Photographic format with custom crop"
        elif ext == ".png":
            if file_size > 1.5 * 1024 * 1024 and is_photo_aspect:
                return "LIKELY_PHOTO", 0.70, "Large PNG photographic export"
            else:
                return "SCREENSHOT", 0.60, "PNG image without camera EXIF metadata"

    return "LIKELY_PHOTO", 0.50, "Unclassified image treated as candidate photo"
