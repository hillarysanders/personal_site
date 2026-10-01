"""Resolve the external image library independently of a shell/notebook directory.

Existing metadata paths use the library's parent workspace (``images/...``).
``root`` arguments retain that convention; no manifest rewrite is required.
"""
from pathlib import Path
import json

SOURCE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SOURCE_ROOT.parents[1]
CONFIG = json.loads((REPO_ROOT / "config/paths.json").read_text())
LIBRARY_ROOT = (REPO_ROOT / CONFIG["library"]).resolve()
WORKSPACE_ROOT = LIBRARY_ROOT.parent
PATHS = json.loads((LIBRARY_ROOT / "paths.json").read_text())


def metadata_path(root, filename):
    return Path(root) / PATHS["metadata"] / filename


def source_path(root, filename):
    """Resolve an inventoried camera filename without guessing alternate locations."""
    inventory = json.loads(metadata_path(root, "source_inventory.json").read_text())
    locations = {entry["filename"]: entry["current_path"] for entry in inventory["files"]}
    return Path(root) / locations[filename]
