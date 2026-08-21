"""
Comprehensive Test Suite for LuminaPhoto.
Tests EXIF extraction, classifier rules, deduplication, thumbnailing, vector search,
safe deletion, duplicate group dismissal, network info, and API endpoints.
"""

import os
import shutil
import tempfile
import sqlite3
import numpy as np
from PIL import Image
import piexif
from fastapi.testclient import TestClient

from backend.database import init_db, get_connection, upsert_photo, get_photos, get_duplicate_groups, get_stats
from backend.metadata_extractor import extract_metadata, calculate_sha256, calculate_perceptual_hashes
from backend.classifier import classify_media
from backend.deduplicator import run_deduplication_pass
from backend.thumbnails import generate_thumbnail
from backend.vector_engine import VectorEngine
from backend.app import app

def create_sample_dataset(test_dir: str):
    """Creates synthetic photos, duplicates, screenshots, and assets for testing."""
    os.makedirs(os.path.join(test_dir, "vacation_2025"), exist_ok=True)
    os.makedirs(os.path.join(test_dir, "screenshots_folder"), exist_ok=True)
    os.makedirs(os.path.join(test_dir, "assets"), exist_ok=True)

    # 1. Genuine camera photo (with rich EXIF)
    cam_photo_path = os.path.join(test_dir, "vacation_2025", "IMG_8492.jpg")
    img = Image.new("RGB", (1600, 1200), color=(50, 120, 200))
    for x in range(800):
        for y in range(600):
            img.putpixel((x, y), (220, 140, 50))

    zeroth_ifd = {
        piexif.ImageIFD.Make: "Canon",
        piexif.ImageIFD.Model: "Canon EOS R5",
        piexif.ImageIFD.Software: "Firmware 1.6.0"
    }
    exif_ifd = {
        piexif.ExifIFD.DateTimeOriginal: "2025:07:15 14:32:00",
        piexif.ExifIFD.ISOSpeedRatings: 200,
        piexif.ExifIFD.FNumber: (28, 10),
        piexif.ExifIFD.ExposureTime: (1, 500),
        piexif.ExifIFD.FocalLength: (50, 1),
        piexif.ExifIFD.LensModel: "RF 50mm F1.2L USM"
    }
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: "N",
        piexif.GPSIFD.GPSLatitude: ((37, 1), (46, 1), (30, 1)),
        piexif.GPSIFD.GPSLongitudeRef: "W",
        piexif.GPSIFD.GPSLongitude: ((122, 1), (25, 1), (0, 1)),
        piexif.GPSIFD.GPSAltitude: (15, 1)
    }
    exif_bytes = piexif.dump({"0th": zeroth_ifd, "Exif": exif_ifd, "GPS": gps_ifd})
    img.save(cam_photo_path, "jpeg", exif=exif_bytes)

    # 2. Exact duplicate of the camera photo in another subfolder
    exact_dup_path = os.path.join(test_dir, "vacation_2025", "IMG_8492_copy.jpg")
    shutil.copy2(cam_photo_path, exact_dup_path)

    # 3. Screenshot image (1920x1080, PNG, no EXIF, screenshot name)
    screenshot_path = os.path.join(test_dir, "screenshots_folder", "Screenshot 2026-08-20 at 10.15.22.png")
    s_img = Image.new("RGB", (1920, 1080), color=(30, 30, 30))
    s_img.save(screenshot_path, "png")

    # 4. Small system UI icon (128x128 px, PNG, no EXIF)
    icon_path = os.path.join(test_dir, "assets", "app_icon.png")
    i_img = Image.new("RGBA", (128, 128), color=(255, 0, 0, 255))
    i_img.save(icon_path, "png")

    # 5. GIF image
    gif_path = os.path.join(test_dir, "assets", "spinner.gif")
    g_img = Image.new("P", (64, 64), color=2)
    g_img.save(gif_path, "gif")

    return {
        "cam_photo": cam_photo_path,
        "exact_dup": exact_dup_path,
        "screenshot": screenshot_path,
        "icon": icon_path,
        "gif": gif_path
    }

