"""Build an offline review gallery from the processing manifest and editable CSV."""

# %% Imports and notebook reload
from pathlib import Path
from io import BytesIO
import argparse
import csv
import json
import os
import sys

import numpy as np
from PIL import Image

from art_pipeline import embedded_jpeg, orient_pixels, source_coordinates
from image_paths import WORKSPACE_ROOT, SOURCE_ROOT, metadata_path, source_path

IN_NOTEBOOK = "ipykernel" in sys.modules
if IN_NOTEBOOK:
    from IPython import get_ipython

    ipython = get_ipython()
    ipython.run_line_magic("load_ext", "autoreload")
    ipython.run_line_magic("autoreload", "2")


# %% Gallery data and portable previews
def build_review(root):
    """Refresh the read-only index; CSV titles and notes remain user-owned."""
    root = Path(root).resolve()
    manifest = json.loads(metadata_path(root, "processing_manifest.json").read_text())
    output = root / manifest["settings"]["output_dir"]
    with metadata_path(root, "catalog.csv").open(newline="", encoding="utf-8-sig") as stream:
        annotations = {row["artwork_id"]: row for row in csv.DictReader(stream)}
    previews = output / "previews" / "sources"
    previews.mkdir(parents=True, exist_ok=True)
    cards = []
    for artwork in manifest["artworks"]:
        source = artwork["source"]
        thumbnail = previews / f"{Path(source).stem}.jpg"
        if not thumbnail.exists():
            camera_bytes, orientation = embedded_jpeg(source_path(root, source))
            with Image.open(BytesIO(camera_bytes)) as camera:
                image = Image.fromarray(orient_pixels(np.asarray(camera.convert("RGB")), orientation))
            image.thumbnail((900, 900), Image.Resampling.LANCZOS)
            image.save(thumbnail, quality=90, subsampling=0)
        record = artwork | {"annotation": annotations[artwork["id"]], "thumbnail": artwork.get("thumbnail_override", thumbnail.relative_to(output).as_posix()),
                            "camera_download": (root / artwork["original_camera_path"]).relative_to(output).as_posix(),
                            "raw_download": os.path.relpath(source_path(root, source), output)}
        if artwork["rendered"] is not None:
            result = artwork["rendered"]
            width, height = result["output_size"]
            steps = np.linspace(0, 1, 33)
            boundary = np.float32([[[value, 0] for value in steps] + [[1, value] for value in steps]
                                   + [[value, 1] for value in steps[::-1]] + [[0, value] for value in steps[::-1]]])
            rectangle = boundary * np.float32([width - 1, height - 1])
            record["crop_points"] = source_coordinates(rectangle, np.array(result["homography"]),
                                                       artwork["corners"], artwork.get("edge_midpoints"))[0].tolist()
            record["display"] = {
                key: (root / result[key]).relative_to(output).as_posix()
                for key in ["master_path", "jpeg_path", "original_camera_path", "camera_preview_path", "developed_preview_path"]
            }
            if artwork.get("previous_edit") is not None:
                record["previous_display"] = {
                    key: (root / artwork["previous_edit"][key]).relative_to(output).as_posix()
                    for key in ["jpeg_path", "master_path"]
                }
        cards.append(record)
    payload = {"source_count": manifest["source_count"], "stage": manifest["stage"], "artworks": cards,
               "archive_status": manifest["archive_status"], "archived_source_count": manifest["archived_source_count"]}
    # JSON is data inside a script element; escape '<' so user titles cannot end it.
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    template = (SOURCE_ROOT / "review_template.html").read_text()
    (output / "index.html").write_text(template.replace("__ARTWORK_DATA__", data)
                                       .replace("__CATALOG_PATH__", os.path.relpath(metadata_path(root, "catalog.csv"), output)))
    print(f"Review index: {output / 'index.html'} ({len(cards)} artwork groups)")


# %% Command-line entry point
if __name__ == "__main__" and not IN_NOTEBOOK:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=WORKSPACE_ROOT)
    build_review(parser.parse_args().root)
