"""
Comprehensive automated tests for People and Pets Detection, Visual Embeddings,
High-Confidence Auto-Tagging, and Confirmation Review Queue.
"""

import os
import sys
import json
import tempfile
import atexit
import shutil
import pytest

# Always isolate automated tests from the live production photos.db
if not os.environ.get("LUMINA_DB_PATH"):
    _TEST_DB_DIR = tempfile.mkdtemp(prefix="lumina_test_suite_")
    os.environ["LUMINA_DB_PATH"] = os.path.join(_TEST_DB_DIR, "test_photos.db")
    atexit.register(lambda: shutil.rmtree(_TEST_DB_DIR, ignore_errors=True))

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
    conn = get_connection()
    row = conn.execute("SELECT id, file_path FROM photos LIMIT 1").fetchone()
    created_dummy_photo = False
    if row:
        photo_id = row["id"]
    else:
        cur = conn.execute(
            "INSERT INTO photos (file_path, file_name, file_size, file_extension, sha256, indexed_at) VALUES ('test_crud_photo.jpg', 'test_crud_photo.jpg', 100, '.jpg', 'crudhash123', 1000.0)"
        )
        photo_id = cur.lastrowid
        conn.commit()
        created_dummy_photo = True
    conn.close()

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
        "candidate_entities_json": json.dumps([{"entity_id": eid, "score": 0.91}]),
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
    pending_box = next(b for b in pending_items if b["id"] == box_id)
    assert json.loads(pending_box["candidate_entities_json"])[0]["entity_id"] == eid

    # 7. Confirm box
    confirm_res = confirm_box(box_id)
    assert confirm_res is True
    confirmed_box = get_box_by_id(box_id)
    assert confirmed_box["status"] == "CONFIRMED"
    assert json.loads(confirmed_box["candidate_entities_json"]) == []

    # 8. Clean up
    delete_box(box_id)
    delete_entity(eid)
    if created_dummy_photo:
        conn = get_connection()
        conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
        conn.commit()
        conn.close()
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

    ambiguous_candidates = detector.rank_entity_candidates(
        emb,
        {100: [emb], 200: [emb], 300: [emb], 400: [emb]},
        threshold=0.78
    )
    assert len(ambiguous_candidates) == 3

    clear_candidates = detector.rank_entity_candidates(
        emb,
        {100: [emb], 200: [[-x for x in emb]]},
        threshold=0.78
    )
    assert clear_candidates == [(100, 1.0)]

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

def test_semantic_search_for_tagged_entities():
    # Create two dummy photos and a tagged person entity
    conn = get_connection()
    cur1 = conn.execute(
        "INSERT INTO photos (file_path, file_name, file_size, file_extension, classification, sha256, indexed_at) "
        "VALUES ('test_person_search_1.jpg', 'test_person_search_1.jpg', 100, '.jpg', 'VERIFIED_PHOTO', 'hash_person_search_1', 1000.0)"
    )
    p1_id = cur1.lastrowid
    cur2 = conn.execute(
        "INSERT INTO photos (file_path, file_name, file_size, file_extension, classification, sha256, indexed_at) "
        "VALUES ('test_person_search_2.jpg', 'test_person_search_2.jpg', 100, '.jpg', 'VERIFIED_PHOTO', 'hash_person_search_2', 1001.0)"
    )
    p2_id = cur2.lastrowid
    conn.commit()
    conn.close()

    entity = get_or_create_entity("UniqueSearchPersonZeta", "PERSON")
    eid = entity["id"]
    b1_id = None
    b2_id = None

    try:
        b1_id = insert_detected_box({
            "photo_id": p1_id,
            "entity_id": eid,
            "box_type": "FACE",
            "label": "person",
            "confidence": 0.99,
            "x_min": 0.1, "y_min": 0.1, "x_max": 0.5, "y_max": 0.5,
            "status": "CONFIRMED",
            "match_confidence": 1.0
        })
        b2_id = insert_detected_box({
            "photo_id": p2_id,
            "entity_id": eid,
            "box_type": "FACE",
            "label": "person",
            "confidence": 0.92,
            "x_min": 0.2, "y_min": 0.2, "x_max": 0.6, "y_max": 0.6,
            "status": "PENDING_REVIEW",
            "match_confidence": 0.91
        })

        # 1. Search by exact name
        res = client.get("/api/photos", params={"query": "UniqueSearchPersonZeta"})
        assert res.status_code == 200
        data = res.json()
        returned_ids = [p["id"] for p in data["photos"]]
        assert p1_id in returned_ids
        assert p2_id in returned_ids
        # Confirmed photo should rank first
        assert returned_ids.index(p1_id) < returned_ids.index(p2_id)
        assert data["parsed_query"]["entity_ids"] == [eid]

        # 2. Search with conversational prefix
        res2 = client.get("/api/photos", params={"query": "show me photos of UniqueSearchPersonZeta"})
        assert res2.status_code == 200
        returned_ids_2 = [p["id"] for p in res2.json()["photos"]]
        assert p1_id in returned_ids_2
        assert p2_id in returned_ids_2
        print("Semantic search for tagged entities test PASSED!")
    finally:
        if b1_id:
            delete_box(b1_id)
        if b2_id:
            delete_box(b2_id)
        delete_entity(eid)
        conn = get_connection()
        conn.execute("DELETE FROM photos WHERE id IN (?, ?)", (p1_id, p2_id))
        conn.commit()
        conn.close()

