# %% Configuration and notebook reload
"""Export approved TIFF masters and reviewed JPEG sources to AVIF/WebP pairs.

Run `.venv/bin/python tools/photos/export_web_images.py` after rendering approved masters;
use `--ids art-036` for a small rebuild. Settings live in images/web.json.
The public manifest and derivative cache live in images/output/web/. Source
SHA-256, recipe and runtime changes invalidate the cache; cache hits are verified.
Partial builds merge their records, and historical hashed images are retained.
"""
from concurrent.futures import ThreadPoolExecutor
from hashlib import file_digest, sha256
from io import BytesIO
from pathlib import Path
import argparse
import json
import sys

import numpy as np
from PIL import Image, ImageCms, ImageOps, __version__ as pillow_version, features
import tifffile

from image_paths import PATHS, WORKSPACE_ROOT, metadata_path
from collection_sources import collection_artworks

IN_NOTEBOOK = "ipykernel" in sys.modules
if IN_NOTEBOOK:
    from IPython import get_ipython
    ipython = get_ipython()
    ipython.run_line_magic("load_ext", "autoreload")
    ipython.run_line_magic("autoreload", "2")

ROOT = WORKSPACE_ROOT
PIPELINE_VERSION = 1
FORMAT_FIELDS = {"webp": ("file", "bytes"), "avif": ("avif_file", "avif_bytes")}


