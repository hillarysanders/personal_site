"""Append newly prepared artwork IDs to the private editor seed; preserve existing edits."""

# %% Imports and notebook reload
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlparse

from collection_sources import collection_artworks
from build_catalog import index_rows, number_cell, read_csv
from build_website_catalog import COLUMNS
from image_paths import PATHS, REPO_ROOT, WORKSPACE_ROOT, metadata_path

IN_NOTEBOOK = "ipykernel" in sys.modules
if IN_NOTEBOOK:
    from IPython import get_ipython
    ipython = get_ipython()
    ipython.run_line_magic("load_ext", "autoreload")
    ipython.run_line_magic("autoreload", "2")


# %% Validate new records using the editor's field names and preparation rules
def editor_record(row, source, variants, config):
    identity = row["artwork_id"]
    if re.fullmatch(r"art-\d+", identity) is None:
        raise ValueError(f"{identity}: expected a stable art-NNN identity")
    for field in ["publish", "dimensions_confirmed"]:
        if row[field] not in {"yes", "no"}:
            raise ValueError(f"{identity}: {field} must be yes or no")
    if row["availability"] not in {"", "available", "private", "sold"}:
        raise ValueError(f"{identity}: invalid availability")
    if row["size_category"] not in {"Small", "Medium", "Large", "Unclassified"}:
        raise ValueError(f"{identity}: invalid size category")
    width, height = [number_cell(row[field], field, identity) for field in ["width_in", "height_in"]]
    if (width is None) != (height is None) or any(value is not None and value <= 0 for value in [width, height]):
        raise ValueError(f"{identity}: enter both positive dimensions or leave both blank")
    if row["dimensions_confirmed"] == "yes" and width is None:
        raise ValueError(f"{identity}: confirmed dimensions are missing")
    price = number_cell(row["price"], "price", identity)
    order = number_cell(row["display_order"], "display_order", identity)
    if price is not None and price < 0 or type(order) is not int or order < 0:
        raise ValueError(f"{identity}: price must be nonnegative and display_order a nonnegative integer")
    if re.fullmatch(r"[A-Za-z]{3}", row["currency"]) is None:
        raise ValueError(f"{identity}: currency must be a three-letter code")
    if row["purchase_url"]:
        parsed = urlparse(row["purchase_url"])
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or row["availability"] != "available":
            raise ValueError(f"{identity}: checkout needs an HTTPS URL and available status")
    if not variants and row["publish"] == "yes":
        raise ValueError(f"{identity}: a published artwork needs finished web images")
    themes = [config["category_aliases"].get(theme, theme) for theme in row["theme"].split("; ")] if row["theme"] else []
    series = [{"seriesId": group["id"], "seriesTitle": group["title"], "seriesPosition": group["members"].index(identity)}
              for group in config["artwork_series"] if identity in group["members"]]
    if len(series) > 1:
        raise ValueError(f"{identity}: artwork belongs to more than one configured series")
    limits = config["size_limits"]
    return {
        "id": identity, "title": row["title"], "description": row["description"],
        "theme": themes[0] if themes else "", "themes": themes, "period": row["period"], "year": row["year"],
        "medium": row["medium"], "surface": "", "width": width, "height": height,
        "dimensionsConfirmed": row["dimensions_confirmed"] == "yes",
        "sizeCategory": row["size_category"] if width is None else "Small" if max(width, height) < limits["small_under_in"] else "Medium" if max(width, height) <= limits["medium_up_to_in"] else "Large",
        "price": price, "currency": row["currency"].upper(), "availability": row["availability"],
        "purchaseUrl": row["purchase_url"], "order": order,
        "images": [{"src": "assets/" + Path(image["file"]).name, "avif": "assets/" + Path(image["avif_file"]).name,
                    "width": image["width"], "height": image["height"], "edge": image["target_edge"]} for image in variants],
        "referenceImage": None if variants else f"admin-photos/{identity}.jpg",
        "published": row["publish"] == "yes",
        "photoStatus": "ready" if row["image_quality"] == "acceptable" else "needs_photo" if row["needs_reshoot"] == "yes" or not variants else "review",
        "notes": row["website_notes"], "qualityNotes": source["quality_notes"], "issues": source["issues"], "revision": 0,
        **(series[0] if series else {"seriesId": "", "seriesTitle": "", "seriesPosition": 0}),
    }


# %% Append only; deletions, remappings and existing edits require explicit reconciliation
def import_editor_catalog(repo=REPO_ROOT, root=WORKSPACE_ROOT, dry_run=False):
    repo, root = Path(repo).resolve(), Path(root).resolve()
    paths = json.loads((repo / "config/paths.json").read_text())
    local = repo / paths["local"]
    seed_path = local / "catalog-seed.json"
    seed = json.loads(seed_path.read_text())
    existing = index_rows(seed["artworks"], "id")
    config = json.loads((repo / "config/site.json").read_text())
    if type(config["include_review_photos"]) is not bool:
        raise ValueError("include_review_photos must be true or false")
    sources = index_rows(collection_artworks(root), "id")
    rows = read_csv(metadata_path(root, "website_catalog.csv"), [COLUMNS])
    images = json.loads((root / PATHS["output"] / "web/manifest.json").read_text())
    if rows.keys() != sources.keys():
        raise ValueError("Preparation CSV and processing manifest IDs differ; reconcile explicitly")
    unknown = (existing.keys() | images.keys()) - sources.keys()
    if unknown:
        raise ValueError(f"Unknown/deleted artwork IDs require explicit reconciliation: {sorted(unknown)}")
    additions, references = [], []
    for identity, row in rows.items():
        if identity in existing:
            continue
        source = sources[identity]
        variants = images[identity] if source["rendered"] is not None else []
        if source["rendered"] is not None and not variants:
            raise ValueError(f"{identity}: export finished web images before importing")
        for image in variants:
            for field in ["file", "avif_file"]:
                if not (root / image[field]).is_file():
                    raise FileNotFoundError(root / image[field])
        additions.append(editor_record(row, source, variants, config))
        if not variants:
            preview = root / PATHS["output"] / (source["thumbnail_override"] if "thumbnail_override" in source else f"previews/sources/{Path(source['source']).stem}.jpg")
            destination = local / "reference-photos" / f"{identity}.jpg"
            if not preview.is_file():
                raise FileNotFoundError(preview)
            if destination.exists():
                raise FileExistsError(f"Existing reference photo requires reconciliation: {destination}")
            references.append((preview, destination))
    if additions and not dry_run:
        for preview, destination in references:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(preview, destination)
        seed["artworks"].extend(additions)
        temporary = seed_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n")
        temporary.replace(seed_path)
    return [record["id"] for record in additions]


# %% Command-line entry
if __name__ == "__main__" and not IN_NOTEBOOK:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=WORKSPACE_ROOT, help="Workspace parent containing images/")
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--dry-run", action="store_true", help="List new IDs and validate sources without writing")
    args = parser.parse_args()
    added = import_editor_catalog(args.repo, args.root, args.dry_run)
    print(f"{'Would import' if args.dry_run else 'Imported'} {len(added)} new artwork IDs: {', '.join(added) or '(none)'}")
