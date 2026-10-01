# Photo preparation

These are the maintained photo tools. They read the external library selected by
`config/paths.json` (`library: ../images`). RAWs, recipes, editable catalogs,
approved masters, QA evidence and historical edits stay in that library, outside
this repository. No original or approved image is changed by moving these tools.

`image_paths.py` is the path contract: `REPO_ROOT` locates this checkout,
`LIBRARY_ROOT` locates the image library, and `WORKSPACE_ROOT` is its parent.
Existing manifest references such as `images/output/art-001.tif` are relative to
that workspace, not to the repository or notebook's current directory. Explicit
`--root` arguments use the same workspace convention. RAW filenames remain stable
identities resolved through `source_inventory.json`; templates come from this
directory. Keep the external library directory named `images` while using this
legacy manifest format.

Install the pinned Python environment with `uv sync --extra notebook` from the
repository. Drivers support notebook cells/autoreload and work from any current
directory when invoked by their full script path. From the repository:

```sh
# Inspect the selected RAW; explicitly edit its recipe/corners in the manifest.
.venv/bin/python tools/photos/art_pipeline.py develop DSC_8519.NEF
.venv/bin/python tools/photos/art_pipeline.py render --status processed --ids art-020

# Refresh local annotations/review, preserving intentional blanks and zeroes.
.venv/bin/python tools/photos/build_catalog.py
.venv/bin/python tools/photos/build_review.py

# Seed only new preparation-catalog rows; existing rows remain user-owned.
.venv/bin/python tools/photos/build_website_catalog.py

# Export only the changed piece; other web manifest entries stay intact.
.venv/bin/python tools/photos/export_web_images.py --ids art-020

# Bring new artwork IDs into the local editor without replacing existing rows.
.venv/bin/python tools/photos/import_editor_catalog.py --dry-run
.venv/bin/python tools/photos/import_editor_catalog.py
```

In Jupyter, load a driver with `%run -i /path/to/personal_site/tools/photos/art_pipeline.py`
before using its functions in cells. The notebook guard skips its CLI and enables
autoreload; this also puts its sibling modules on the import path without relying
on the notebook's current directory.

The Python CSV builders use only the standard library. They replace the former
Codex-dependent JavaScript catalog drivers; spreadsheet preview rendering is no
longer part of a CSV refresh. Website/editor build and serving commands are in the
repository README. The editor's SQLite overrides remain authoritative for later
website edits; refreshing a preparation CSV does not import over them.
The editor import appends new IDs only, preserves seed records and SQLite edits,
and copies incomplete pieces' reference photos into private `.local/reference-photos`.
Unknown/deleted IDs fail with a reconciliation request instead of disappearing.

## New photographs

1. Preserve each new NEF under `images/raw/` with a unique filename. Register its
   filename, byte count, SHA-256 and workspace-relative `current_path` in
   `images/metadata/source_inventory.json`; never overwrite another capture.
2. Add it to the intended artwork's `sources` in `processing_manifest.json`, or
   create a new stable artwork ID and explicit metadata record. Update
   `source_count` and `source_locations`. Keep old captures in the inventory.
   For a new ID, add its description/theme to `website-art-metadata.json` too.
3. Develop the selected source, record its corners/geometry and quality review,
   and explicitly approve the processing recipe/status before rendering that ID.
   Coordinates refer to oriented developed RAW pixels, not the camera JPEG.
4. Review the result, refresh the catalogs, export that ID's web copies, then run
   `import_editor_catalog.py` and the repository's website build. Existing seed
   rows remain unchanged. Physical measurements and publication stay explicit.

Before revising an approved edit, preserve its master, JPEG and recipe in a named
`images/output/revisions/` snapshot with checksums. Web exports retain hashed local
history; the website build selects only current variants for public delivery.

```sh
.venv/bin/python -m unittest discover -s tests/photos -v
.venv/bin/python tools/photos/finalize_collection.py verify
```

Tests use small temporary fixtures. The full verifier reads the collection and
refreshes its audit report; neither operation rerenders the collection.

## Previous-website photographs

`images/imports/nfs-20261001/site/` is an untouched download of the old public site,
including unlinked photographs and professional-site assets. `inventory.json`
records every file's original path, byte count and SHA-256. A checksum comparison
against NFS also verified the download. This archive stays outside Git and is
never included wholesale in a deployment.

`decisions.json` groups alternative captures and detail crops under one artwork
ID, records the preferred source and explains the visual choice. Existing IDs and
owner-authored metadata survive. New works use new IDs; previously hidden works
remain drafts. Similar subjects alone do not establish a duplicate.

```sh
.venv/bin/python tools/photos/register_website_import.py ../images/imports/nfs-20261001/decisions.json
.venv/bin/python tools/photos/export_web_images.py
.venv/bin/python tools/photos/import_editor_catalog.py --dry-run
.venv/bin/python tools/photos/import_editor_catalog.py
.venv/bin/python tools/photos/build_import_review.py ../images/imports/nfs-20261001/decisions.json
```

Registration writes `images/metadata/imported_artworks.json`. Its additions and
explicit delivery replacements are joined with the RAW manifest by
`collection_sources.py`; a full web export includes both. The RAW manifest,
masters and historic quality audit remain unchanged. RAW-only catalog/review/audit
commands still describe the camera collection; the editor and website catalogs
include the imports too. To choose the RAW version again, set the existing work's
`selected` to `null` in the decisions file, register, and re-export that ID.

JPEG imports retain their original pixels and framing: honor EXIF orientation,
convert tagged color to sRGB (interpret untagged web JPEGs as sRGB), apply only an
explicit reviewed quarter-turn if present, then downsize and encode AVIF/WebP.
Do not apply RAW exposure, saturation or contrast settings to these finished
photographs. No upscaling, sharpening or generative retouching is performed.

The generated `review.html` is a self-contained local comparison with links to
full originals. Review it in a local browser. The editor's explicit publish flag
wins even for finished photos needing review; export does not publish drafts.
Broad media and descriptive titles are provisional; unknown measurements, dates,
prices and availability stay blank until the owner supplies them.