# %% Content identity and verified derivatives
def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest_file(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    """Publish metadata only after every selected artwork has exported successfully."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def validate_outputs(root, saved):
    """Reject corrupt cache entries, renamed bytes, color loss or leaked metadata."""
    for record in saved["outputs"]:
        for format_name, (file_field, bytes_field) in FORMAT_FIELDS.items():
            path = root / record[file_field]
            digest = digest_file(path)
            require(digest == saved["sha256"][record[file_field]], f"{path}: content hash changed")
            require(path.stem.endswith("-" + digest[:12]), f"{path}: immutable filename does not match content")
            require(path.stat().st_size == record[bytes_field], f"{path}: byte count changed")
            with Image.open(path) as image:
                image.load()
                require(image.format == format_name.upper() and image.mode == "RGB", f"{path}: expected RGB {format_name}")
                require(list(image.size) == [record["width"], record["height"]], f"{path}: dimensions changed")
                require(sha256(image.info["icc_profile"]).hexdigest() == saved["icc_sha256"], f"{path}: ICC changed")
                require(not image.getexif(), f"{path}: unexpected EXIF metadata")
                require(image.width <= saved["source_size"][0] and image.height <= saved["source_size"][1],
                        f"{path}: export enlarged the master")


def read_master(path):
    """Decode approved TIFFs or archived JPEGs without applying the RAW recipe twice."""
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        with Image.open(path) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
            # Old untagged website JPEGs are explicitly interpreted as web sRGB.
            if "icc_profile" in original.info:
                source = ImageCms.ImageCmsProfile(BytesIO(original.info["icc_profile"]))
                image = ImageCms.profileToProfile(image, source, profile, outputMode="RGB")
            return image, profile.tobytes()
    require(path.suffix.lower() in {".tif", ".tiff"}, f"Unsupported delivery source: {path}")
    with tifffile.TiffFile(path) as master:
        require(len(master.pages) == 1, f"{path}: expected one TIFF page")
        pixels = master.asarray()
        profile = master.pages[0].tags[34675].value
    require(pixels.dtype == np.uint16 and pixels.ndim == 3 and pixels.shape[2] == 3,
            f"{path}: expected RGB16 master")
    require("srgb" in ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(BytesIO(profile))).lower(),
            f"{path}: expected sRGB master")
    # Masters are already sRGB encoded: 65535 / 255 == 257; no second color transform.
    return Image.fromarray(np.rint(pixels.astype(np.float32) / 257).astype(np.uint8)), profile


def export_artwork(root, artwork, config, cache):
    """Decode the selected source, resize proportionally, and encode current web variants."""
    identity = artwork["id"]
    master_path = root / artwork["rendered"]["master_path"]
    signature = sha256(json.dumps({
        "source_sha256": digest_file(master_path), "source_size": artwork["rendered"]["output_size"],
        "target_edges": config["target_edges"], "formats": config["formats"], "pipeline_version": PIPELINE_VERSION,
        **({"rotation": artwork["rendered"]["rotation"]} if "rotation" in artwork["rendered"] else {}),
        "runtime": {"pillow": pillow_version, "numpy": np.__version__, "tifffile": tifffile.__version__,
                    "webp": features.version("webp"), "avif": features.version("avif")},
    }, sort_keys=True).encode()).hexdigest()
    if identity in cache and cache[identity]["fingerprint"] == signature:
        saved = cache[identity]
        if all((root / record[field]).is_file() for record in saved["outputs"] for field, _ in FORMAT_FIELDS.values()):
            validate_outputs(root, saved)
            return identity, saved, "cached"

    image, profile = read_master(master_path)
    if "rotation" in artwork["rendered"]:
        rotation = artwork["rendered"]["rotation"]
        require(rotation in {90, 180, 270}, f"{identity}: rotation must be 90, 180 or 270 degrees")
        image = image.rotate(rotation, expand=True)
    width, height = image.size
    require([width, height] == artwork["rendered"]["output_size"], f"{identity}: master size mismatch")
    output_directory = root / PATHS["output"] / "web"
    output_directory.mkdir(parents=True, exist_ok=True)
    outputs, hashes = [], {}
    for edge in config["target_edges"]:
        scale = min(1, edge / max(width, height))
        size = tuple(max(1, round(dimension * scale)) for dimension in (width, height))
        resized = image if size == image.size else image.resize(size, Image.Resampling.LANCZOS)
        record = {"width": size[0], "height": size[1], "target_edge": edge}
        for format_name, options in config["formats"].items():
            buffer = BytesIO()
            resized.save(buffer, format=format_name.upper(), icc_profile=profile, **options)
            content = buffer.getvalue()
            digest = sha256(content).hexdigest()
            path = output_directory / f"{identity}-{edge}-{digest[:12]}.{format_name}"
            # A collision must fail; an existing immutable URL must never change bytes.
            if path.exists():
                require(digest_file(path) == digest, f"{path}: immutable filename collision")
            else:
                temporary = path.with_suffix(path.suffix + ".tmp")
                temporary.write_bytes(content)
                temporary.replace(path)
            file_field, bytes_field = FORMAT_FIELDS[format_name]
            record[file_field] = path.relative_to(root).as_posix()
            record[bytes_field] = len(content)
            hashes[record[file_field]] = digest
        outputs.append(record)
    saved = {"fingerprint": signature, "icc_sha256": sha256(profile).hexdigest(),
             "source_size": [width, height], "sha256": hashes, "outputs": outputs}
    validate_outputs(root, saved)
    return identity, saved, "exported"


# %% Collection export with partial-build manifest preservation
def export_collection(root=ROOT, ids=None):
    root = Path(root).resolve()
    config = json.loads((root / "images/web.json").read_text())
    require(set(config["formats"]) == set(FORMAT_FIELDS), "Configure exactly webp and avif formats")
    edges = config["target_edges"]
    require(edges == sorted(set(edges)) and edges and all(type(edge) is int and edge > 0 for edge in edges),
            "target_edges must be positive, unique, increasing integers")
    require(type(config["workers"]) is int and config["workers"] > 0, "workers must be a positive integer")
    for format_name in config["formats"]:
        require(features.check(format_name), f"Pillow requires {format_name} support")
    records = collection_artworks(root)
    require(len(records) == len({record["id"] for record in records}), "Duplicate artwork IDs")
    artworks = {record["id"]: record for record in records if record["status"] == "processed"}
    selected_ids = sorted(artworks if ids is None else ids)
    require(len(selected_ids) == len(set(selected_ids)), "Duplicate requested artwork IDs")
    require(set(selected_ids) <= set(artworks), f"Unknown or unprocessed artwork IDs: {set(selected_ids) - set(artworks)}")
    output_directory = root / PATHS["output"] / "web"
    output_directory.mkdir(parents=True, exist_ok=True)
    cache_path, manifest_path = output_directory / ".cache.json", output_directory / "manifest.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if ids is None:
        cache = {identity: saved for identity, saved in cache.items() if identity in artworks}
        manifest = {identity: variants for identity, variants in manifest.items() if identity in artworks}
    with ThreadPoolExecutor(max_workers=config["workers"]) as executor:
        results = executor.map(lambda identity: export_artwork(root, artworks[identity], config, cache), selected_ids)
        for index, (identity, saved, status) in enumerate(results, 1):
            cache[identity] = saved
            manifest[identity] = saved["outputs"]
            print(f"{index}/{len(selected_ids)} {identity}: {status}", flush=True)
    write_json(cache_path, cache)
    write_json(manifest_path, dict(sorted(manifest.items())))
    print(f"Verified {len(selected_ids)} artworks; manifest contains {len(manifest)}. {manifest_path}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--ids", nargs="+", help="Rebuild only these artwork IDs and preserve other manifest entries")
    args = parser.parse_args()
    export_collection(args.root, args.ids)


if __name__ == "__main__" and not IN_NOTEBOOK:
    main()
