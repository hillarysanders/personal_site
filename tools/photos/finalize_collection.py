"""Audit approved edits, historical revisions, and every inventoried RAW."""

# %% Imports and notebook reload
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import argparse
import hashlib
import json
import sys

import numpy as np
from PIL import Image
import tifffile

from art_pipeline import embedded_jpeg
from image_paths import WORKSPACE_ROOT, PATHS, metadata_path, source_path

IN_NOTEBOOK = "ipykernel" in sys.modules
if IN_NOTEBOOK:
    from IPython import get_ipython
    ipython = get_ipython()
    ipython.run_line_magic("load_ext", "autoreload")
    ipython.run_line_magic("autoreload", "2")

V3 = {"exposure_ev": .85, "saturation": 1.09, "contrast": 1.15, "contrast_pivot": .35}


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


# %% File, geometry, recipe, and preservation audit
def verify(root):
    manifest = read_json(metadata_path(root, "processing_manifest.json"))
    inventory = read_json(metadata_path(root, "source_inventory.json"))
    files = {entry["filename"]: entry for entry in inventory["files"]}
    preserved_revisions = []
    output = root / PATHS["output"]
    for directory in sorted((output / "revisions").iterdir()):
        name = directory.name
        for filename, expected in read_json(directory / "checksums.json").items():
            require(sha256(directory / Path(filename).name) == expected, f"Preserved revision changed: {name}/{filename}")
        preserved_revisions.append(name)
    qa = metadata_path(root, "qa")
    qa_checksums = read_json(qa / "checksums.json")
    for filename, expected in qa_checksums.items():
        require(sha256(qa / filename) == expected, f"Preserved QA evidence changed: {filename}")
    require(len(files) == manifest["source_count"], "Inventory differs from recorded source count")
    grouped = {source for artwork in manifest["artworks"] for source in artwork["sources"]}
    require(grouped == set(files), "Artwork groups do not account for exactly all original RAWs")
    require({path.name for path in (root / PATHS["raw"]).glob("*.NEF")} == set(files), "RAW directory differs from inventory")
    raw_locations = {}
    for filename, entry in files.items():
        path = root / entry["current_path"]
        require(path.parent == root / PATHS["raw"], f"RAW outside configured directory: {filename}")
        require(path.stat().st_size == entry["bytes"] and sha256(path) == entry["sha256"], f"Original content changed: {filename}")
        raw_locations[filename] = path.relative_to(root).as_posix()
    require(raw_locations == manifest["source_locations"], "Manifest/inventory source locations disagree")
    output_records, unresolved = [], []
    for artwork in manifest["artworks"]:
        identity = artwork["id"]
        require(artwork["source"] in artwork["sources"], f"{identity}: selected source not in group")
        camera_bytes, _ = embedded_jpeg(source_path(root, artwork["source"]))
        require((root / artwork["original_camera_path"]).read_bytes() == camera_bytes, f"{identity}: camera JPEG is not exact")
        result = artwork["rendered"]
        if result is None:
            require(artwork["status"].startswith("needs_") and artwork["issues"], f"{identity}: unresolved note absent")
            unresolved.append({"id": identity, "status": artwork["status"], "issues": artwork["issues"]})
            continue
        require(artwork["status"] == "processed", f"{identity}: rendered status must be processed")
        require("native_qa" in artwork, f"{identity}: native QA record missing")
        recipe = V3 | ({"exposure_ev": .8} if identity == "art-036" else {})
        require(all(result[key] == value for key, value in recipe.items()), f"{identity}: not the approved V3 recipe")
        master_path, jpeg_path = root / result["master_path"], root / result["jpeg_path"]
        with tifffile.TiffFile(master_path) as master:
            pixels = master.asarray()
            require(pixels.dtype == np.uint16 and pixels.ndim == 3 and pixels.shape[2] == 3, f"{identity}: expected RGB16 master")
            require(bool(master.pages[0].tags[34675].value), f"{identity}: TIFF ICC profile missing")
        height, width = pixels.shape[:2]
        require([width, height] == result["output_size"], f"{identity}: master dimensions mismatch")
        # Independent integer rounding of width/height scales by the ratio for panoramas.
        ratio = artwork["aspect_ratio"]
        require(abs(width - ratio * height) <= max(1, ratio), f"{identity}: proportions mismatch")
        if artwork["aspect_ratio"] == 1:
            require(width == height, f"{identity}: square artwork is stretched")
        with Image.open(jpeg_path) as jpeg:
            require(list(jpeg.size) == result["jpeg_size"] and max(jpeg.size) <= 3000, f"{identity}: website JPEG size mismatch")
            require(jpeg.width <= width and jpeg.height <= height, f"{identity}: JPEG enlarged")
            require(bool(jpeg.info["icc_profile"]), f"{identity}: JPEG ICC profile missing")
            jpeg.verify()
        if identity in {"art-001", "art-020", "art-036"}:
            require(np.array_equal(pixels, tifffile.imread(output / f"color-variants/{identity}/v3.tif")), f"{identity}: differs from approved sample V3")
        output_records.append({"id": identity, "master_size": [width, height], "master_sha256": sha256(master_path),
                               "jpeg_sha256": sha256(jpeg_path), "recipe_verified": recipe, "exact_camera_jpeg": True,
                               "bright_channel_pixel_percent": float(np.any(pixels == 65535, axis=-1).mean() * 100),
                               "black_channel_pixel_percent": float(np.any(pixels == 0, axis=-1).mean() * 100),
                               "native_qa": artwork["native_qa"]})
        print(f"Verified {identity}: {width}×{height}", flush=True)
    report = {"validated_at_utc": datetime.now(timezone.utc).isoformat(), "revision": "collection-v3", "status": "passed",
              "manifest_sha256": sha256(metadata_path(root, "processing_manifest.json")), "source_count": len(files),
              "all_original_hashes_unchanged": True, "source_locations": raw_locations,
              "preserved_revision_hashes_verified": preserved_revisions,
              "preserved_qa_files_verified": len(qa_checksums),
              "finished_count": len(output_records), "unresolved_count": len(unresolved),
              "quality_counts": dict(Counter(artwork["image_quality"] for artwork in manifest["artworks"])),
              "outputs": output_records, "unresolved": unresolved}
    write_json(metadata_path(root, "validation_report.json"), report)
    print(f"Verified {len(output_records)} finished images, {len(unresolved)} unresolved artworks, all {len(files)} original hashes", flush=True)
    return report


# %% Command line
if __name__ == "__main__" and not IN_NOTEBOOK:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["verify"])
    parser.add_argument("--root", type=Path, default=WORKSPACE_ROOT)
    args = parser.parse_args()
    verify(args.root.resolve())
