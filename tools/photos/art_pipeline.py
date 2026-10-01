"""Faithful RAW development and reproducible four-corner artwork exports.

Corners are TL, TR, BR, BL pixels in the *oriented developed RAW*. Camera JPEGs
are separate references: their crop, distortion correction and tone can differ.
"""

# %% Imports and interactive reload
from pathlib import Path
from io import BytesIO
import argparse
import json
import shutil
import sys

import cv2
import numpy as np
import rawpy
import tifffile
from PIL import Image, ImageCms, TiffImagePlugin
from image_paths import WORKSPACE_ROOT, PATHS, source_path

IN_NOTEBOOK = "ipykernel" in sys.modules
if IN_NOTEBOOK:
    from IPython import get_ipython

    ipython = get_ipython()
    ipython.run_line_magic("load_ext", "autoreload")
    ipython.run_line_magic("autoreload", "2")

DEFAULT_SETTINGS = {
    "cache_dir": ".cache/art",
    "output_dir": PATHS["output"],
    "jpeg_max_edge": 3000,
    "jpeg_quality": 95,
    "preview_max_edge": 1800,
    "inset_px": 1.0,
}
RAW_RECIPE = {
    "version": 1,
    "white_balance": "camera",
    "brightness": "fixed, no automatic brightening",
    "color_space": "linear sRGB then explicit sRGB transfer",
    "demosaic": "AHD",
    "lens_correction": "none",
}


# %% Camera previews and orientation
def orient_pixels(pixels, orientation):
    """Apply EXIF orientation once, identically for RGB16 and RGB8 arrays."""
    transforms = {
        1: lambda image: image,
        2: np.fliplr,
        3: lambda image: np.rot90(image, 2),
        4: np.flipud,
        5: lambda image: image.swapaxes(0, 1),
        6: lambda image: np.rot90(image, 3),
        7: lambda image: np.rot90(image, 2).swapaxes(0, 1),
        8: lambda image: np.rot90(image, 1),
    }
    return np.ascontiguousarray(transforms[orientation](pixels))


def embedded_jpeg(source):
    """Return the largest embedded JPEG's exact bytes and TIFF orientation."""
    previews = []
    with Path(source).open("rb") as stream:
        header = stream.read(8)
        container = Image.open(stream)
        orientation = int(container.getexif()[274])
        offsets = container.tag_v2[330]
        for offset in offsets:
            stream.seek(offset)
            directory = TiffImagePlugin.ImageFileDirectory_v2(ifh=header)
            directory.load(stream)
            if 513 in directory:
                stream.seek(directory[513])
                jpeg = stream.read(directory[514])
                with Image.open(BytesIO(jpeg)) as preview:
                    previews.append((preview.width * preview.height, jpeg))
    return max(previews, key=lambda candidate: candidate[0])[1], orientation


def srgb_profile():
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def linear_to_srgb(linear):
    """Encode linear [0, 1] sRGB using its specified piecewise transfer."""
    linear = np.clip(linear, 0.0, 1.0)
    return np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055,
    )


def srgb_to_linear(encoded):
    """Decode sRGB values using the inverse of the display transfer."""
    return np.where(encoded <= 0.04045, encoded / 12.92, ((encoded + 0.055) / 1.055) ** 2.4)


def tone_luminance(luminance, contrast, pivot):
    """Bounded S-curve in display lightness; endpoints and pivot stay fixed.

    Contrast is the exponent on odds around the pivot: 1 is identity. Values
    outside the display range bypass the curve, leaving clipping to export.
    """
    lightness = linear_to_srgb(luminance)
    numerator = lightness ** contrast
    denominator = numerator + (1 - lightness) ** contrast * (pivot / (1 - pivot)) ** (contrast - 1)
    mapped = srgb_to_linear(numerator / denominator)
    return np.where((luminance > 0) & (luminance < 1), mapped, luminance)


def adjusted_linear(linear16, exposure_ev=0.0, saturation=1.0, contrast=1.0, contrast_pivot=0.35):
    """Apply recorded exposure, color strength and optional global contrast.

    Saturation scales linear RGB distance from Rec.709 luminance, retaining
    neutral colors. Contrast scales RGB together to preserve chromaticity;
    it has no hard shadow threshold, white-balance shift or local adjustment.
    """
    if not np.isfinite([exposure_ev, saturation, contrast, contrast_pivot]).all() or saturation < 0 or contrast <= 0 or not 0 < contrast_pivot < 1:
        raise ValueError("settings must be finite; saturation nonnegative, contrast positive, pivot between 0 and 1")
    linear = linear16.astype(np.float32) * (2.0 ** exposure_ev / 65535.0)
    if saturation != 1.0 or contrast != 1.0:
        luminance = (linear @ np.float32([0.2126, 0.7152, 0.0722]))[..., None]
    if saturation != 1.0:
        linear = luminance + saturation * (linear - luminance)
    if contrast != 1.0:
        target = tone_luminance(luminance, contrast, contrast_pivot)
        linear *= np.divide(target, luminance, out=np.ones_like(luminance), where=luminance > 0)
    return linear