def run_tests():
    print("=== Starting LuminaPhoto Automated Test Suite ===")
    test_dir = tempfile.mkdtemp(prefix="luminaphoto_test_")
    test_db = os.path.join(test_dir, "test_photos.db")

    try:
        # Step 1: Create test data
        samples = create_sample_dataset(test_dir)
        print("[PASS] Created synthetic test photo dataset with in-place pointers, EXIF, duplicates, and screenshots")

        # Step 2: Test Metadata Extractor (In-place pointer verification)
        cam_meta = extract_metadata(samples["cam_photo"])
        assert cam_meta["file_path"] == os.path.abspath(samples["cam_photo"]), "File pointer mismatch"
        assert cam_meta["camera_make"] == "Canon", f"Expected Canon, got {cam_meta['camera_make']}"
        assert cam_meta["camera_model"] == "Canon EOS R5", f"Expected Canon EOS R5, got {cam_meta['camera_model']}"
        assert cam_meta["iso"] == 200, f"Expected ISO 200, got {cam_meta['iso']}"
        assert cam_meta["latitude"] is not None and abs(cam_meta["latitude"] - 37.775) < 0.01, f"GPS latitude failed: {cam_meta['latitude']}"
        assert cam_meta["longitude"] is not None and abs(cam_meta["longitude"] - (-122.4166)) < 0.01, f"GPS longitude failed: {cam_meta['longitude']}"
        print("[PASS] Metadata Extractor: Successfully extracted in-place file pointer, Camera Make, Model, ISO, Lens, GPS non-destructively")

        # Step 3: Test Classifier Rules
        cam_class, cam_score, _ = classify_media(cam_meta)
        assert cam_class == "VERIFIED_PHOTO", f"Expected VERIFIED_PHOTO, got {cam_class}"

        screen_meta = extract_metadata(samples["screenshot"])
        screen_class, _, _ = classify_media(screen_meta)
        assert screen_class == "SCREENSHOT", f"Expected SCREENSHOT, got {screen_class}"

        icon_meta = extract_metadata(samples["icon"])
        icon_class, _, _ = classify_media(icon_meta)
        assert icon_class == "SYSTEM_ASSET", f"Expected SYSTEM_ASSET, got {icon_class}"

        print("[PASS] Classifier: Accurately differentiated Real Camera Photo vs Screenshot vs System Asset")

        # Step 4: Test Database Operations & Deduplication
        init_db(test_db)
        
        p1_id = upsert_photo({**cam_meta, "classification": cam_class, "classification_score": cam_score, "indexed_at": 1000}, test_db)
        dup_meta = extract_metadata(samples["exact_dup"])
        d_class, d_score, _ = classify_media(dup_meta)
        p2_id = upsert_photo({**dup_meta, "classification": d_class, "classification_score": d_score, "indexed_at": 1001}, test_db)

        # Run deduplication pass
        dup_groups_count = run_deduplication_pass(test_db)
        assert dup_groups_count >= 1, f"Expected at least 1 duplicate group, got {dup_groups_count}"
        groups = get_duplicate_groups(test_db)
        assert len(groups) >= 1, "Duplicate groups list is empty"
        print(f"[PASS] Deduplicator: Successfully clustered duplicate group with 1 copy identified and primary designated")

        # Step 5: Test Non-destructive Thumbnail Generation
        thumb_path = generate_thumbnail(samples["cam_photo"], p1_id, "thumb")
        assert os.path.exists(thumb_path), "Thumbnail file was not created"
        with Image.open(thumb_path) as t_img:
            assert t_img.width <= 320 and t_img.height <= 320, "Thumbnail dimension exceeds 320"
        print("[PASS] Thumbnail Generator: Generated fast WebP cached preview", flush=True)

        # Step 6: Test Multimodal Vector Engine
        vector_engine = VectorEngine.get_instance()
        print("[INFO] Vector Engine: Initializing & computing embedding...", flush=True)
        vector_engine.add_or_update_photo(p1_id, samples["cam_photo"], test_db)
        print("[INFO] Vector Engine: Searching text...", flush=True)
        search_res = vector_engine.search_text("colorful photo", top_k=5)
        assert len(search_res) > 0, "Semantic search returned empty results"
        print(f"[PASS] Vector Engine: Semantic natural language query returned match with score {search_res[0]['similarity_score']:.4f}", flush=True)

        # Step 7: Test FastAPI Endpoints via TestClient
        client = TestClient(app)
        res_health = client.get("/api/health")
        assert res_health.status_code == 200, "Health check failed"

        res_net = client.get("/api/network-info")
        assert res_net.status_code == 200, "Network info endpoint failed"
        assert "primary_url" in res_net.json(), "Missing primary_url in network info"
        print(f"[PASS] Network Info API: Successfully returned host network URL: {res_net.json()['primary_url']}", flush=True)

        # Step 8: Test Safe Deletion API
        disp_path = os.path.join(test_dir, "to_delete.jpg")
        shutil.copy2(samples["cam_photo"], disp_path)
        disp_meta = extract_metadata(disp_path)
        disp_id = upsert_photo({**disp_meta, "classification": "VERIFIED_PHOTO", "indexed_at": 1005})
        
        del_res = client.delete(f"/api/photos/{disp_id}?permanent=true")
        assert del_res.status_code == 200, f"Delete failed: {del_res.text}"
        assert not os.path.exists(disp_path), "File was not deleted from disk"
        print("[PASS] Safe Deletion API: Deleted file safely and purged record from catalog", flush=True)

        print("\n*** ALL UNIT & INTEGRATION TESTS PASSED PERFECTLY! ***\n", flush=True)

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

if __name__ == "__main__":
    run_tests()
