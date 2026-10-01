"""Refresh generated CSV references while preserving annotations by artwork ID."""

# %% Imports and notebook reload
import argparse
import csv
import json
import math
from pathlib import Path
import re
import sys

from image_paths import WORKSPACE_ROOT, metadata_path

IN_NOTEBOOK = "ipykernel" in sys.modules
if IN_NOTEBOOK:
    from IPython import get_ipython
    ipython = get_ipython()
    ipython.run_line_magic("load_ext", "autoreload")
    ipython.run_line_magic("autoreload", "2")

LEGACY_COLUMNS = "artwork_id title status selected_source alternate_sources estimated_ratio proportion ratio_confidence working_width_in working_height_in dimension_basis dimension_confidence confirmed_width_in confirmed_height_in original_raw original_camera_jpeg edited_tiff website_jpeg selection_notes review_notes".split()
QUALITY_COLUMNS = "image_quality needs_reshoot quality_notes".split()
COLUMNS = LEGACY_COLUMNS + QUALITY_COLUMNS
ANNOTATIONS = "title estimated_ratio proportion ratio_confidence working_width_in working_height_in dimension_basis dimension_confidence confirmed_width_in confirmed_height_in review_notes".split() + QUALITY_COLUMNS
NUMBERS = set("estimated_ratio working_width_in working_height_in confirmed_width_in confirmed_height_in".split())
NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


# %% Strict CSV input and stable numeric output
def text(value):
    if type(value) is float and value.is_integer():
        return str(int(value))
    return "" if value is None else str(value)


def number_cell(value, field, identity):
    if value is None or value == "":
        return None
    if type(value) in (int, float) or isinstance(value, str) and NUMBER.fullmatch(value):
        number = float(value)
        if math.isfinite(number):
            return int(number) if number.is_integer() else number
    raise ValueError(f"{identity}: {field} must be a finite number or blank, received {value!r}")


def index_rows(rows, field):
    indexed = {}
    for row in rows:
        identity = row[field]
        if not identity or identity in indexed:
            raise ValueError(f"Missing or duplicate {field}: {identity!r}")
        indexed[identity] = row
    return indexed


def read_csv(path, schemas):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames) or set(reader.fieldnames) not in [set(schema) for schema in schemas]:
            raise ValueError(f"Unexpected CSV columns: {path}")
        rows = []
        for row in reader:
            if None in row or None in row.values():
                raise ValueError(f"Malformed CSV row in {path}")
            if any(row.values()):
                rows.append(row)
    return index_rows(rows, "artwork_id")


def write_csv(path, columns, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


# %% Merge generated references with intentional user edits
def generated_row(root, artwork, locations):
    rendered = artwork["rendered"]
    relative = lambda filename: (root / filename).resolve().relative_to(root).as_posix()
    return {
        "artwork_id": artwork["id"], "title": artwork["label"], "status": artwork["status"],
        "selected_source": artwork["source"],
        "alternate_sources": "; ".join(source for source in artwork["sources"] if source != artwork["source"]),
        "estimated_ratio": artwork["aspect_ratio"], "proportion": artwork["proportion"],
        "ratio_confidence": artwork["ratio_confidence"], "working_width_in": artwork["working_width_in"],
        "working_height_in": artwork["working_height_in"], "dimension_basis": artwork["dimension_basis"],
        "dimension_confidence": artwork["dimension_confidence"],
        "confirmed_width_in": artwork.get("confirmed_width_in"), "confirmed_height_in": artwork.get("confirmed_height_in"),
        "original_raw": relative(locations[artwork["source"]]),
        "original_camera_jpeg": relative(artwork["original_camera_path"]),
        "edited_tiff": "" if rendered is None else relative(rendered["master_path"]),
        "website_jpeg": "" if rendered is None else relative(rendered["jpeg_path"]),
        "selection_notes": artwork["selection_reason"], "review_notes": "; ".join(artwork["issues"]),
        **{field: artwork[field] for field in QUALITY_COLUMNS},
    }


def build_catalog(root=WORKSPACE_ROOT, quiet=False):
    root = Path(root).resolve()
    manifest = json.loads(metadata_path(root, "processing_manifest.json").read_text())
    artworks = index_rows(manifest["artworks"], "id")
    inventory = json.loads(metadata_path(root, "source_inventory.json").read_text())
    locations = {entry["filename"]: entry["current_path"] for entry in inventory["files"]}
    filename = metadata_path(root, "catalog.csv")
    baseline_path = metadata_path(root, "catalog-generated.json")
    existing = read_csv(filename, [LEGACY_COLUMNS, COLUMNS]) if filename.exists() else {}
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    removed = existing.keys() - artworks.keys()
    if removed:
        raise ValueError(f"CSV artworks absent from manifest: {sorted(removed)}")
    generated, rows = {}, []
    for artwork in manifest["artworks"]:
        identity = artwork["id"]
        row = generated_row(root, artwork, locations)
        generated[identity] = {field: row[field] for field in ANNOTATIONS}
        manual = set(baseline[identity].get("__manual_fields", [])) if identity in baseline else set()
        if identity in existing:
            previous = existing[identity]
            for field in ANNOTATIONS:
                if field not in previous:  # A legacy 20-column CSV has no quality annotations.
                    continue
                if identity not in baseline or text(previous[field]) != text(baseline[identity].get(field)):
                    manual.add(field)
                if field in manual:
                    row[field] = previous[field]
        generated[identity]["__manual_fields"] = sorted(manual)
        rows.append({field: number_cell(row[field], field, identity) if field in NUMBERS else row[field] for field in COLUMNS})
    # Remember an override even when it later happens to equal a generated value.
    write_csv(filename, COLUMNS, rows)
    baseline_path.write_text(json.dumps(generated, indent=2, ensure_ascii=False) + "\n")
    if not quiet:
        print(f"Refreshed {len(rows)} catalog records: {filename}")
    return filename


# %% Command-line entry
if __name__ == "__main__" and not IN_NOTEBOOK:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=WORKSPACE_ROOT, help="Workspace parent containing images/")
    build_catalog(parser.parse_args().root)
