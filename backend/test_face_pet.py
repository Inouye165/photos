"""
Comprehensive automated tests for People and Pets Detection, Visual Embeddings,
High-Confidence Auto-Tagging, and Confirmation Review Queue.
"""

import os
import sys
import json
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.database import (
    get_connection,
    init_db,
    get_or_create_entity,
    list_entities,
    get_entity_by_id,
    update_entity,
    delete_entity,
    insert_detected_box,
    get_boxes_for_photo,
    get_box_by_id,
    update_box_entity,
    confirm_box,
    reject_box,
    batch_confirm_boxes,
    get_pending_review_boxes,
    delete_box,
    get_confirmed_embeddings_for_entities,
    resolve_duplicate_photo_entity_assignments
)
from backend.face_pet_detector import (
    FacePetDetector,
    STRICT_HIGH_CONFIDENCE_THRESHOLD,
    CROPS_CACHE_DIR
)
from PIL import Image

client = TestClient(app)

def test_database_entity_and_boxes_crud():
    init_db()
    # 1. Create entity
    entity = get_or_create_entity("Test Person Alpha", "PERSON")
    assert entity["id"] is not None
    assert entity["name"] == "Test Person Alpha"
    assert entity["entity_type"] == "PERSON"
    eid = entity["id"]

    # 2. Get existing entity (case insensitive)
    dup = get_or_create_entity("test person alpha", "PERSON")
    assert dup["id"] == eid

    # 3. Update entity
    updated = update_entity(eid, name="Test Person Alpha Renamed", entity_type="PERSON")
    assert updated is True
    fetched = get_entity_by_id(eid)
    assert fetched["name"] == "Test Person Alpha Renamed"

    # 4. Insert detected box
    # Find any photo in DB or use dummy photo_id = 999999
    conn = get_connection()
    row = conn.execute("SELECT id, file_path FROM photos LIMIT 1").fetchone()
    conn.close()
    
    photo_id = row["id"] if row else 1

    box_data = {
        "photo_id": photo_id,
        "entity_id": eid,
        "box_type": "FACE",
        "label": "person",
        "confidence": 0.98,
        "x_min": 0.2,
        "y_min": 0.2,
        "x_max": 0.6,
        "y_max": 0.6,
        "embedding_json": json.dumps([0.1] * 512),
        "status": "PENDING_REVIEW",
        "match_confidence": 0.91
    }
    box_id = insert_detected_box(box_data)
    assert box_id is not None

    # 5. Fetch boxes for photo
    boxes = get_boxes_for_photo(photo_id)
    assert any(b["id"] == box_id for b in boxes)

    # 6. Verify pending reviews query
    pending_items, total_pending = get_pending_review_boxes(limit=10, entity_id=eid)
    assert total_pending >= 1
    assert any(b["id"] == box_id for b in pending_items)

    # 7. Confirm box
    confirm_res = confirm_box(box_id)
    assert confirm_res is True
    confirmed_box = get_box_by_id(box_id)
    assert confirmed_box["status"] == "CONFIRMED"

    # 8. Clean up
    delete_box(box_id)
    delete_entity(eid)
    print("Database entity and boxes CRUD test PASSED!")

def test_detector_embedding_and_matching():
    detector = FacePetDetector.get_instance()
    # Create test image
    img = Image.new("RGB", (300, 300), color=(180, 120, 80))
    box = {"x_min": 0.1, "y_min": 0.1, "x_max": 0.8, "y_max": 0.8, "box_type": "PET"}
    
    emb, crop = detector.extract_crop_embedding(img, box)
    assert len(emb) == 512
    assert crop.size[0] > 0 and crop.size[1] > 0

    # Matching with threshold >= 0.78
    entity_embeddings = {
        100: [emb], # Target match
        200: [[-x for x in emb]] # Inverted vector (opposite)
    }

    # Match exact same vector
    matched_id, score, status = detector.match_against_entities(emb, entity_embeddings, threshold=0.78)
    assert matched_id == 100
    assert score >= 0.99
    assert status == "PENDING_REVIEW"

    # Weak match test (< 0.78 threshold)
    weak_emb = [0.0] * 512
    weak_emb[0] = 1.0 # orthogonal vector
    matched_id_weak, score_weak, status_weak = detector.match_against_entities(weak_emb, {100: [emb]}, threshold=0.78)
    assert matched_id_weak is None
    assert status_weak == "UNASSIGNED"
    print("Detector embedding and matching test PASSED!")

def test_api_endpoints():
    # 1. Stats endpoint check
    stats_res = client.get("/api/stats")
    assert stats_res.status_code == 200
    stats_json = stats_res.json()
    assert "total_people" in stats_json
    assert "total_pets" in stats_json
    assert "total_pending_boxes" in stats_json

    # 2. Entity creation via API
    create_res = client.post("/api/people-pets/entities", json={"name": "End2End Buddy", "entity_type": "PET"})
    assert create_res.status_code == 200
    eid = create_res.json()["id"]

    # 3. List entities
    list_res = client.get("/api/people-pets/entities")
    assert list_res.status_code == 200
    entities = list_res.json()
    assert any(e["id"] == eid for e in entities)

    # 4. Filter entities by type
    pet_res = client.get("/api/people-pets/entities?entity_type=PET")
    assert pet_res.status_code == 200
    pets = pet_res.json()
    assert any(e["id"] == eid for e in pets)

    # 5. Pending reviews endpoint
    pending_res = client.get("/api/people-pets/pending")
    assert pending_res.status_code == 200
    assert "items" in pending_res.json()

    # 6. Delete entity
    del_res = client.delete(f"/api/people-pets/entities/{eid}")
    assert del_res.status_code == 200

    # 7. Resolve duplicates endpoint check
    resolve_res = client.post("/api/people-pets/resolve-duplicates")
    assert resolve_res.status_code == 200
    assert "resolved_count" in resolve_res.json()
    print("API endpoints test PASSED!")

