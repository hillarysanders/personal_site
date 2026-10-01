"""Imported selections must survive full exports without modifying camera records."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/photos'))
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from PIL import Image
from collection_sources import collection_artworks
from export_web_images import export_collection, read_master


class ImportedSourcesTests(unittest.TestCase):
    def test_full_export_includes_additions_and_selection_without_rewriting_raw(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / 'images/metadata'
            metadata.mkdir(parents=True)
            photo = root / 'source.jpg'
            exif = Image.Exif(); exif[274] = 6
            Image.new('RGB', (48, 32), '#b57344').save(photo, exif=exif)
            rendered = {'master_path': 'source.jpg', 'output_size': [32, 48]}
            original = {'artworks': [{'id': 'art-001', 'status': 'needs_new_photo', 'rendered': None}]}
            raw_path = metadata / 'processing_manifest.json'
            raw_path.write_text(json.dumps(original))
            imported = {'artworks': [{'id': 'art-083', 'status': 'processed', 'rendered': rendered}],
                        'replacements': {'art-001': {'rendered': rendered}}}
            (metadata / 'imported_artworks.json').write_text(json.dumps(imported))
            (root / 'images/web.json').write_text(json.dumps({'target_edges': [24, 90], 'workers': 1,
                'formats': {'webp': {'quality': 88}, 'avif': {'quality': 75, 'speed': 8}}}))
            with patch('builtins.print'):
                manifest = export_collection(root)
                repeated = export_collection(root)
            self.assertEqual(manifest, repeated)
            self.assertEqual(set(manifest), {'art-001', 'art-083'})
            self.assertEqual((manifest['art-083'][-1]['width'], manifest['art-083'][-1]['height']), (32, 48))
            self.assertEqual(json.loads(raw_path.read_text()), original)
            image, profile = read_master(photo)
            self.assertEqual(image.size, (32, 48))
            self.assertTrue(profile)
            imported['artworks'][0]['id'] = 'art-001'
            (metadata / 'imported_artworks.json').write_text(json.dumps(imported))
            with self.assertRaisesRegex(ValueError, 'overlap'):
                collection_artworks(root)


if __name__ == '__main__':
    unittest.main()
