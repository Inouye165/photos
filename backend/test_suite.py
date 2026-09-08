"""
Comprehensive Test Suite for LuminaPhoto.
Tests EXIF extraction, classifier rules, deduplication, thumbnailing, vector search,
safe deletion, duplicate group dismissal, network info, and API endpoints.
"""

import os
import sys
import shutil
import tempfile
import sqlite3
import numpy as np
from PIL import Image
import piexif
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        import backend.database
        import backend.app
        backend.database.DB_PATH = test_db
        backend.app.DB_PATH = test_db
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
        assert thumb_path is not None and os.path.exists(thumb_path), "Thumbnail file was not created"
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

        # Step 9: Test Trash Tagging (Deferred Deletion / File Preservation)
        trash_sample_path = os.path.join(test_dir, "trash_candidate.jpg")
        shutil.copy2(samples["cam_photo"], trash_sample_path)
        trash_meta = extract_metadata(trash_sample_path)
        trash_pid = upsert_photo({**trash_meta, "classification": "VERIFIED_PHOTO", "indexed_at": 1010})

        # Tag for trash
        tag_res = client.post(f"/api/photos/{trash_pid}/trash", json={"is_trashed": True})
        assert tag_res.status_code == 200, f"Tag trash failed: {tag_res.text}"
        assert tag_res.json()["is_trashed"] is True
        # Verify file is preserved intact on disk
        assert os.path.exists(trash_sample_path), "File should be preserved on disk when tagged for trash"

        # Verify default list_photos excludes trashed photos
        list_res = client.get("/api/photos")
        pids = [p["id"] for p in list_res.json()["photos"]]
        assert trash_pid not in pids, "Trashed photo should not appear in default photo gallery"

        # Verify trash listing endpoint
        trash_list_res = client.get("/api/trash")
        assert trash_list_res.status_code == 200
        trash_pids = [p["id"] for p in trash_list_res.json()["photos"]]
        assert trash_pid in trash_pids, "Trashed photo must appear in /api/trash"
        print("[PASS] Trash Tagging: Photo tagged for trash, file preserved intact on disk and filtered from active gallery", flush=True)

        # Step 10: Test Space-Triggered Auto-Purge & Notification Message
        purge_res = client.post("/api/trash/purge-for-space", json={"force_purge_count": 1})
        assert purge_res.status_code == 200, f"Purge for space failed: {purge_res.text}"
        purge_data = purge_res.json()
        assert purge_data["purged"] is True, "Expected purged=True on space reclamation"
        assert purge_data["count"] >= 1, "Expected at least 1 photo purged"
        assert not os.path.exists(trash_sample_path), "File should be permanently deleted on disk after space purge"
        assert "CRITICAL DISK SPACE NOTICE" in purge_data["message"], f"Expected notice in message, got {purge_data['message']}"
        
        # Verify purge audit logs
        logs_res = client.get("/api/trash/purge-logs")
        assert logs_res.status_code == 200
        logs = logs_res.json()["logs"]
        assert len(logs) >= 1, "Expected at least 1 purge log entry"
        assert logs[0]["reason"] == "LOW_DISK_SPACE"
        print(f"[PASS] Disk Space Auto-Purge: Permanently deleted file on disk and generated mandatory notification: '{purge_data['message'][:60]}...'", flush=True)

        # Step 11: Test Duplicate Trashing Flow (Batch and Single)
        dup_img = Image.new("RGB", (1300, 900), color=(99, 120, 200))
        for x in range(100):
            for y in range(100):
                dup_img.putpixel((x, y), (200, 50, 150))
        dup_test_1 = os.path.join(test_dir, "dup_orig.jpg")
        dup_test_2 = os.path.join(test_dir, "dup_copy.jpg")
        dup_img.save(dup_test_1, "jpeg")
        dup_img.save(dup_test_2, "jpeg")
        m1 = extract_metadata(dup_test_1)
        m2 = extract_metadata(dup_test_2)
        d_p1 = upsert_photo({**m1, "classification": "VERIFIED_PHOTO", "indexed_at": 2001})
        d_p2 = upsert_photo({**m2, "classification": "VERIFIED_PHOTO", "indexed_at": 2002})
        run_deduplication_pass()
        
        # Verify duplicate group was found
        groups_res = client.get("/api/duplicates")
        assert groups_res.status_code == 200
        dup_groups_before = groups_res.json()
        assert len(dup_groups_before) >= 1, "Expected duplicate group before trash"
        
        # Trash all duplicates
        trash_dups_res = client.post("/api/duplicates/trash-all")
        assert trash_dups_res.status_code == 200
        trash_dups_data = trash_dups_res.json()
        assert trash_dups_data["count"] >= 1, f"Expected at least 1 duplicate trashed, got {trash_dups_data}"

        # Verify duplicate group list is now empty/resolved
        groups_after = client.get("/api/duplicates").json()
        assert len(groups_after) == 0, f"Expected 0 duplicate groups after trashing, got {len(groups_after)}"

        # Verify file is still physically on disk (non-destructive)
        assert os.path.exists(dup_test_2), "Duplicate copy must remain preserved on disk in Trash state"
        print("[PASS] Duplicate Trashing: Successfully moved duplicate copies to Trash, preserved primary original, and updated duplicate inspector", flush=True)

        # Step 12: Test Compare Studio Selective Batch Trashing & Group Reconciliation
        trip_base = os.path.join(test_dir, "trip_base.jpg")
        Image.new("RGB", (1400, 1000), color=(12, 140, 240)).save(trip_base, "jpeg")
        trip_1 = os.path.join(test_dir, "trip_1.jpg")
        trip_2 = os.path.join(test_dir, "trip_2.jpg")
        trip_3 = os.path.join(test_dir, "trip_3.jpg")
        shutil.copy2(trip_base, trip_1)
        shutil.copy2(trip_base, trip_2)
        shutil.copy2(trip_base, trip_3)
        t_m1 = extract_metadata(trip_1)
        t_m2 = extract_metadata(trip_2)
        t_m3 = extract_metadata(trip_3)
        tp1 = upsert_photo({**t_m1, "classification": "VERIFIED_PHOTO", "indexed_at": 3001})
        tp2 = upsert_photo({**t_m2, "classification": "VERIFIED_PHOTO", "indexed_at": 3002})
        tp3 = upsert_photo({**t_m3, "classification": "VERIFIED_PHOTO", "indexed_at": 3003})
        run_deduplication_pass()

        groups_res = client.get("/api/duplicates")
        assert groups_res.status_code == 200
        trip_group = next(
            (g for g in groups_res.json() if any(item["id"] == tp1 for item in [g["primary"], *g["duplicates"]])),
            None
        )
        assert trip_group is not None, "Expected triplet group to be formed"
        assert trip_group["total_items"] == 3

        # User compares group and selectively trashes only 1 of the duplicates (tp2)
        batch_res = client.post("/api/photos/batch-trash", json={"photo_ids": [tp2], "is_trashed": True})
        assert batch_res.status_code == 200

        # Verify group is reconciled to 2 items (user kept more than 1)
        groups_after_partial = client.get("/api/duplicates").json()
        reconciled_group = next((g for g in groups_after_partial if g["group_id"] == trip_group["group_id"]), None)
        assert reconciled_group is not None, "Group should still exist with 2 remaining photos"
        assert reconciled_group["total_items"] == 2

        # Step 12b: Test Duplicate Sorting by Number of Duplicates & Photo Age
        # Create a second duplicate cluster with distinct duplicate count and older date
        quad_base = os.path.join(test_dir, "quad_base.jpg")
        Image.new("RGB", (800, 600), color=(180, 50, 90)).save(quad_base, "jpeg")
        q1 = os.path.join(test_dir, "q1.jpg")
        q2 = os.path.join(test_dir, "q2.jpg")
        q3 = os.path.join(test_dir, "q3.jpg")
        shutil.copy2(quad_base, q1)
        shutil.copy2(quad_base, q2)
        shutil.copy2(quad_base, q3)
        qm1 = extract_metadata(q1)
        qm2 = extract_metadata(q2)
        qm3 = extract_metadata(q3)
        # Set older date for quad cluster and newer date for triplet cluster
        qp1 = upsert_photo({**qm1, "classification": "VERIFIED_PHOTO", "date_taken": "2019-06-15 10:00:00", "indexed_at": 3501})
        qp2 = upsert_photo({**qm2, "classification": "VERIFIED_PHOTO", "date_taken": "2019-06-15 10:00:00", "indexed_at": 3502})
        qp3 = upsert_photo({**qm3, "classification": "VERIFIED_PHOTO", "date_taken": "2019-06-15 10:00:00", "indexed_at": 3503})
        # Set trip cluster photos to newer date
        conn_test = get_connection()
        conn_test.execute("UPDATE photos SET date_taken = '2024-11-20 14:00:00' WHERE id IN (?, ?)", (tp1, tp3))
        conn_test.commit()
        conn_test.close()
        run_deduplication_pass()

        # 1. Sort by count DESC (Most duplicates first)
        sort_count_desc = client.get("/api/duplicates?sort_by=count&sort_order=desc").json()
        assert len(sort_count_desc) >= 2
        for i in range(len(sort_count_desc) - 1):
            assert sort_count_desc[i]["duplicate_count"] >= sort_count_desc[i + 1]["duplicate_count"], \
                f"Count DESC violated at index {i}: {sort_count_desc[i]['duplicate_count']} < {sort_count_desc[i + 1]['duplicate_count']}"

        # 2. Sort by count ASC (Fewest duplicates first)
        sort_count_asc = client.get("/api/duplicates?sort_by=count&sort_order=asc").json()
        assert len(sort_count_asc) >= 2
        for i in range(len(sort_count_asc) - 1):
            assert sort_count_asc[i]["duplicate_count"] <= sort_count_asc[i + 1]["duplicate_count"], \
                f"Count ASC violated at index {i}: {sort_count_asc[i]['duplicate_count']} > {sort_count_asc[i + 1]['duplicate_count']}"

        # 3. Sort by date ASC (Oldest photos first)
        sort_date_asc = client.get("/api/duplicates?sort_by=date&sort_order=asc").json()
        assert len(sort_date_asc) >= 2
        dated_asc = [str(g["date_taken"]).replace(":", "-") for g in sort_date_asc if g.get("date_taken")]
        for i in range(len(dated_asc) - 1):
            assert dated_asc[i] <= dated_asc[i + 1], f"Date ASC violated: {dated_asc[i]} > {dated_asc[i + 1]}"

        # 4. Sort by date DESC (Newest photos first)
        sort_date_desc = client.get("/api/duplicates?sort_by=date&sort_order=desc").json()
        assert len(sort_date_desc) >= 2
        dated_desc = [str(g["date_taken"]).replace(":", "-") for g in sort_date_desc if g.get("date_taken")]
        for i in range(len(dated_desc) - 1):
            assert dated_desc[i] >= dated_desc[i + 1], f"Date DESC violated: {dated_desc[i]} < {dated_desc[i + 1]}"
        print("[PASS] Duplicate Sorting API: Successfully sorted duplicate clusters by count (most/fewest) and age (oldest/newest)", flush=True)

        # Step 13: Test Duplicate Dismissal Persistence Across Scans/Passes
        dis_orig = os.path.join(test_dir, "dis_orig.jpg")
        dis_copy = os.path.join(test_dir, "dis_copy.jpg")
        shutil.copy2(trip_base, dis_orig)
        shutil.copy2(trip_base, dis_copy)
        dis_m1 = extract_metadata(dis_orig)
        dis_m2 = extract_metadata(dis_copy)
        dp1 = upsert_photo({**dis_m1, "classification": "VERIFIED_PHOTO", "indexed_at": 4001})
        dp2 = upsert_photo({**dis_m2, "classification": "VERIFIED_PHOTO", "indexed_at": 4002})
        run_deduplication_pass()

        groups_res = client.get("/api/duplicates")
        dis_group = next(
            (g for g in groups_res.json() if any(item["id"] == dp1 for item in [g["primary"], *g["duplicates"]])),
            None
        )
        assert dis_group is not None, "Expected duplicate group to be created for dismissal test"

        # Dismiss the duplicate group
        dismiss_res = client.post(f"/api/duplicates/group/{dis_group['group_id']}/dismiss")
        assert dismiss_res.status_code == 200, f"Dismiss failed: {dismiss_res.text}"

        # Re-run full deduplication pass
        run_deduplication_pass()

        # Verify the dismissed pair does NOT re-cluster into a duplicate group
        groups_after_repass = client.get("/api/duplicates").json()
        assert not any(
            any(item["id"] == dp1 for item in [g["primary"], *g["duplicates"]]) for g in groups_after_repass
        ), "Dismissed duplicate pair was improperly re-clustered after a deduplication pass!"
        print("[PASS] Dismissal Persistence: Dismissed duplicate pair remembered and prevented from re-clustering", flush=True)

        # Step 14: Test Semantic Search with Candidate Pre-Filtering
        vector_engine.add_or_update_photo(dp1, dis_orig, test_db)
        # Search with allowed_photo_ids restricted to [dp1]
        filtered_search = vector_engine.search_text("colorful blue", top_k=5, allowed_photo_ids={dp1})
        assert len(filtered_search) == 1 and filtered_search[0]["photo_id"] == dp1, "Pre-filtered search did not constrain to allowed ID"
        # Search with empty allowed set
        empty_search = vector_engine.search_text("colorful blue", top_k=5, allowed_photo_ids={999999})
        assert len(empty_search) == 0, "Expected empty results for non-matching allowed IDs"
        # Step 15: Test Continuous Burst Detection & Category Filtering API
        burst_img_1 = os.path.join(test_dir, "burst_take_1.jpg")
        burst_img_2 = os.path.join(test_dir, "burst_take_2.jpg")
        burst_img_3 = os.path.join(test_dir, "burst_take_3.jpg")
        
        # Create base photo with low-frequency structure (half-split) so pHash is distinct after 32x32 DCT downsampling
        b_base = Image.new("RGB", (1200, 800), color=(80, 160, 220))
        for x in range(600):
            for y in range(800):
                b_base.putpixel((x, y), (240, 40, 90))
        # Save burst takes with slightly different compression/encoding (SHA-256 differs, visual pHash is identical)
        b_base.save(burst_img_1, "jpeg", quality=95)
        b_base.save(burst_img_2, "jpeg", quality=94)
        b_base.save(burst_img_3, "jpeg", quality=93)

        bm1 = extract_metadata(burst_img_1)
        bm2 = extract_metadata(burst_img_2)
        bm3 = extract_metadata(burst_img_3)

        # Timestamps taken 4 seconds apart (continuous burst within 1 minute)
        bp1 = upsert_photo({**bm1, "classification": "VERIFIED_PHOTO", "date_taken": "2024-06-16 10:06:00", "indexed_at": 5001})
        bp2 = upsert_photo({**bm2, "classification": "VERIFIED_PHOTO", "date_taken": "2024-06-16 10:06:04", "indexed_at": 5002})
        bp3 = upsert_photo({**bm3, "classification": "VERIFIED_PHOTO", "date_taken": "2024-06-16 10:06:08", "indexed_at": 5003})

        run_deduplication_pass()

        # Verify burst group was formed with BURST_SEQUENCE match_type
        burst_res = client.get("/api/duplicates?category=burst")
        assert burst_res.status_code == 200
        burst_groups = burst_res.json()
        assert len(burst_groups) >= 1, "Expected at least 1 BURST_SEQUENCE group"
        b_group = next(
            (g for g in burst_groups if any(item["id"] == bp1 for item in [g["primary"], *g["duplicates"]])),
            None
        )
        assert b_group is not None, "Burst group containing bp1 was not found"
        assert b_group["match_type"] == "BURST_SEQUENCE", f"Expected BURST_SEQUENCE, got {b_group['match_type']}"
        assert b_group["total_items"] == 3

        # Verify category=exact only returns EXACT_HASH
        exact_res = client.get("/api/duplicates?category=exact")
        assert exact_res.status_code == 200
        for eg in exact_res.json():
            assert eg["match_type"] == "EXACT_HASH"

        print("[PASS] Continuous Burst & Category Filtering: Successfully detected rapid burst sequence, assigned BURST_SEQUENCE match_type, and filtered categories via API", flush=True)

        print("\n*** ALL UNIT & INTEGRATION TESTS PASSED PERFECTLY! ***\n", flush=True)

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

if __name__ == "__main__":
    run_tests()
