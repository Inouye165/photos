import os
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, UnidentifiedImageError

import backend.image_loader as image_loader
import backend.thumbnails as thumbnails
from backend.classifier import classify_media
from backend.database import get_connection, init_db, upsert_photo
from backend.metadata_extractor import extract_metadata
from backend.photo_repair import repair_incomplete_photos


class ImageLoadingTests(unittest.TestCase):
    def test_retries_transient_open_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, "source.jpg")
            Image.new("RGB", (640, 480), "red").save(source_path, "JPEG")
            real_open = image_loader.Image.open
            opened_image = real_open(source_path)

            with patch.object(
                image_loader.Image,
                "open",
                side_effect=[UnidentifiedImageError("transient"), opened_image],
            ) as mocked_open:
                with image_loader.open_image_with_retry(source_path, attempts=2, retry_delay=0) as image:
                    self.assertEqual(image.size, (640, 480))

            self.assertEqual(mocked_open.call_count, 2)

    def test_force_refresh_replaces_corrupt_thumbnail_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, "source.jpg")
            cache_dir = os.path.join(temp_dir, "cache")
            Image.new("RGB", (640, 480), "blue").save(source_path, "JPEG")

            with patch.object(thumbnails, "CACHE_DIR", cache_dir):
                thumb_path = thumbnails.generate_thumbnail(source_path, 1, "thumb")
                self.assertIsNotNone(thumb_path)
                with open(thumb_path, "wb") as cache_file:
                    cache_file.write(b"broken")

                refreshed_path = thumbnails.generate_thumbnail(source_path, 1, "thumb", force=True)
                self.assertEqual(refreshed_path, thumb_path)
                with Image.open(refreshed_path) as refreshed:
                    refreshed.verify()
                    self.assertEqual(refreshed.format, "WEBP")
                self.assertFalse(any(name.endswith(".tmp") for name in os.listdir(cache_dir)))


class CatalogRepairTests(unittest.TestCase):
    def test_repairs_legacy_rows_and_quarantines_bad_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "photos.db")
            valid_path = os.path.join(temp_dir, "valid.jpg")
            invalid_path = os.path.join(temp_dir, "invalid.jpg")
            missing_path = os.path.join(temp_dir, "missing.jpg")
            Image.new("RGB", (800, 600), "green").save(valid_path, "JPEG")
            with open(invalid_path, "wb") as invalid_file:
                invalid_file.write(b"not an image")
            Image.new("RGB", (800, 600), "yellow").save(missing_path, "JPEG")
            init_db(db_path)

            valid_id = self._insert_legacy_row(valid_path, db_path)
            invalid_id = self._insert_legacy_row(invalid_path, db_path)
            missing_id = self._insert_legacy_row(missing_path, db_path)
            os.remove(missing_path)

            report = repair_incomplete_photos(db_path, generate_thumbnails=False)

            self.assertEqual(report["total"], 3)
            self.assertEqual(report["repaired"], 1)
            self.assertEqual(report["unsupported"], 1)
            self.assertEqual(report["missing"], 1)
            self.assertEqual(report["failed"], 0)

            conn = get_connection(db_path)
            try:
                valid = conn.execute("SELECT * FROM photos WHERE id = ?", (valid_id,)).fetchone()
                invalid = conn.execute("SELECT * FROM photos WHERE id = ?", (invalid_id,)).fetchone()
                missing = conn.execute("SELECT * FROM photos WHERE id = ?", (missing_id,)).fetchone()
            finally:
                conn.close()

            self.assertEqual((valid["width"], valid["height"]), (800, 600))
            self.assertEqual(valid["format"], "JPEG")
            self.assertIsNotNone(valid["phash"])
            self.assertEqual(invalid["classification"], "UNSUPPORTED")
            self.assertEqual(invalid["format"], "UNREADABLE")
            self.assertEqual(missing["classification"], "UNSUPPORTED")

    @staticmethod
    def _insert_legacy_row(file_path, db_path):
        metadata = extract_metadata(file_path)
        classification, score, reason = classify_media(metadata)
        metadata["classification"] = "LIKELY_PHOTO" if classification == "UNSUPPORTED" else classification
        metadata["classification_score"] = 0.5 if classification == "UNSUPPORTED" else score
        metadata["classification_reason"] = "Legacy incomplete record" if classification == "UNSUPPORTED" else reason
        metadata["width"] = None
        metadata["height"] = None
        metadata["format"] = None
        metadata["phash"] = None
        metadata["dhash"] = None
        metadata["indexed_at"] = 1.0
        return upsert_photo(metadata, db_path)


if __name__ == "__main__":
    unittest.main()