def encoded_pixels(linear16, exposure_ev=0.0, bits=16, saturation=1.0, contrast=1.0, contrast_pivot=0.35):
    """Encode the recorded linear-light recipe as RGB8 or RGB16 sRGB."""
    linear = adjusted_linear(linear16, exposure_ev, saturation, contrast, contrast_pivot)
    encoded = np.rint(linear_to_srgb(linear) * (2**bits - 1))
    return encoded.astype({8: np.uint8, 16: np.uint16}[bits])


def save_jpeg(path, pixels, max_edge, quality, profile):
    """Save a display-ready RGB JPEG; thumbnail never enlarges the source."""
    image = Image.fromarray(pixels)
    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    image.save(path, quality=quality, subsampling=0, icc_profile=profile)
    return list(image.size)


# %% RAW development cache (original NEFs are read only)
def develop_raw(root, source, settings=None):
    """Cache oriented linear RGB16 plus full-size camera/developed previews.

    Returned source_size is the coordinate system for all corner annotations.
    No lens profile or camera JPEG coordinates are silently reused for the RAW.
    """
    root = Path(root).resolve()
    config = DEFAULT_SETTINGS | (settings or {})
    raw_path = source_path(root, source)
    cache = root / config["cache_dir"] / raw_path.stem
    cache.mkdir(parents=True, exist_ok=True)
    metadata_path = cache / "development.json"
    source_stat = raw_path.stat()
    fingerprint = {
        "source_size_bytes": source_stat.st_size,
        "source_mtime_ns": source_stat.st_mtime_ns,
        "recipe": RAW_RECIPE,
        "rawpy_version": rawpy.__version__,
    }
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
        if metadata["fingerprint"] == fingerprint:
            return metadata

    camera_bytes, orientation = embedded_jpeg(raw_path)
    camera_path = cache / "camera-embedded.jpg"
    camera_path.write_bytes(camera_bytes)
    with Image.open(BytesIO(camera_bytes)) as camera:
        camera_pixels = orient_pixels(np.asarray(camera.convert("RGB")), orientation)

    # Decode without implicit rotation, automatic exposure, or a display gamma.
    # Standard sensor normalization remains enabled; WB comes from the NEF.
    with rawpy.imread(str(raw_path)) as raw:
        linear = raw.postprocess(
            use_camera_wb=True,
            use_auto_wb=False,
            no_auto_bright=True,
            adjust_maximum_thr=0.0,
            bright=1.0,
            exp_shift=1.0,
            gamma=(1.0, 1.0),
            output_bps=16,
            output_color=rawpy.ColorSpace.sRGB,
            demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
            highlight_mode=rawpy.HighlightMode.Clip,
            user_flip=0,
        )
    linear = orient_pixels(linear, orientation)
    linear_path = cache / "linear-srgb16.npy"
    np.save(linear_path, linear)
    profile = srgb_profile()
    preview_path = cache / "developed.jpg"
    camera_preview_path = cache / "camera-oriented.jpg"
    source_size = [linear.shape[1], linear.shape[0]]
    save_jpeg(preview_path, encoded_pixels(linear, bits=8), max(source_size), 95, profile)
    save_jpeg(camera_preview_path, camera_pixels, max(camera_pixels.shape[:2]), 95, profile)
    metadata = {
        "source": source,
        "source_size": source_size,
        "camera_orientation": orientation,
        "camera_size": [camera_pixels.shape[1], camera_pixels.shape[0]],
        "linear_path": str(linear_path),
        "preview_path": str(preview_path),
        "camera_embedded_path": str(camera_path),
        "camera_preview_path": str(camera_preview_path),
        "fingerprint": fingerprint,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


# %% Perspective correction and exports
def rectification(corners, aspect_ratio, inset_px, source_size):
    """Return homography and conservative output size for ordered corners.

    inset_px is measured on the shorter rectified edge; the same fractional
    inset on both axes preserves the requested proportions. Geometry and inset
    are composed before resampling. Opposing shorter edges bound native scale.
    """
    corners = np.asarray(corners, dtype=np.float32)
    if corners.shape != (4, 2) or not np.isfinite(corners).all():
        raise ValueError("corners must contain four finite [x, y] pairs")
    if aspect_ratio <= 0 or not np.isfinite(aspect_ratio) or inset_px < 0:
        raise ValueError("aspect_ratio must be positive and inset_px nonnegative")
    if np.any(corners < 0) or np.any(corners > np.asarray(source_size) - 1):
        raise ValueError("corners lie outside the oriented RAW image")
    edges = np.roll(corners, -1, axis=0) - corners
    next_edges = np.roll(edges, -1, axis=0)
    turns = edges[:, 0] * next_edges[:, 1] - edges[:, 1] * next_edges[:, 0]
    if np.any(turns <= 0):
        raise ValueError("corners must be convex and ordered TL, TR, BR, BL")
    lengths = np.linalg.norm(edges, axis=1)
    native_height = min(lengths[1], lengths[3], min(lengths[0], lengths[2]) / aspect_ratio)
    native_width = native_height * aspect_ratio
    fraction = inset_px / min(native_width, native_height)
    if fraction >= 0.5:
        raise ValueError("inset removes the entire artwork")
    height = int(np.floor(native_height * (1 - 2 * fraction))) + 1
    width = int(np.floor(native_width * (1 - 2 * fraction))) + 1
    if min(width, height) < 2:
        raise ValueError("artwork is too small to rectify")

    unit_square = np.float32([[0, 0], [1, 0], [1, 1], [0, 1]])
    unit_to_source = cv2.getPerspectiveTransform(unit_square, corners)
    inset_square = unit_square * (1 - 2 * fraction) + fraction
    inset_corners = cv2.perspectiveTransform(inset_square[None], unit_to_source)[0]
    destination = unit_square * np.float32([width - 1, height - 1])
    return cv2.getPerspectiveTransform(inset_corners, destination), (width, height)


def source_coordinates(points, transform, corners, edge_midpoints=None):
    """Map rectified pixels back to RAW, optionally following bowed face edges.

    Four measured edge midpoints (top/right/bottom/left) add smooth quadratic
    boundary offsets to the projective map. This is a documented approximation
    for visible edge curvature, not a calibrated optical lens profile.
    """
    source = cv2.perspectiveTransform(np.asarray(points, dtype=np.float32), np.linalg.inv(transform))
    if edge_midpoints is None:
        return source
    midpoints = np.asarray(edge_midpoints, dtype=np.float32)
    if midpoints.shape != (4, 2) or not np.isfinite(midpoints).all():
        raise ValueError("edge_midpoints requires four finite top/right/bottom/left pairs")
    unit = np.float32([[0, 0], [1, 0], [1, 1], [0, 1]])
    unit_to_source = cv2.getPerspectiveTransform(unit, np.float32(corners))
    uv = cv2.perspectiveTransform(source, np.linalg.inv(unit_to_source))
    expected = cv2.perspectiveTransform(np.float32([[[.5, 0], [1, .5], [.5, 1], [0, .5]]]), unit_to_source)[0]
    offsets = midpoints - expected
    horizontal, vertical = uv[..., 0:1], uv[..., 1:2]
    source += 4 * horizontal * (1 - horizontal) * ((1 - vertical) * offsets[0] + vertical * offsets[2])
    source += 4 * vertical * (1 - vertical) * ((1 - horizontal) * offsets[3] + horizontal * offsets[1])
    return source


def crop_linear(linear, artwork, transform, size):
    """Resample once in linear light, using an optional curved-edge mapping."""
    if "edge_midpoints" not in artwork:
        return cv2.warpPerspective(linear, transform, size, flags=cv2.INTER_LINEAR)
    width, height = size
    horizontal, vertical = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    mapping = source_coordinates(np.stack([horizontal, vertical], axis=-1), transform, artwork["corners"], artwork["edge_midpoints"])
    if np.any(mapping < 0) or np.any(mapping > np.float32([linear.shape[1] - 1, linear.shape[0] - 1])):
        raise ValueError("Curved crop extends beyond the source image")
    # A coarse Jacobian check rejects folded mappings before any output is saved.
    sample = mapping[::max(1, height // 32), ::max(1, width // 32)]
    across, down = np.diff(sample, axis=1)[:-1], np.diff(sample, axis=0)[:, :-1]
    if np.any(across[..., 0] * down[..., 1] - across[..., 1] * down[..., 0] <= 0):
        raise ValueError("Curved crop folds over itself")
    return cv2.remap(linear, mapping[..., 0], mapping[..., 1], interpolation=cv2.INTER_LINEAR)


def render_artwork(root, artwork, settings=None):
    """Export one annotated artwork and return paths, dimensions and recipe."""
    root = Path(root).resolve()
    config = DEFAULT_SETTINGS | (settings or {})
    development = develop_raw(root, artwork["source"], config)
    linear = np.load(development["linear_path"], mmap_mode="r")
    inset = artwork.get("inset_px", config["inset_px"])
    exposure_ev = artwork.get("exposure_ev", 0.0)
    saturation = artwork.get("saturation", 1.0)
    contrast = artwork.get("contrast", 1.0)
    contrast_pivot = artwork.get("contrast_pivot", 0.35)
    recipe = dict(exposure_ev=exposure_ev, saturation=saturation, contrast=contrast, contrast_pivot=contrast_pivot)
    transform, size = rectification(
        artwork["corners"], artwork["aspect_ratio"], inset, development["source_size"]
    )
    # One resampling in linear light. Bilinear interpolation avoids ringing at
    # paint/frame edges and preserves the original captured color values.
    corrected = crop_linear(linear, artwork, transform, size)
    output_dir = root / config["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    original_dir = output_dir / "originals"
    preview_dir = output_dir / "previews"
    original_dir.mkdir(exist_ok=True)
    preview_dir.mkdir(exist_ok=True)
    master_path = output_dir / f"{artwork['id']}.tif"
    jpeg_path = output_dir / f"{artwork['id']}.jpg"
    original_camera_path = original_dir / f"{Path(artwork['source']).stem}.jpg"
    camera_preview_path = preview_dir / f"{artwork['id']}-camera.jpg"
    developed_preview_path = preview_dir / f"{artwork['id']}-raw.jpg"
    profile = srgb_profile()
    # Deliverables keep their own provenance images; deleting caches is safe.
    shutil.copyfile(development["camera_embedded_path"], original_camera_path)
    for source, destination in [
        (development["camera_preview_path"], camera_preview_path),
        (development["preview_path"], developed_preview_path),
    ]:
        with Image.open(source) as preview:
            save_jpeg(destination, np.asarray(preview), config["preview_max_edge"], 95, profile)
    tifffile.imwrite(
        master_path,
        encoded_pixels(corrected, **recipe),
        photometric="rgb",
        compression="deflate",
        iccprofile=profile,
        metadata=None,
    )
    jpeg_size = save_jpeg(
        jpeg_path,
        encoded_pixels(corrected, bits=8, **recipe),
        config["jpeg_max_edge"],
        config["jpeg_quality"],
        profile,
    )
    return {
        "id": artwork["id"],
        "source": artwork["source"],
        "source_size": development["source_size"],
        "output_size": list(size),
        "jpeg_size": jpeg_size,
        "master_path": master_path.relative_to(root).as_posix(),
        "jpeg_path": jpeg_path.relative_to(root).as_posix(),
        "preview_path": Path(development["preview_path"]).resolve().relative_to(root).as_posix(),
        "original_camera_path": original_camera_path.relative_to(root).as_posix(),
        "camera_preview_path": camera_preview_path.relative_to(root).as_posix(),
        "developed_preview_path": developed_preview_path.relative_to(root).as_posix(),
        "camera_orientation": development["camera_orientation"],
        "aspect_ratio": artwork["aspect_ratio"],
        "inset_px": inset,
        "exposure_ev": exposure_ev,
        "saturation": saturation,
        "contrast": contrast,
        "contrast_pivot": contrast_pivot,
        "homography": transform.tolist(),
        "geometry_method": "projective_with_measured_edge_curvature" if "edge_midpoints" in artwork else "projective",
        "edge_midpoints": artwork.get("edge_midpoints"),
    }


# %% CLI driver (or call develop_raw / render_artwork from notebook cells)
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=WORKSPACE_ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    develop = commands.add_parser("develop", help="Develop RAWs for corner inspection")
    develop.add_argument("sources", nargs="+")
    render = commands.add_parser("render", help="Render annotated manifest entries")
    render.add_argument("manifest", nargs="?", default=f"{PATHS['metadata']}/processing_manifest.json")
    render.add_argument("--ids", nargs="+")
    render.add_argument("--status", default="pilot", help="Status filter; all disables it")
    args = parser.parse_args()
    if args.command == "develop":
        results = [develop_raw(args.root, source) for source in args.sources]
    else:
        manifest_path = args.root / args.manifest
        manifest = json.loads(manifest_path.read_text())
        artworks = manifest["artworks"]
        if args.ids:
            missing = set(args.ids) - {artwork["id"] for artwork in artworks}
            if missing:
                raise ValueError(f"Unknown artwork IDs: {sorted(missing)}")
            artworks = [artwork for artwork in artworks if artwork["id"] in args.ids]
        if args.status != "all":
            artworks = [artwork for artwork in artworks if artwork["status"] == args.status]
        if not artworks:
            raise ValueError("No artworks match the requested IDs/status")
        results = [render_artwork(args.root, artwork, manifest["settings"]) for artwork in artworks]
        for artwork, result in zip(artworks, results):
            artwork["rendered"] = result
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__" and not IN_NOTEBOOK:
    main()
