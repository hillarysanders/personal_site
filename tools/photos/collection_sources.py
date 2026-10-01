"""Join the preserved RAW collection with explicitly reviewed website imports.

The RAW manifest remains the record of camera processing. Imported originals and
preferred delivery sources live separately, so a RAW rerender cannot erase an
import or silently replace a reviewed website photograph.
"""
import json
from build_catalog import index_rows
from image_paths import metadata_path


def collection_artworks(root):
    records = index_rows(json.loads(metadata_path(root, "processing_manifest.json").read_text())["artworks"], "id")
    path = metadata_path(root, "imported_artworks.json")
    if not path.exists():  # A collection without legacy imports needs no registry.
        return list(records.values())
    imported = json.loads(path.read_text())
    additions = index_rows(imported["artworks"], "id")
    if records.keys() & additions.keys():
        raise ValueError("Imported artwork IDs overlap existing RAW artworks")
    for identity, selection in imported["replacements"].items():
        if identity not in records:
            raise ValueError(f"Replacement has no existing artwork: {identity}")
        records[identity] = records[identity] | {"rendered": selection["rendered"], "status": "processed"}
    return list(records.values()) + list(additions.values())