def test_mutual_exclusion_and_duplicate_resolution():
    # 1. Create a dummy photo and entity
    conn = get_connection()
    cur = conn.execute("INSERT INTO photos (file_path, file_name, file_size, file_extension, sha256, indexed_at) VALUES ('test_photo_dup.jpg', 'test_photo_dup.jpg', 100, '.jpg', 'dummyhash123', 1000.0)")
    photo_id = cur.lastrowid
    conn.commit()
    conn.close()

    entity = get_or_create_entity("Test Unique Person", "PERSON")
    eid = entity["id"]

    try:
        # 2. Insert two boxes for the SAME photo assigned to the SAME entity
        b1_id = insert_detected_box({
            "photo_id": photo_id,
            "entity_id": eid,
            "box_type": "FACE",
            "confidence": 0.95,
            "x_min": 0.1, "y_min": 0.1, "x_max": 0.3, "y_max": 0.3,
            "status": "PENDING_REVIEW",
            "match_confidence": 0.98
        })
        b2_id = insert_detected_box({
            "photo_id": photo_id,
            "entity_id": eid,
            "box_type": "FACE",
            "confidence": 0.90,
            "x_min": 0.4, "y_min": 0.1, "x_max": 0.6, "y_max": 0.3,
            "status": "PENDING_REVIEW",
            "match_confidence": 0.88
        })

        # 3. Run resolution pass
        unlinked = resolve_duplicate_photo_entity_assignments()
        assert unlinked >= 1

        # 4. Verify b1 kept the entity and b2 was reset to UNASSIGNED
        b1 = get_box_by_id(b1_id)
        b2 = get_box_by_id(b2_id)
        assert b1["entity_id"] == eid
        assert b1["status"] == "PENDING_REVIEW"
        assert b2["entity_id"] is None
        assert b2["status"] == "UNASSIGNED"
        assert b2["match_confidence"] == 0.0
        print("Mutual exclusion and duplicate resolution test PASSED!")
    finally:
        delete_box(b1_id)
        delete_box(b2_id)
        delete_entity(eid)
        conn = get_connection()
        conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
        conn.commit()
        conn.close()

def test_redundant_pet_face_cleanup_and_suppression():
    from backend.app import cleanup_redundant_boxes

    # 1. Create a dummy photo and entity
    conn = get_connection()
    cur = conn.execute("INSERT INTO photos (file_path, file_name, file_size, file_extension, sha256, indexed_at) VALUES ('test_pet_cleanup.jpg', 'test_pet_cleanup.jpg', 100, '.jpg', 'hashpet123', 1000.0)")
    photo_id = cur.lastrowid
    conn.commit()
    conn.close()

    pet_entity = get_or_create_entity("Test Dobby Dog", "PET")
    eid = pet_entity["id"]

    try:
        # Outer PET box (whole dog)
        pet_box_id = insert_detected_box({
            "photo_id": photo_id,
            "entity_id": eid,
            "box_type": "PET",
            "label": "dog",
            "confidence": 0.95,
            "x_min": 0.1, "y_min": 0.1, "x_max": 0.8, "y_max": 0.8,
            "status": "CONFIRMED",
            "match_confidence": 1.0
        })

        # Nested unassigned face box (e.g. snout detected as face)
        face_box_id = insert_detected_box({
            "photo_id": photo_id,
            "entity_id": None,
            "box_type": "FACE",
            "label": "person",
            "confidence": 0.85,
            "x_min": 0.4, "y_min": 0.4, "x_max": 0.55, "y_max": 0.55,
            "status": "UNASSIGNED",
            "match_confidence": 0.0
        })

        # Run cleanup
        cleanup_redundant_boxes(photo_id, pet_box_id)

        # Verify face box was cleaned up (deleted)
        remaining_face = get_box_by_id(face_box_id)
        assert remaining_face is None

        # Verify pet box remains intact
        remaining_pet = get_box_by_id(pet_box_id)
        assert remaining_pet is not None
        assert remaining_pet["status"] == "CONFIRMED"

        delete_box(pet_box_id)
    finally:
        delete_entity(eid)
        conn = get_connection()
        conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
        conn.commit()
        conn.close()

if __name__ == "__main__":
    test_database_entity_and_boxes_crud()
    test_detector_embedding_and_matching()
    test_api_endpoints()
    test_mutual_exclusion_and_duplicate_resolution()
    test_redundant_pet_face_cleanup_and_suppression()
    print("ALL TESTS COMPLETED SUCCESSFULLY!")