def test_rematch_unassigned_boxes_group_photo_and_type_safety():
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="rematch_test_")
    test_db = os.path.join(tmp_dir, "rematch.db")
    init_db(test_db)

    try:
        conn = get_connection(test_db)
        p1 = conn.execute(
            "INSERT INTO photos (file_path, file_name, file_size, file_extension, classification, sha256, indexed_at) "
            "VALUES ('p1.jpg', 'p1.jpg', 100, '.jpg', 'VERIFIED_PHOTO', 'h1', 1.0)"
        ).lastrowid
        p2 = conn.execute(
            "INSERT INTO photos (file_path, file_name, file_size, file_extension, classification, sha256, indexed_at) "
            "VALUES ('p2.jpg', 'p2.jpg', 100, '.jpg', 'VERIFIED_PHOTO', 'h2', 2.0)"
        ).lastrowid
        conn.commit()
        conn.close()

        person_a = get_or_create_entity("Alice", "PERSON", db_path=test_db)
        person_b = get_or_create_entity("Bob", "PERSON", db_path=test_db)
        pet_c = get_or_create_entity("Rex", "PET", db_path=test_db)

        vec_b = [0.0] * 512
        vec_b[10] = 1.0

        # Confirm Bob on photo 1
        insert_detected_box({
            "photo_id": p1,
            "entity_id": person_b["id"],
            "box_type": "FACE",
            "label": "person",
            "confidence": 0.99,
            "x_min": 0.1, "y_min": 0.1, "x_max": 0.3, "y_max": 0.3,
            "embedding_json": json.dumps(vec_b),
            "status": "CONFIRMED",
            "match_confidence": 1.0
        }, db_path=test_db)

        # On photo 2 (group photo): Alice is ALREADY CONFIRMED, Bob's face is UNASSIGNED, and a PET box has Bob's vector
        insert_detected_box({
            "photo_id": p2,
            "entity_id": person_a["id"],
            "box_type": "FACE",
            "label": "person",
            "confidence": 0.99,
            "x_min": 0.1, "y_min": 0.1, "x_max": 0.3, "y_max": 0.3,
            "embedding_json": json.dumps([1.0] + [0.0] * 511),
            "status": "CONFIRMED",
            "match_confidence": 1.0
        }, db_path=test_db)

        bob_unassigned_id = insert_detected_box({
            "photo_id": p2,
            "entity_id": None,
            "box_type": "FACE",
            "label": "person",
            "confidence": 0.95,
            "x_min": 0.4, "y_min": 0.1, "x_max": 0.6, "y_max": 0.3,
            "embedding_json": json.dumps(vec_b),
            "status": "UNASSIGNED",
            "match_confidence": 0.0
        }, db_path=test_db)

        pet_unassigned_id = insert_detected_box({
            "photo_id": p2,
            "entity_id": None,
            "box_type": "PET",
            "label": "dog",
            "confidence": 0.95,
            "x_min": 0.7, "y_min": 0.5, "x_max": 0.9, "y_max": 0.9,
            "embedding_json": json.dumps(vec_b),
            "status": "UNASSIGNED",
            "match_confidence": 0.0
        }, db_path=test_db)

        detector = FacePetDetector.get_instance()
        rematched = detector.rematch_unassigned_boxes(db_path=test_db)
        assert rematched == 1

        bob_box = get_box_by_id(bob_unassigned_id, db_path=test_db)
        pet_box = get_box_by_id(pet_unassigned_id, db_path=test_db)
        assert bob_box["entity_id"] == person_b["id"]
        assert bob_box["status"] == "PENDING_REVIEW"
        # PET box must NOT match a PERSON entity
        assert pet_box["entity_id"] is None
        assert pet_box["status"] == "UNASSIGNED"
        print("Rematch unassigned boxes group photo and type safety test PASSED!")
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

