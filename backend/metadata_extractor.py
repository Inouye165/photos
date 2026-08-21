"""
Non-destructive Metadata & Hash Extractor for LuminaPhoto.
Extracts complete EXIF, GPS, camera hardware tags, SHA-256, and perceptual hashes (pHash/dHash).
Leaves original files completely untouched.
"""

import os
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from PIL import Image, ExifTags
import imagehash

# Register HEIF opener for Apple iOS photos if available
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

# Supported photo and video extensions
SUPPORTED_PHOTO_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tiff", ".tif",
    ".cr2", ".nef", ".arw", ".dng", ".rw2", ".orf", ".pef"
}
SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv"
}

def calculate_sha256(file_path: str, chunk_size: int = 65536) -> str:
    """Computes SHA-256 hash of file content for exact deduplication."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()

def calculate_perceptual_hashes(img: Image.Image) -> Tuple[Optional[str], Optional[str]]:
    """Calculates 64-bit pHash and dHash for near-duplicate and burst detection."""
    try:
        rgb_img = img.convert("RGB") if img.mode not in ("RGB", "L") else img
        ph = str(imagehash.phash(rgb_img))
        dh = str(imagehash.dhash(rgb_img))
        return ph, dh
    except Exception:
        return None, None

def _convert_to_degrees(value) -> Optional[float]:
    """Helper to convert GPS rational coordinates (degrees, minutes, seconds) to decimal float."""
    try:
        if isinstance(value, (tuple, list)) and len(value) >= 3:
            d = float(value[0])
            m = float(value[1])
            s = float(value[2])
            return d + (m / 60.0) + (s / 3600.0)
        return float(value)
    except Exception:
        return None

def extract_gps_info(exif_data: Dict[int, Any]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Extracts decimal latitude, longitude, and altitude from EXIF GPSInfo tag (34853)."""
    gps_info = exif_data.get(34853)
    if not gps_info or not isinstance(gps_info, dict):
        return None, None, None

    lat = None
    lon = None
    alt = None

    # GPS Tag IDs: 1: LatRef, 2: Lat, 3: LonRef, 4: Lon, 5: AltRef, 6: Alt
    lat_val = gps_info.get(2)
    lat_ref = gps_info.get(1)
    lon_val = gps_info.get(4)
    lon_ref = gps_info.get(3)
    alt_val = gps_info.get(6)

    if lat_val:
        lat = _convert_to_degrees(lat_val)
        if lat is not None and lat_ref and str(lat_ref).upper().startswith("S"):
            lat = -lat

    if lon_val:
        lon = _convert_to_degrees(lon_val)
        if lon is not None and lon_ref and str(lon_ref).upper().startswith("W"):
            lon = -lon

    if alt_val:
        try:
            alt = float(alt_val)
        except Exception:
            alt = None

    return lat, lon, alt

def parse_exif_date(date_str: Optional[str]) -> Optional[str]:
    """Parses standard EXIF date format 'YYYY:MM:DD HH:MM:SS' into ISO 8601 'YYYY-MM-DDTHH:MM:SS'."""
    if not date_str or not isinstance(date_str, str):
        return None
    date_str = date_str.strip().replace("\x00", "")
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y:%m:%d"):
        try:
            dt = datetime.strptime(date_str[:19], fmt)
            return dt.isoformat()
        except Exception:
            continue
    return None

def extract_metadata(file_path: str) -> Dict[str, Any]:
    """
    Extracts all metadata, dimensions, hashes, and EXIF tags from a media file.
    Non-destructive: original file is only opened for reading.
    """
    stat = os.stat(file_path)
    file_size = stat.st_size
    file_name = os.path.basename(file_path)
    _, ext = os.path.splitext(file_name)
    ext_lower = ext.lower()

    result: Dict[str, Any] = {
        "file_path": os.path.abspath(file_path),
        "file_name": file_name,
        "file_size": file_size,
        "file_extension": ext_lower,
        "file_created_at": stat.st_ctime,
        "file_modified_at": stat.st_mtime,
        "sha256": calculate_sha256(file_path),
        "width": None,
        "height": None,
        "aspect_ratio": None,
        "color_mode": None,
        "format": None,
        "phash": None,
        "dhash": None,
        "date_taken": None,
        "camera_make": None,
        "camera_model": None,
        "lens_model": None,
        "focal_length": None,
        "f_number": None,
        "exposure_time": None,
        "iso": None,
        "flash": None,
        "orientation": 1,
        "software": None,
        "latitude": None,
        "longitude": None,
        "altitude": None,
        "raw_exif_json": None
    }

    if ext_lower in SUPPORTED_VIDEO_EXTENSIONS:
        result["format"] = "VIDEO"
        result["date_taken"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
        return result

    try:
        with Image.open(file_path) as img:
            width, height = img.size
            result["width"] = width
            result["height"] = height
            result["aspect_ratio"] = round(width / max(height, 1), 4)
            result["color_mode"] = img.mode
            result["format"] = img.format or ext_lower.replace(".", "").upper()

            # Calculate perceptual hashes
            ph, dh = calculate_perceptual_hashes(img)
            result["phash"] = ph
            result["dhash"] = dh

            # Extract EXIF dictionary
            raw_exif_dict = {}
            exif = img._getexif() if hasattr(img, "_getexif") and callable(img._getexif) else None

            if exif and isinstance(exif, dict):
                for tag_id, value in exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    # Sanitize non-serializable binary values
                    if isinstance(value, bytes):
                        try:
                            value_str = value.decode("utf-8", errors="ignore").strip().replace("\x00", "")
                        except Exception:
                            value_str = f"<bytes {len(value)}>"
                    else:
                        value_str = str(value).strip().replace("\x00", "")
                    
                    raw_exif_dict[tag_name] = value_str

                    # Map standard EXIF fields
                    if tag_name in ("Make", "make"):
                        result["camera_make"] = value_str
                    elif tag_name in ("Model", "model"):
                        result["camera_model"] = value_str
                    elif tag_name in ("LensModel", "LensInfo", "Lens"):
                        result["lens_model"] = value_str
                    elif tag_name in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
                        if not result["date_taken"]:
                            result["date_taken"] = parse_exif_date(value_str)
                    elif tag_name == "FocalLength":
                        try:
                            result["focal_length"] = round(float(value), 2)
                        except Exception:
                            pass
                    elif tag_name == "FNumber":
                        try:
                            result["f_number"] = round(float(value), 2)
                        except Exception:
                            pass
                    elif tag_name == "ExposureTime":
                        result["exposure_time"] = str(value_str)
                    elif tag_name in ("ISOSpeedRatings", "PhotographicSensitivity", "ISO"):
                        try:
                            result["iso"] = int(value)
                        except Exception:
                            pass
                    elif tag_name == "Flash":
                        result["flash"] = str(value_str)
                    elif tag_name == "Orientation":
                        try:
                            result["orientation"] = int(value)
                        except Exception:
                            pass
                    elif tag_name in ("Software", "software"):
                        result["software"] = value_str

                # Extract GPS
                lat, lon, alt = extract_gps_info(exif)
                result["latitude"] = lat
                result["longitude"] = lon
                result["altitude"] = alt

                result["raw_exif_json"] = json.dumps(raw_exif_dict)

    except Exception as e:
        # If Pillow fails on special RAW or unhandled format, preserve basic file info
        pass

    # Fallback for date_taken if not in EXIF
    if not result["date_taken"]:
        result["date_taken"] = datetime.fromtimestamp(stat.st_mtime).isoformat()

    return result
