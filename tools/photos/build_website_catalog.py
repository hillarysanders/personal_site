"""Seed new website CSV rows; preserve every existing cell, including blanks."""

# %% Imports and notebook reload
import argparse
import json
from pathlib import Path
import sys

from collection_sources import collection_artworks
from build_catalog import read_csv, write_csv, index_rows
from image_paths import REPO_ROOT, WORKSPACE_ROOT, metadata_path

IN_NOTEBOOK = "ipykernel" in sys.modules
if IN_NOTEBOOK:
    from IPython import get_ipython
    ipython = get_ipython()
    ipython.run_line_magic("load_ext", "autoreload")
    ipython.run_line_magic("autoreload", "2")

COLUMNS = "artwork_id title description theme period year medium width_in height_in dimensions_confirmed size_category price currency availability publish display_order purchase_url website_notes image_quality needs_reshoot dimension_basis".split()
PRIORITY = ["art-019", "art-036", "art-013", "art-001", "art-041", "art-020", "art-065", "art-053"]


# %% Preparation metadata only; the editor database keeps its own later edits
def build_website_catalog(root=WORKSPACE_ROOT, site_config=REPO_ROOT / "config/site.json", quiet=False):
    root = Path(root).resolve()
    filename = metadata_path(root, "website_catalog.csv")
    manifest = {"artworks": collection_artworks(root)}
    artworks = index_rows(manifest["artworks"], "id")
    curation = json.loads(metadata_path(root, "website-art-metadata.json").read_text())
    config = json.loads(Path(site_config).read_text())
    existing = read_csv(filename, [COLUMNS]) if filename.exists() else {}
    removed = existing.keys() - artworks.keys()
    if removed:
        raise ValueError(f"Website CSV artworks absent from manifest: {sorted(removed)}")
    rows = []
    for index, artwork in enumerate(manifest["artworks"]):
        identity = artwork["id"]
        if identity in existing:
            rows.append(existing[identity])
            continue
        measured = bool(artwork.get("confirmed_width_in") and artwork.get("confirmed_height_in"))
        category = "user-provided category size" in artwork["dimension_basis"].lower()
        longest = max(artwork["working_width_in"] or 0, artwork["working_height_in"] or 0)
        rows.append({
            "artwork_id": identity, "title": artwork["label"], "description": curation[identity]["description"],
            "theme": curation[identity]["theme"], "period": "", "year": "", "medium": "",
            "width_in": artwork["confirmed_width_in"] if measured else artwork["working_width_in"] if category else "",
            "height_in": artwork["confirmed_height_in"] if measured else artwork["working_height_in"] if category else "",
            "dimensions_confirmed": "yes" if measured else "no",
            "size_category": "Unclassified" if longest == 0 else "Small" if longest < config["size_limits"]["small_under_in"] else "Medium" if longest <= config["size_limits"]["medium_up_to_in"] else "Large",
            "price": "", "currency": config["currency"], "availability": "",
            "publish": "yes" if artwork["rendered"] and (config["default_quality"] == "all_finished" or artwork["image_quality"] == "acceptable") else "no",
            "display_order": PRIORITY.index(identity) + 1 if identity in PRIORITY else 100 + index,
            "purchase_url": "",
            "website_notes": "" if measured else "Category size from owner; confirm this piece before selling." if category else "Precise dimensions withheld until measured; size category provisional.",
            **{field: artwork[field] for field in ["image_quality", "needs_reshoot", "dimension_basis"]},
        })
    write_csv(filename, COLUMNS, rows)
    if not quiet:
        print(f"Prepared {len(rows)} website records; retained {len(existing)} existing rows: {filename}")
    return filename


# %% Command-line entry
if __name__ == "__main__" and not IN_NOTEBOOK:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=WORKSPACE_ROOT, help="Workspace parent containing images/")
    parser.add_argument("--site-config", type=Path, default=REPO_ROOT / "config/site.json")
    args = parser.parse_args()
    build_website_catalog(args.root, args.site_config)