def test_top_5_fixes_verification():
    """Verifies avatar repair, manual classification preservation on upsert, and VectorEngine.remove_photos."""
    import tempfile
    import numpy as np
    from backend.database import upsert_photo, get_photo_by_id, repair_entity_avatars
    from backend.vector_engine import VectorEngine

    tmp_dir = tempfile.mkdtemp(prefix="lumina_top5_test_")
    test_db = os.path.join(tmp_dir, "test_top5.db")
    try:
        init_db(db_path=test_db)
        # 1. Verify manual classification override is preserved on re-scan upsert
        pid = upsert_photo({
            "file_path": "/fake/manual_override.jpg",
            "file_name": "manual_override.jpg",
            "file_size": 1024,
            "file_extension": ".jpg",
            "sha256": "hash_manual_1",
            "indexed_at": 1000.0,
            "classification": "GOOD",
            "classification_score": 100.0,
            "classification_reason": "User verified",
            "is_manual_override": 1
        }, db_path=test_db)
        # Simulate scanner upserting without is_manual_override
        upsert_photo({
            "file_path": "/fake/manual_override.jpg",
            "file_name": "manual_override.jpg",
            "file_size": 1024,
            "file_extension": ".jpg",
            "sha256": "hash_manual_1",
            "indexed_at": 2000.0,
            "classification": "BAD_BLURRY",
            "classification_score": 12.0,
            "classification_reason": "Blurry auto check"
        }, db_path=test_db)
        row = get_photo_by_id(pid, db_path=test_db)
        assert row["classification"] == "GOOD"
        assert row["is_manual_override"] == 1

        # 2. Verify repair_entity_avatars fixes broken avatar_box_id
        person = get_or_create_entity("AvatarRepairPerson", "PERSON", db_path=test_db)
        eid = person["id"]
        valid_box_id = insert_detected_box({
            "photo_id": pid,
            "entity_id": eid,
            "box_type": "FACE",
            "label": "person",
            "confidence": 0.99,
            "x_min": 0.1, "y_min": 0.1, "x_max": 0.4, "y_max": 0.4,
            "status": "CONFIRMED",
            "match_confidence": 1.0
        }, db_path=test_db)
        # Point avatar_box_id to a non-existent box ID 999999
        update_entity(eid, avatar_box_id=999999, db_path=test_db)
        # list_entities should still fall back to valid_box_id even before repair
        entities_before = list_entities(db_path=test_db)
        ent_before = next(e for e in entities_before if e["id"] == eid)
        assert ent_before["avatar_box_id"] == valid_box_id
        # repair_entity_avatars should permanently fix the DB column
        repaired = repair_entity_avatars(db_path=test_db)
        assert repaired == 1
        fetched = get_entity_by_id(eid, db_path=test_db)
        assert fetched["avatar_box_id"] == valid_box_id

        # 3. Verify VectorEngine.remove_photos removes deleted photo IDs from memory
        ve = VectorEngine()
        ve.photo_ids = [101, 202, 303]
        ve.embeddings = np.eye(3, 512, dtype=np.float32)
        ve.save_index = lambda: None  # no-op for unit test
        ve.remove_photos([202])
        assert ve.photo_ids == [101, 303]
        assert ve.embeddings.shape == (2, 512)
        print("Top 5 fixes verification test PASSED!")
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_database_entity_and_boxes_crud()
    test_detector_embedding_and_matching()
    test_api_endpoints()
    test_mutual_exclusion_and_duplicate_resolution()
    test_redundant_pet_face_cleanup_and_suppression()
    test_semantic_search_for_tagged_entities()
    test_rematch_unassigned_boxes_group_photo_and_type_safety()
    test_top_5_fixes_verification()
    print("ALL TESTS COMPLETED SUCCESSFULLY!")

