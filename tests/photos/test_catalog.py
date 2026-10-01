"""Catalog refresh must preserve authored cells and migrate the legacy schema."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/photos"))

import json
from tempfile import TemporaryDirectory
import unittest

import build_catalog as catalog
import build_website_catalog as website
from image_paths import metadata_path


class CatalogTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        metadata = metadata_path(root, "processing_manifest.json")
        metadata.parent.mkdir(parents=True)
        base = {
            "status": "pending", "source": "DSC_0001.NEF", "sources": ["DSC_0001.NEF", "DSC_0002.NEF"],
            "aspect_ratio": 1.0, "proportion": "1:1", "ratio_confidence": "medium", "working_width_in": 24,
            "working_height_in": 24, "dimension_basis": "working estimate", "dimension_confidence": "low",
            "issues": ["Measure dimensions"], "selection_reason": "Clear detail", "rendered": None,
            "original_camera_path": "images/output/originals/DSC_0001.jpg",
            "image_quality": "pending_review", "needs_reshoot": "pending_review", "quality_notes": "",
        }
        manifest = {"artworks": [base | {"id": identity, "label": title} for identity, title in
                                 [("art-001", "First"), ("art-002", "Second"), ("art-003", "Third")]]}
        metadata.write_text(json.dumps(manifest))
        inventory = {"files": [{"filename": name, "current_path": f"images/raw/{name}"} for name in base["sources"]]}
        metadata_path(root, "source_inventory.json").write_text(json.dumps(inventory))
        return root, metadata, manifest

    def test_annotations_legacy_quality_migration_and_persistent_manual_fields(self):
        with TemporaryDirectory() as directory:
            root, manifest_path, manifest = self.fixture(directory)
            filename = catalog.build_catalog(root, quiet=True)
            imported = catalog.read_csv(filename, [catalog.COLUMNS])
            imported["art-001"].update(title='Blue, "rain"\nStudy', estimated_ratio="1.25", working_height_in="",
                                       confirmed_width_in="0", review_notes="Measured by hand — keep this note")
            legacy_rows = [{field: row[field] for field in catalog.LEGACY_COLUMNS} for row in reversed(list(imported.values()))]
            catalog.write_csv(filename, catalog.LEGACY_COLUMNS, legacy_rows)
            baseline_path = metadata_path(root, "catalog-generated.json")
            baseline = json.loads(baseline_path.read_text())
            for row in baseline.values():
                for field in catalog.QUALITY_COLUMNS:
                    del row[field]
            baseline_path.write_text(json.dumps(baseline))
            for artwork in manifest["artworks"]:
                artwork.update(label=artwork["label"] + " updated", status="pilot", aspect_ratio=0.75, working_height_in=30)
            manifest["artworks"][0].update(image_quality="low_quality", needs_reshoot="yes", quality_notes="Soft detail")
            manifest["artworks"][1].update(image_quality="acceptable", needs_reshoot="no")
            manifest_path.write_text(json.dumps(manifest))
            catalog.build_catalog(root, quiet=True)
            result = catalog.read_csv(filename, [catalog.COLUMNS])
            self.assertEqual(len(result), 3)
            self.assertEqual([row["image_quality"] for row in result.values()], ["low_quality", "acceptable", "pending_review"])
            self.assertEqual([row["needs_reshoot"] for row in result.values()], ["yes", "no", "pending_review"])
            for field, value in {"title": 'Blue, "rain"\nStudy', "estimated_ratio": "1.25", "working_height_in": "",
                                 "confirmed_width_in": "0", "review_notes": "Measured by hand — keep this note",
                                 "status": "pilot", "quality_notes": "Soft detail", "original_raw": "images/raw/DSC_0001.NEF",
                                 "original_camera_jpeg": "images/output/originals/DSC_0001.jpg"}.items():
                self.assertEqual(result["art-001"][field], value)
            self.assertEqual(result["art-002"]["title"], "Second updated")
            self.assertEqual(result["art-002"]["estimated_ratio"], "0.75")
            self.assertEqual(result["art-002"]["working_height_in"], "30")
            result["art-001"].update(image_quality="acceptable", needs_reshoot="no", quality_notes="Reviewed by owner")
            catalog.write_csv(filename, catalog.COLUMNS, result.values())
            for ratio in [1.25, 0.5]:
                manifest["artworks"][0]["aspect_ratio"] = ratio
                manifest_path.write_text(json.dumps(manifest))
                catalog.build_catalog(root, quiet=True)
            refreshed = catalog.read_csv(filename, [catalog.COLUMNS])
            self.assertEqual(refreshed["art-001"]["estimated_ratio"], "1.25")
            self.assertEqual(refreshed["art-001"]["image_quality"], "acceptable")
            self.assertEqual(refreshed["art-001"]["quality_notes"], "Reviewed by owner")

    def test_missing_baseline_retains_blanks_and_zeroes_and_rejects_unknown_ids(self):
        with TemporaryDirectory() as directory:
            root, _, _ = self.fixture(directory)
            filename = catalog.build_catalog(root, quiet=True)
            rows = catalog.read_csv(filename, [catalog.COLUMNS])
            rows["art-001"].update(title="", confirmed_width_in="0")
            catalog.write_csv(filename, catalog.COLUMNS, rows.values())
            metadata_path(root, "catalog-generated.json").unlink()
            catalog.build_catalog(root, quiet=True)
            refreshed = catalog.read_csv(filename, [catalog.COLUMNS])
            self.assertEqual(refreshed["art-001"]["title"], "")
            self.assertEqual(refreshed["art-001"]["confirmed_width_in"], "0")
            refreshed["art-001"]["artwork_id"] = "unknown"
            catalog.write_csv(filename, catalog.COLUMNS, refreshed.values())
            with self.assertRaisesRegex(ValueError, "absent from manifest"):
                catalog.build_catalog(root, quiet=True)

    def test_website_seed_retains_existing_cells_and_adds_only_new_rows(self):
        with TemporaryDirectory() as directory:
            root, manifest_path, manifest = self.fixture(directory)
            curation = {art["id"]: {"description": "Prepared description", "theme": "Portraits"} for art in manifest["artworks"]}
            metadata_path(root, "website-art-metadata.json").write_text(json.dumps(curation))
            config = root / "site.json"
            config.write_text(json.dumps({"size_limits": {"small_under_in": 12, "medium_up_to_in": 30}, "currency": "USD", "default_quality": "all_finished"}))
            filename = website.build_website_catalog(root, config, quiet=True)
            rows = catalog.read_csv(filename, [website.COLUMNS])
            rows["art-001"].update(title="", description='A, "quoted"\ncaption', price="0", availability="private", publish="no")
            catalog.write_csv(filename, website.COLUMNS, rows.values())
            manifest["artworks"][0]["label"] = "Generated title changed"
            manifest_path.write_text(json.dumps(manifest))
            website.build_website_catalog(root, config, quiet=True)
            self.assertEqual(catalog.read_csv(filename, [website.COLUMNS]), rows)

    def test_numbers_fail_loudly(self):
        for invalid in [True, " 1", "NaN", float("inf"), "1e999"]:
            with self.assertRaises(ValueError):
                catalog.number_cell(invalid, "width", "art-001")


if __name__ == "__main__":
    unittest.main()
