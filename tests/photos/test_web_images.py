"""Small RGB16 fixtures exercise codec outputs, immutable caching and partial rebuilds."""
from hashlib import sha256
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/photos"))
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import os
import unittest

import numpy as np
from PIL import Image, ImageCms
import tifffile

import export_web_images as exporter


class WebImageTests(unittest.TestCase):
    def test_exports_preserve_color_dimensions_and_partial_manifest(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / exporter.PATHS["output"]
            output.mkdir(parents=True)
            metadata = exporter.metadata_path(root, "processing_manifest.json")
            metadata.parent.mkdir(parents=True)
            config = {"target_edges": [32, 80], "workers": 1,
                      "formats": {"webp": {"quality": 88, "method": 4},
                                  "avif": {"quality": 75, "speed": 4, "subsampling": "4:2:0"}}}
            (root / "images/web.json").write_text(json.dumps(config))
            profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
            pixels = np.broadcast_to(np.linspace(0, 65535, 64, dtype=np.uint16)[None, :, None], (40, 64, 3)).copy()
            artworks = []
            for identity in ["art-001", "art-002"]:
                path = output / f"{identity}.tif"
                tifffile.imwrite(path, pixels, photometric="rgb", extratags=[(34675, "B", len(profile), profile, False)])
                artworks.append({"id": identity, "status": "processed", "rendered": {
                    "master_path": path.relative_to(root).as_posix(), "output_size": [64, 40]}})
            metadata.write_text(json.dumps({"artworks": artworks}))

            with patch("builtins.print"):
                first = exporter.export_collection(root)
            for records in first.values():
                self.assertEqual([(record["width"], record["height"]) for record in records], [(32, 20), (64, 40)])
                for record in records:
                    for format_name, (file_field, bytes_field) in exporter.FORMAT_FIELDS.items():
                        path = root / record[file_field]
                        self.assertFalse(Path(record[file_field]).is_absolute())
                        self.assertTrue(path.stem.endswith(sha256(path.read_bytes()).hexdigest()[:12]))
                        self.assertEqual(path.stat().st_size, record[bytes_field])
                        with Image.open(path) as image:
                            self.assertEqual(image.format, format_name.upper())
                            self.assertEqual(image.info["icc_profile"], profile)
                            self.assertFalse(image.getexif())

            # A warm build must validate and reuse bytes without calling an encoder.
            with patch("builtins.print"), patch.object(Image.Image, "save", side_effect=AssertionError("Unexpected encoding")):
                self.assertEqual(exporter.export_collection(root), first)

            # Content hashes invalidate even when file size and modification time match.
            source = root / artworks[0]["rendered"]["master_path"]
            previous_stat = source.stat()
            tifffile.imwrite(source, 65535 - pixels, photometric="rgb", extratags=[(34675, "B", len(profile), profile, False)])
            os.utime(source, ns=(previous_stat.st_atime_ns, previous_stat.st_mtime_ns))
            self.assertEqual(source.stat().st_size, previous_stat.st_size)
            with patch("builtins.print"):
                updated = exporter.export_collection(root, ["art-001"])
            self.assertEqual(updated["art-002"], first["art-002"])
            self.assertNotEqual(updated["art-001"][0]["file"], first["art-001"][0]["file"])
            self.assertTrue((root / first["art-001"][0]["file"]).exists())

            damaged = root / updated["art-001"][0]["avif_file"]
            damaged.write_bytes(damaged.read_bytes() + b"corrupt")
            with self.assertRaisesRegex(ValueError, "content hash changed"), patch("builtins.print"):
                exporter.export_collection(root, ["art-001"])


if __name__ == "__main__":
    unittest.main()
