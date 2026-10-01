"""Register explicitly reviewed archive decisions, without changing RAWs or editor edits.

Example: .venv/bin/python tools/photos/register_website_import.py \
  ../images/imports/nfs-20261001/decisions.json
Then export web images and run import_editor_catalog.py. Never infer duplicates
from filenames or feature scores here: each decision must already be reviewed.
"""
# %% Imports and notebook reload
import argparse
from hashlib import file_digest
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps
from build_catalog import index_rows, read_csv, write_csv
from build_website_catalog import build_website_catalog, COLUMNS
from export_web_images import write_json
from image_paths import WORKSPACE_ROOT, metadata_path

IN_NOTEBOOK = "ipykernel" in sys.modules
if IN_NOTEBOOK:
    from IPython import get_ipython
    ipython = get_ipython()
    ipython.run_line_magic("load_ext", "autoreload")
    ipython.run_line_magic("autoreload", "2")


# %% Reconcile reviewed decisions with the preserved archive

def register(decisions_path, root=WORKSPACE_ROOT):
    root = Path(root).resolve()
    decisions = json.loads(Path(decisions_path).read_text())
    archive = root / decisions["archive"]
    inventory = index_rows(json.loads((archive.parent / "inventory.json").read_text())["files"], "path")
    groups = index_rows(decisions["groups"], "id")
    raw = index_rows(json.loads(metadata_path(root, "processing_manifest.json").read_text())["artworks"], "id")
    registry_path = metadata_path(root, "imported_artworks.json")
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else {"version": 1, "artworks": [], "replacements": {}}
    additions = index_rows(registry["artworks"], "id")
    curation_path = metadata_path(root, "website-art-metadata.json")
    curation = json.loads(curation_path.read_text())
    assigned = set()
    for identity, group in groups.items():
        if assigned.intersection(group["sources"]):
            raise ValueError(f"Photograph assigned to multiple artworks: {identity}")
        assigned.update(group["sources"])
        for filename in group["sources"]:
            with (archive / filename).open("rb") as stream:
                actual = file_digest(stream, "sha256").hexdigest()
            if actual != inventory[filename]["sha256"]:
                raise ValueError(f"Archived source changed: {filename}")
        if group["selected"] is None:
            if group["kind"] != "existing" or identity not in raw:
                raise ValueError(f"Only existing artworks can retain a current photo: {identity}")
            registry["replacements"].pop(identity, None)
            continue
        if group["selected"] not in group["sources"]:
            raise ValueError(f"Selected image not in reviewed source group: {identity}")
        photo = archive / group["selected"]
        with Image.open(photo) as original:
            size = list(ImageOps.exif_transpose(original).size)
        rotation = group["rotation"]
        if rotation not in {0, 90, 180, 270}:
            raise ValueError(f"Unsupported rotation: {identity}")
        if rotation in {90, 270}:
            size.reverse()
        rendered = {"master_path": photo.relative_to(root).as_posix(), "output_size": size}
        if rotation:
            rendered["rotation"] = rotation
        provenance = {"archive": decisions["archive"], "sources": group["sources"], "selection_reason": group["reason"]}
        if group["kind"] == "existing":
            if identity not in raw:
                raise ValueError(f"Existing artwork missing: {identity}")
            registry["replacements"][identity] = {"rendered": rendered, **provenance}
        elif group["kind"] == "new":
            if identity in raw:
                raise ValueError(f"New artwork reuses a RAW identity: {identity}")
            quality = {"ready": "acceptable", "review": "review", "needs_photo": "low_quality"}[group["photo_status"]]
            additions[identity] = {"id": identity, "label": group["title"], "status": "processed", "rendered": rendered,
                "working_width_in": None, "working_height_in": None, "dimension_basis": "Not measured; pixel dimensions are not physical measurements.",
                "image_quality": quality, "needs_reshoot": "yes" if group["photo_status"] == "needs_photo" else "no",
                "quality_notes": group["reason"], "issues": [] if quality == "acceptable" else [group["reason"]], **provenance}
            if identity not in curation:
                curation[identity] = {"description": "", "theme": "; ".join(group["themes"])}
        else:
            raise ValueError(f"Unknown decision kind: {group['kind']}")
    registry["artworks"] = list(additions.values())
    # Preserve every existing CSV cell; seed only newly registered IDs.
    csv_path = metadata_path(root, "website_catalog.csv")
    existing = read_csv(csv_path, [COLUMNS])
    write_json(registry_path, registry)
    write_json(curation_path, curation)
    build_website_catalog(root, quiet=True)
    rows = read_csv(csv_path, [COLUMNS])
    for index, (identity, group) in enumerate(groups.items()):
        if group["kind"] != "new" or identity in existing:
            continue
        rows[identity].update(medium=group["medium"], publish="yes" if group["published"] else "no", display_order=1000 + index,
            website_notes="Imported from the previous website. Descriptive title and broad medium need owner confirmation; dimensions, year, price and availability are unknown. " + group["reason"])
    write_csv(csv_path, COLUMNS, rows.values())
    print(f"Registered {len(additions)} imported works and {len(registry['replacements'])} preferred photographs. RAW recipes and existing CSV/editor entries are unchanged.")


# %% Command-line entry
if __name__ == "__main__" and not IN_NOTEBOOK:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decisions", type=Path)
    register(parser.parse_args().decisions)
