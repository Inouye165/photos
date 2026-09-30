"""Checks that full-queue review confirmation is scoped to pending suggestions."""

from backend.database import confirm_all_pending_boxes, get_connection, init_db


def test_confirm_all_pending_boxes_updates_only_pending_suggestions(tmp_path):
    db_path = str(tmp_path / "review_queue.db")
    init_db(db_path)
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO photos (file_path, file_name, file_size, file_extension, sha256, indexed_at) "
        "VALUES ('photo.jpg', 'photo.jpg', 1, '.jpg', 'hash', 1)"
    )
    photo_id = conn.execute("SELECT id FROM photos").fetchone()[0]
    conn.execute("INSERT INTO entities (name, entity_type, created_at, updated_at) VALUES ('Person', 'PERSON', 1, 1)")
    entity_id = conn.execute("SELECT id FROM entities").fetchone()[0]
    for status in ("PENDING_REVIEW", "PENDING_REVIEW", "UNASSIGNED", "CONFIRMED"):
        conn.execute(
            "INSERT INTO detected_boxes (photo_id, entity_id, x_min, y_min, x_max, y_max, status, created_at) "
            "VALUES (?, ?, 0.1, 0.1, 0.5, 0.5, ?, 1)",
            (photo_id, entity_id, status),
        )
    conn.commit()
    conn.close()

    assert confirm_all_pending_boxes(db_path) == 2
    conn = get_connection(db_path)
    statuses = [row[0] for row in conn.execute("SELECT status FROM detected_boxes ORDER BY id")]
    conn.close()
    assert statuses == ["CONFIRMED", "CONFIRMED", "UNASSIGNED", "CONFIRMED"]