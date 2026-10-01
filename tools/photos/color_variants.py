"""Build five reversible sample treatments and their local comparison page.

Only the configured sample artworks are rendered. Existing deliverables, CSV,
original files and the processing manifest are never modified by this driver.
"""

# %% Imports and notebook reload
from pathlib import Path
import argparse
import csv
import hashlib
import json
import sys

import cv2
import numpy as np
import tifffile

from art_pipeline import adjusted_linear, develop_raw, linear_to_srgb, rectification, save_jpeg, srgb_profile
from image_paths import WORKSPACE_ROOT, SOURCE_ROOT, metadata_path

IN_NOTEBOOK = "ipykernel" in sys.modules
if IN_NOTEBOOK:
    from IPython import get_ipython

    ipython = get_ipython()
    ipython.run_line_magic("load_ext", "autoreload")
    ipython.run_line_magic("autoreload", "2")


# %% Configuration-driven sample exports
def build_variants(root):
    root = Path(root).resolve()
    config = json.loads(metadata_path(root, "color_review.json").read_text())
    manifest = json.loads(metadata_path(root, "processing_manifest.json").read_text())
    artworks = {artwork["id"]: artwork for artwork in manifest["artworks"]}
    output = root / manifest["settings"]["output_dir"]
    destination = root / config["output_dir"]
    destination.mkdir(parents=True, exist_ok=True)
    with metadata_path(root, "catalog.csv").open(newline="", encoding="utf-8-sig") as stream:
        annotations = {row["artwork_id"]: row for row in csv.DictReader(stream)}
    if len(config["versions"]) != 5 or len({version["id"] for version in config["versions"]}) != 5:
        raise ValueError("The review requires exactly five uniquely identified versions")

    profile = srgb_profile()
    inventory = {entry["filename"]: entry for entry in json.loads(metadata_path(root, "source_inventory.json").read_text())["files"]}
    payload = {"series_id": config["series_id"], "config": config,
               "recipe_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
               "source_manifest_sha256": hashlib.sha256(metadata_path(root, "processing_manifest.json").read_bytes()).hexdigest(), "artworks": []}
    verification = []
    for sample in config["artworks"]:
        artwork = artworks[sample["id"]]
        row = annotations[artwork["id"]]
        development = develop_raw(root, artwork["source"], manifest["settings"])
        transform, size = rectification(artwork["corners"], artwork["aspect_ratio"], artwork["inset_px"], development["source_size"])
        if list(size) != artwork["rendered"]["output_size"] or not np.array_equal(transform, artwork["rendered"]["homography"]):
            raise ValueError(f"{artwork['id']}: geometry differs from the approved crop")
        linear = np.load(development["linear_path"], mmap_mode="r")
        cropped = cv2.warpPerspective(linear, transform, size, flags=cv2.INTER_LINEAR)
        directory = destination / artwork["id"]
        directory.mkdir(exist_ok=True)
        confirmed = row["confirmed_width_in"] and row["confirmed_height_in"]
        dimensions = f"{row['confirmed_width_in']} × {row['confirmed_height_in']} in · confirmed" if confirmed else f"{row['proportion']} · physical size unconfirmed"
        card = {"id": artwork["id"], "title": row["title"], "dimensions": dimensions,
                "source": artwork["source"], "source_sha256": inventory[artwork["source"]]["sha256"],
                "corners": artwork["corners"], "homography": transform.tolist(), "source_size": development["source_size"],
                "camera_preview_path": (root / artwork["rendered"]["camera_preview_path"]).relative_to(output).as_posix(), "variants": []}
        for version in config["versions"]:
            recipe = {"exposure_ev": round(sample["base_exposure_ev"] + version["exposure_delta_ev"], 3),
                      "saturation": version["saturation"], "contrast": version["contrast"], "contrast_pivot": config["contrast_pivot"]}
            adjusted = adjusted_linear(cropped, **recipe)
            encoded = linear_to_srgb(adjusted)
            master_pixels = np.rint(encoded * 65535).astype(np.uint16)
            web_pixels = np.rint(encoded * 255).astype(np.uint8)
            paths = {"master_path": directory / f"{version['id']}.tif", "jpeg_path": directory / f"{version['id']}.jpg",
                     "preview_path": directory / f"{version['id']}-preview.jpg"}
            if version["number"] == 1:
                # The comparison keeps its frozen pre-V3 anchor after rollout.
                baseline = root / config["baseline_master_dir"] / f"{artwork['id']}.tif"
                if not np.array_equal(master_pixels, tifffile.imread(baseline)):
                    raise ValueError(f"{artwork['id']}: V1 no longer matches the preserved comparison baseline")
            tifffile.imwrite(paths["master_path"], master_pixels, photometric="rgb", compression="deflate", iccprofile=profile, metadata=None)
            jpeg_size = save_jpeg(paths["jpeg_path"], web_pixels, manifest["settings"]["jpeg_max_edge"], manifest["settings"]["jpeg_quality"], profile)
            save_jpeg(paths["preview_path"], web_pixels, config["preview_max_edge"], 95, profile)
            display = {key: path.relative_to(output).as_posix() for key, path in paths.items()}
            card["variants"].append(version | recipe | display)

            # Inspect native pixels; aggregate lightness/chroma compare the ladder.
            luminance = encoded @ np.float32([.2126, .7152, .0722])
            lab = cv2.cvtColor(encoded[::4, ::4], cv2.COLOR_RGB2LAB)
            record = {"artwork_id": artwork["id"], "version": version["id"], "recipe": recipe, "output_size": list(size),
                      "jpeg_size": jpeg_size, "luminance_percentiles": np.percentile(luminance, [1, 5, 50, 95, 99]).tolist(),
                      "mean_chroma": float(np.linalg.norm(lab[..., 1:], axis=-1).mean()),
                      "above_gamut_pixel_percent": float(np.any(adjusted > 1, axis=-1).mean() * 100),
                      "below_gamut_pixel_percent": float(np.any(adjusted < 0, axis=-1).mean() * 100),
                      "master_sha256": hashlib.sha256(paths["master_path"].read_bytes()).hexdigest()}
            verification.append(record)
            print(f"{artwork['id']} {version['id']}: {size[0]}×{size[1]} TIFF + JPEG", flush=True)
        payload["artworks"].append(card)

    # Record every setting beside the exports, independent of transient caches.
    (destination / "review.json").write_text(json.dumps(payload, indent=2) + "\n")
    (destination / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    template = (SOURCE_ROOT / "color_review_template.html").read_text()
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    (output / "color-review.html").write_text(template.replace("__COLOR_REVIEW_DATA__", data))
    print(f"Review: {output / 'color-review.html'}")


# %% Command-line entry point
if __name__ == "__main__" and not IN_NOTEBOOK:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=WORKSPACE_ROOT)
    build_variants(parser.parse_args().root)
