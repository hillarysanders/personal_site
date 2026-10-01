"""New artwork intake must not reset the private seed or SQLite editor changes."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/photos"))

import json
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from build_catalog import write_csv
from build_website_catalog import COLUMNS
from import_editor_catalog import import_editor_catalog


class EditorImportTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        repo = root / "checkout"
        config, local = repo / "config", repo / ".local"
        metadata, output = root / "images/metadata", root / "images/output"
        for path in [config, local, metadata, output / "web", output / "previews/sources"]:
            path.mkdir(parents=True)
        (config / "paths.json").write_text(json.dumps({"local": ".local", "library": "../images"}))
        settings = {"include_review_photos": True, "category_aliases": {"Birds & wildlife": "Wildlife"},
                    "size_limits": {"small_under_in": 12, "medium_up_to_in": 24},
                    "artwork_series": [{"id": "pair", "title": "New pair", "members": ["art-002", "art-003"]}]}
        (config / "site.json").write_text(json.dumps(settings))
        original = {"id": "art-001", "title": "Hand-edited seed title", "published": False, "revision": 4, "notes": "Keep private note"}
        (local / "catalog-seed.json").write_text(json.dumps({"site": {"preserved": True}, "artworks": [original]}))
        sources = [{"id": identity, "source": "DSC_0003.NEF", "rendered": {} if identity != "art-003" else None,
                    "quality_notes": "Capture review", "issues": ["Measure before selling"]}
                   for identity in ["art-001", "art-002", "art-003"]]
        (metadata / "processing_manifest.json").write_text(json.dumps({"artworks": sources}))
        base = {field: "" for field in COLUMNS}
        base.update(theme="Birds & wildlife", currency="USD", publish="no", dimensions_confirmed="no", size_category="Unclassified",
                    image_quality="acceptable", needs_reshoot="no", website_notes="Private preparation note")
        rows = [base | {"artwork_id": source["id"], "title": "Prepared title", "display_order": str(index + 1)}
                for index, source in enumerate(sources)]
        rows[1].update(publish="yes", width_in="6", height_in="6", dimensions_confirmed="yes", availability="available", price="100")
        rows[2].update(image_quality="low_quality", needs_reshoot="yes")
        write_csv(metadata / "website_catalog.csv", COLUMNS, rows)
        variant = {"file": "images/output/web/art-002-480-hash.webp", "avif_file": "images/output/web/art-002-480-hash.avif",
                   "width": 480, "height": 480, "target_edge": 480}
        for field in ["file", "avif_file"]:
            (root / variant[field]).write_bytes(b"Exported codec bytes are verified by the exporter")
        (output / "web/manifest.json").write_text(json.dumps({"art-002": [variant]}))
        (output / "previews/sources/DSC_0003.jpg").write_bytes(b"Private reference image")
        database = local / "admin.sqlite"
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE artwork_edits (artwork_id TEXT, document TEXT, revision INTEGER)")
            connection.execute("INSERT INTO artwork_edits VALUES (?, ?, ?)", ("art-001", '{"title":"Owner editor title"}', 8))
        return root, repo, original

    def test_dry_run_and_append_preserve_existing_seed_and_database(self):
        with TemporaryDirectory() as directory:
            root, repo, original = self.fixture(directory)
            local = repo / ".local"
            seed_path, database = local / "catalog-seed.json", local / "admin.sqlite"
            original_seed, original_database = seed_path.read_bytes(), database.read_bytes()
            self.assertEqual(import_editor_catalog(repo, root, dry_run=True), ["art-002", "art-003"])
            self.assertEqual(seed_path.read_bytes(), original_seed)
            self.assertFalse((local / "reference-photos").exists())
            self.assertEqual(import_editor_catalog(repo, root), ["art-002", "art-003"])
            seed = json.loads(seed_path.read_text())
            self.assertEqual(seed["site"], {"preserved": True})
            self.assertEqual(seed["artworks"][0], original)
            self.assertEqual(database.read_bytes(), original_database)
            complete, incomplete = seed["artworks"][1:]
            self.assertTrue(complete["published"])
            self.assertEqual(complete["themes"], ["Wildlife"])
            self.assertEqual(complete["surface"], "")
            self.assertEqual(complete["sizeCategory"], "Small")
            self.assertEqual(complete["notes"], "Private preparation note")
            self.assertEqual(complete["qualityNotes"], "Capture review")
            self.assertEqual(complete["seriesId"], "pair")
            self.assertEqual(incomplete["images"], [])
            self.assertFalse(incomplete["published"])
            self.assertEqual(incomplete["photoStatus"], "needs_photo")
            self.assertEqual(incomplete["referenceImage"], "admin-photos/art-003.jpg")
            self.assertEqual((local / "reference-photos/art-003.jpg").read_bytes(), b"Private reference image")
            imported_seed = seed_path.read_bytes()
            self.assertEqual(import_editor_catalog(repo, root), [])
            self.assertEqual(seed_path.read_bytes(), imported_seed)

    def test_explicit_unpublished_row_stays_draft_even_with_finished_review_photo(self):
        with TemporaryDirectory() as directory:
            root, repo, _ = self.fixture(directory)
            path = root / "images/metadata/website_catalog.csv"
            import csv
            with path.open() as stream:
                rows = list(csv.DictReader(stream))
            rows[1].update(publish="no", image_quality="review")
            write_csv(path, COLUMNS, rows)
            import_editor_catalog(repo, root)
            seed = json.loads((repo / ".local/catalog-seed.json").read_text())
            self.assertFalse(seed["artworks"][1]["published"])
            self.assertEqual(seed["artworks"][1]["photoStatus"], "review")

    def test_deleted_ids_fail_before_any_write(self):
        with TemporaryDirectory() as directory:
            root, repo, _ = self.fixture(directory)
            seed_path = repo / ".local/catalog-seed.json"
            seed = json.loads(seed_path.read_text())
            seed["artworks"].append({"id": "art-999", "notes": "Never silently discard"})
            seed_path.write_text(json.dumps(seed))
            before = seed_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "explicit reconciliation"):
                import_editor_catalog(repo, root)
            self.assertEqual(seed_path.read_bytes(), before)
            self.assertFalse((repo / ".local/reference-photos").exists())


if __name__ == "__main__":
    unittest.main()
