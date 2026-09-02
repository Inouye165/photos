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

def _convert_to_degrees(value: Any) -> Optional[float]:
    """Helper to convert GPS rational coordinates (degrees, minutes, seconds) to decimal float."""
    try:
        if isinstance(value, (tuple, list)):
            if len(value) >= 3:
                d = float(value[0])
                m = float(value[1])
                s = float(value[2])
                return d + (m / 60.0) + (s / 3600.0)
            elif len(value) == 1:
                return float(value[0])
            return None
        return float(value)
    except Exception:
        return None

def extract_gps_info(gps_data: Dict[Any, Any]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Extracts decimal latitude, longitude, and altitude from GPS IFD or EXIF dictionary."""
    if not gps_data or not isinstance(gps_data, dict):
        return None, None, None

    # If caller passed full EXIF dict containing GPS tag (34853)
    if 34853 in gps_data and isinstance(gps_data[34853], dict):
        gps_info = gps_data[34853]
    else:
        gps_info = gps_data

    lat = None
    lon = None
    alt = None

    # GPS Tag IDs: 1: LatRef, 2: Lat, 3: LonRef, 4: Lon, 5: AltRef, 6: Alt
    lat_val = gps_info.get(2) or gps_info.get("GPSLatitude")
    lat_ref = gps_info.get(1) or gps_info.get("GPSLatitudeRef")
    lon_val = gps_info.get(4) or gps_info.get("GPSLongitude")
    lon_ref = gps_info.get(3) or gps_info.get("GPSLongitudeRef")
    alt_val = gps_info.get(6) or gps_info.get("GPSAltitude")
    alt_ref = gps_info.get(5) or gps_info.get("GPSAltitudeRef")

    if lat_val is not None:
        lat = _convert_to_degrees(lat_val)
        if lat is not None and lat_ref:
            ref_str = lat_ref.decode("utf-8", errors="ignore") if isinstance(lat_ref, bytes) else str(lat_ref)
            if ref_str.upper().startswith("S"):
                lat = -abs(lat)

    if lon_val is not None:
        lon = _convert_to_degrees(lon_val)
        if lon is not None and lon_ref:
            ref_str = lon_ref.decode("utf-8", errors="ignore") if isinstance(lon_ref, bytes) else str(lon_ref)
            if ref_str.upper().startswith("W"):
                lon = -abs(lon)

    if alt_val is not None:
        try:
            alt = float(alt_val)
            if alt_ref and (alt_ref == 1 or alt_ref == b'\x01' or str(alt_ref) == "1"):
                alt = -abs(alt)
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
        "file_created_at": getattr(stat, "st_birthtime", stat.st_mtime),
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

            # Extract EXIF tags across both modern Pillow (getexif / IFDs) and legacy (_getexif)
            raw_exif_dict = {}
            combined_tags: Dict[str, Any] = {}
            gps_ifd: Dict[Any, Any] = {}

            exif_obj = None
            if hasattr(img, "getexif"):
                try:
                    exif_obj = img.getexif()
                except Exception:
                    exif_obj = None

            if exif_obj:
                for tag_id, value in exif_obj.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    combined_tags[tag_name] = value

                # Exif sub-IFD (tag 34665)
                if hasattr(ExifTags, "IFD") and hasattr(ExifTags.IFD, "Exif"):
                    try:
                        exif_sub = exif_obj.get_ifd(ExifTags.IFD.Exif)
                        for tag_id, value in exif_sub.items():
                            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                            combined_tags[tag_name] = value
                    except Exception:
                        pass
                elif hasattr(exif_obj, "get_ifd"):
                    try:
                        exif_sub = exif_obj.get_ifd(34665)
                        for tag_id, value in exif_sub.items():
                            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                            combined_tags[tag_name] = value
                    except Exception:
                        pass

                # GPS sub-IFD (tag 34853)
                if hasattr(ExifTags, "IFD") and hasattr(ExifTags.IFD, "GPSInfo"):
                    try:
                        gps_ifd = dict(exif_obj.get_ifd(ExifTags.IFD.GPSInfo))
                    except Exception:
                        pass
                elif hasattr(exif_obj, "get_ifd"):
                    try:
                        gps_ifd = dict(exif_obj.get_ifd(34853))
                    except Exception:
                        pass

            # Legacy _getexif fallback if needed
            if not combined_tags and hasattr(img, "_getexif"):
                legacy_exif = getattr(img, "_getexif", lambda: None)()
                if legacy_exif and isinstance(legacy_exif, dict):
                    for tag_id, value in legacy_exif.items():
                        tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                        combined_tags[tag_name] = value
                        if tag_id == 34853 and isinstance(value, dict):
                            gps_ifd = value

            # Fallback for GPS if embedded in combined_tags
            if not gps_ifd:
                if isinstance(combined_tags.get("34853"), dict):
                    gps_ifd = combined_tags["34853"]
                elif isinstance(combined_tags.get("GPSInfo"), dict):
                    gps_ifd = combined_tags["GPSInfo"]

            for tag_name, value in combined_tags.items():
                if isinstance(value, bytes):
                    try:
                        value_str = value.decode("utf-8", errors="ignore").strip().replace("\x00", "")
                    except Exception:
                        value_str = f"<bytes {len(value)}>"
                else:
                    value_str = str(value).strip().replace("\x00", "")

                raw_exif_dict[tag_name] = value_str

                if tag_name in ("Make", "make") and not result["camera_make"]:
                    result["camera_make"] = value_str
                elif tag_name in ("Model", "model") and not result["camera_model"]:
                    result["camera_model"] = value_str
                elif tag_name in ("LensModel", "LensInfo", "Lens") and not result["lens_model"]:
                    result["lens_model"] = value_str
                elif tag_name in ("DateTimeOriginal", "DateTimeDigitized", "DateTime") and not result["date_taken"]:
                    result["date_taken"] = parse_exif_date(value_str)
                elif tag_name == "FocalLength" and result["focal_length"] is None:
                    try:
                        result["focal_length"] = round(float(value), 2)
                    except Exception:
                        pass
                elif tag_name == "FNumber" and result["f_number"] is None:
                    try:
                        result["f_number"] = round(float(value), 2)
                    except Exception:
                        pass
                elif tag_name == "ExposureTime" and not result["exposure_time"]:
                    result["exposure_time"] = value_str
                elif tag_name in ("ISOSpeedRatings", "PhotographicSensitivity", "ISO") and result["iso"] is None:
                    try:
                        result["iso"] = int(value)
                    except Exception:
                        pass
                elif tag_name == "Flash" and not result["flash"]:
                    result["flash"] = value_str
                elif tag_name == "Orientation" and result["orientation"] == 1:
                    try:
                        result["orientation"] = int(value)
                    except Exception:
                        pass
                elif tag_name in ("Software", "software") and not result["software"]:
                    result["software"] = value_str

            # Extract GPS
            lat, lon, alt = extract_gps_info(gps_ifd)
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
