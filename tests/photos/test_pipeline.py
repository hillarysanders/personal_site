"""Small synthetic checks; no real RAW development or collection-wide runs."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/photos"))
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image
import tifffile

import art_pipeline as pipeline
from image_paths import PATHS, metadata_path, source_path


class PipelineTests(unittest.TestCase):
    def test_source_identity_resolves_inventory_location(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            inventory = metadata_path(root, "source_inventory.json")
            inventory.parent.mkdir(parents=True)
            inventory.write_text(json.dumps({"files": [{"filename": "camera.NEF", "current_path": "images/raw/camera.NEF"}]}))
            self.assertEqual(source_path(root, "camera.NEF"), root / "images/raw/camera.NEF")
            with self.assertRaises(KeyError):
                source_path(root, "unknown.NEF")

    def test_cli_persists_render_metadata_and_keeps_stage_and_status(self):
        with TemporaryDirectory() as directory:
            manifest_path = metadata_path(directory, "processing_manifest.json")
            manifest_path.parent.mkdir(parents=True)
            manifest = {"stage": "pilot_review", "settings": {}, "artworks": [
                {"id": "art-001", "status": "pilot", "rendered": {"output_size": [1, 1]}},
                {"id": "art-002", "status": "pending_processing", "rendered": None},
            ]}
            manifest_path.write_text(json.dumps(manifest))
            result = {"id": "art-001", "output_size": [120, 160]}
            with patch("sys.argv", ["art_pipeline.py", "--root", directory, "render"]), \
                    patch.object(pipeline, "render_artwork", return_value=result) as render, \
                    patch("builtins.print"):
                pipeline.main()
            updated = json.loads(manifest_path.read_text())
            render.assert_called_once()
            self.assertEqual(updated["artworks"][0]["rendered"], result)
            self.assertEqual(updated["artworks"][0]["status"], "pilot")
            self.assertEqual(updated["artworks"][1], manifest["artworks"][1])
            self.assertEqual(updated["stage"], "pilot_review")

    def test_orientation_8_matches_counterclockwise_display(self):
        pixels = np.array([[1, 2, 3], [4, 5, 6]])
        np.testing.assert_array_equal(pipeline.orient_pixels(pixels, 8), [[3, 6], [2, 5], [1, 4]])
        np.testing.assert_array_equal(pipeline.orient_pixels(pixels, 6), [[4, 1], [5, 2], [6, 3]])

    def test_srgb_transfer_at_reference_values(self):
        actual = pipeline.linear_to_srgb(np.array([0, 0.0031308, 0.18, 1]))
        np.testing.assert_allclose(actual, [0, 0.040449936, 0.46135613, 1], atol=1e-7)

    def test_color_revision_preserves_neutrals_and_rejects_invalid_settings(self):
        neutral = np.array([[[12000, 12000, 12000], [24000, 24000, 24000]]], dtype=np.uint16)
        baseline = pipeline.encoded_pixels(neutral, exposure_ev=0.5)
        np.testing.assert_array_equal(pipeline.encoded_pixels(neutral, 0.5, saturation=1.06), baseline)
        self.assertTrue(np.all(baseline > pipeline.encoded_pixels(neutral)))
        with self.assertRaisesRegex(ValueError, "finite"):
            pipeline.encoded_pixels(neutral, exposure_ev=np.nan)
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            pipeline.encoded_pixels(neutral, saturation=-1)

    def test_contrast_is_monotonic_preserves_endpoints_and_deepens_shadows(self):
        brightness = np.linspace(0, 1, 1001)
        result = pipeline.linear_to_srgb(pipeline.tone_luminance(pipeline.srgb_to_linear(brightness), 1.2, .35))
        self.assertTrue(np.all(np.diff(result) > 0))
        np.testing.assert_allclose(result[[0, 350, -1]], [0, .35, 1], atol=1e-7)
        self.assertLess(result[100], .1)
        self.assertGreater(result[600], .6)
        color = np.array([[[12000, 24000, 6000]]], dtype=np.uint16)
        output = pipeline.adjusted_linear(color, contrast=1.2)
        np.testing.assert_allclose(output[0, 0] / output[0, 0, 0], [1, 2, .5], atol=1e-6)

    def test_corners_map_to_rectangle_with_native_scale(self):
        corners = np.float32([[10, 10], [130, 15], [125, 95], [15, 90]])
        transform, (width, height) = pipeline.rectification(corners, 1.5, 0, [150, 110])
        actual = cv2.perspectiveTransform(corners[None], transform)[0]
        np.testing.assert_allclose(actual, [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], atol=1e-5)
        self.assertLessEqual(width - 1, np.linalg.norm(corners[2] - corners[3]))
        self.assertLess(abs(width / height - 1.5), 2 / height)

    def test_inset_removes_boundary_without_adding_background(self):
        image = np.full((101, 101, 3), 50000, dtype=np.uint16)
        image[[0, -1]] = 0
        image[:, [0, -1]] = 0
        transform, size = pipeline.rectification([[0, 0], [100, 0], [100, 100], [0, 100]], 1, 1, [101, 101])
        result = cv2.warpPerspective(image, transform, size)
        self.assertEqual(size, (99, 99))
        self.assertTrue(np.all(result == 50000))

    def test_invalid_corner_order_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, "ordered"):
            pipeline.rectification([[0, 0], [0, 50], [50, 50], [50, 0]], 1, 0, [51, 51])

    def test_curved_edges_preserve_corners_and_match_measured_midpoints(self):
        corners = np.float32([[10, 10], [110, 10], [110, 110], [10, 110]])
        transform, size = pipeline.rectification(corners, 1, 0, [121, 121])
        midpoints = [[60, 14], [107, 60], [60, 108], [13, 60]]
        boundary = np.float32([[[0, 0], [100, 0], [100, 100], [0, 100], [50, 0], [100, 50], [50, 100], [0, 50]]])
        mapped = pipeline.source_coordinates(boundary, transform, corners, midpoints)[0]
        np.testing.assert_allclose(mapped[:4], corners, atol=1e-4)
        np.testing.assert_allclose(mapped[4:], midpoints, atol=1e-4)
        linear = np.ones((121, 121, 3), dtype=np.uint16) * 12000
        cropped = pipeline.crop_linear(linear, {"corners": corners, "edge_midpoints": midpoints}, transform, size)
        self.assertEqual(cropped.shape, (101, 101, 3))
        self.assertTrue(np.all(cropped == 12000))

    def test_exports_are_tagged_rgb16_and_jpeg_never_enlarges(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            linear_path = root / "linear.npy"
            np.save(linear_path, np.full((81, 101, 3), 12000, dtype=np.uint16))
            preview_path = root / "camera.jpg"
            Image.new("RGB", (101, 81), (100, 120, 140)).save(preview_path)
            development = {
                "linear_path": str(linear_path), "source_size": [101, 81],
                "preview_path": str(preview_path), "camera_preview_path": str(preview_path),
                "camera_embedded_path": str(preview_path), "camera_orientation": 1,
            }
            artwork = {
                "id": "synthetic", "source": "unused.NEF", "aspect_ratio": 1.25,
                "corners": [[0, 0], [100, 0], [100, 80], [0, 80]], "inset_px": 0,
            }
            with patch.object(pipeline, "develop_raw", return_value=development):
                result = pipeline.render_artwork(root, artwork)
            with tifffile.TiffFile(root / result["master_path"]) as master:
                self.assertEqual(master.asarray().dtype, np.uint16)
                self.assertEqual(master.asarray().shape, (81, 101, 3))
                self.assertGreater(len(master.pages[0].tags[34675].value), 0)
            with Image.open(root / result["jpeg_path"]) as jpeg:
                self.assertEqual(jpeg.size, (101, 81))
                self.assertTrue(jpeg.info["icc_profile"])
            self.assertFalse(Path(result["master_path"]).is_absolute())
            self.assertEqual(result["exposure_ev"], 0)
            self.assertEqual((root / result["original_camera_path"]).read_bytes(), preview_path.read_bytes())
            self.assertTrue((root / result["camera_preview_path"]).is_file())
            self.assertTrue((root / result["developed_preview_path"]).is_file())
            self.assertEqual(result["camera_orientation"], 1)


if __name__ == "__main__":
    unittest.main()
