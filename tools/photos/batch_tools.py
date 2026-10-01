"""Small visual aids for annotating and inspecting the artwork batch."""

# %% Imports
from pathlib import Path
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw


# %% Full-view coordinates and native border sheets
def overview(source, destination, corners=None, max_edge=1600):
    """Label a reduced view with original pixel coordinates and optional quad."""
    image = Image.open(source).convert("RGB")
    scale = min(1, max_edge / max(image.size))
    image = image.resize(tuple(round(value * scale) for value in image.size))
    draw = ImageDraw.Draw(image)
    for axis in [0, 1]:
        for value in range(0, round(image.size[axis] / scale), 500):
            position = round(value * scale)
            if axis == 0:
                draw.line((position, 0, position, image.height), fill="#999999", width=1)
                draw.text((position + 2, 4), str(value), fill="yellow", stroke_fill="black", stroke_width=1)
            else:
                draw.line((0, position, image.width, position), fill="#999999", width=1)
                draw.text((4, position + 2), str(value), fill="yellow", stroke_fill="black", stroke_width=1)
    if corners is not None:
        points = [(float(x) * scale, float(y) * scale) for x, y in corners]
        draw.line(points + [points[0]], fill="yellow", width=2)
    image.save(destination)
    return str(destination)


def border_sheets(source, directory, label, depth=80, tile_width=480):
    """Cover every output border at 1:1 pixel scale across compact QA pages.

    Vertical strips are rotated for display only. Returned images are review
    artifacts, never processing inputs or replacements for the master.
    """
    image = Image.open(source).convert("RGB")
    width, height = image.size
    edges = {
        "top": image.crop((0, 0, width, depth)),
        "bottom": image.crop((0, height - depth, width, height)),
        "left rotated": image.crop((0, 0, depth, height)).transpose(Image.Transpose.ROTATE_90),
        "right rotated": image.crop((width - depth, 0, width, height)).transpose(Image.Transpose.ROTATE_90),
    }
    patches = [(name, start, edge.crop((start, 0, min(start + tile_width, edge.width), depth)))
               for name, edge in edges.items() for start in range(0, edge.width, tile_width)]
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for page in range(math.ceil(len(patches) / 12)):
        subset = patches[page * 12:(page + 1) * 12]
        sheet = Image.new("RGB", (2 * tile_width, math.ceil(len(subset) / 2) * (depth + 25)), "#eeeeeb")
        draw = ImageDraw.Draw(sheet)
        for index, (name, start, patch) in enumerate(subset):
            x, y = index % 2 * tile_width, index // 2 * (depth + 25)
            draw.text((x + 3, y + 3), f"{label}: {name} {start}px", fill="black")
            sheet.paste(patch, (x, y + 25))
        path = directory / f"{label}-border-{page + 1}.jpg"
        sheet.save(path, quality=98, subsampling=0)
        paths.append(str(path))
    return paths


def quad_from_lines(lines):
    """Intersect manually verified top/right/bottom/left endpoint pairs."""
    equations = [np.cross([*start, 1], [*end, 1]) for start, end in lines]
    points = [np.cross(equations[index - 1], equations[index]) for index in range(4)]
    if any(abs(point[2]) < 1e-10 for point in points):
        raise ValueError("Adjacent artwork boundary lines are parallel")
    return [[float(point[0] / point[2]), float(point[1] / point[2])] for point in points]
