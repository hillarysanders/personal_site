"""Build a portable local HTML comparison of reviewed website-import decisions."""
# %% Imports and notebook reload
import argparse
from base64 import b64encode
from html import escape
from io import BytesIO
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps
from image_paths import WORKSPACE_ROOT, metadata_path

IN_NOTEBOOK = "ipykernel" in sys.modules
if IN_NOTEBOOK:
    from IPython import get_ipython
    ipython = get_ipython()
    ipython.run_line_magic("load_ext", "autoreload")
    ipython.run_line_magic("autoreload", "2")


# %% Review artifact; original photographs remain untouched

def build_review(decisions_path, root=WORKSPACE_ROOT):
    root = Path(root).resolve()
    decisions_path = Path(decisions_path).resolve()
    decisions = json.loads(decisions_path.read_text())
    archive = root / decisions["archive"]
    downloaded = json.loads((archive.parent / "inventory.json").read_text())["downloaded_at"][:10]
    raw = {art["id"]: art for art in json.loads(metadata_path(root, "processing_manifest.json").read_text())["artworks"]}
    def figure(path, caption, rotation=0):
        with Image.open(path) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            if rotation:
                image = image.rotate(rotation, expand=True)
            dimensions = f"{image.width} × {image.height} px"
            image.thumbnail((650,650))
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=88)
        data = b64encode(buffer.getvalue()).decode()
        return f'<figure><a href="{escape(path.as_uri())}"><img loading="lazy" src="data:image/jpeg;base64,{data}" alt="{escape(caption)}"></a><figcaption>{escape(caption)} · {dimensions}</figcaption></figure>'
    sections = []
    for group in decisions["groups"]:
        identity = group["id"]
        category = "comparisons" if group["kind"] == "existing" else "added" if group["published"] else "drafts"
        images = []
        if group["kind"] == "existing":
            original = raw[identity]
            path = root / (original["rendered"]["jpeg_path"] if original["rendered"] else original["original_camera_path"])
            images.append(figure(path, "Previous local edit"))
        for source in group["sources"]:
            selected = source == group["selected"]
            images.append(figure(archive / source, ("Selected: " if selected else "Alternative/detail: ") + source,
                                 group["rotation"] if selected else 0))
        decision = "Keep current full view" if group["selected"] is None else "Use selected photo"
        sections.append(f'<article data-kind="{category}"><h2>{identity} · {escape(group["title"])}</h2><p><strong>{decision}</strong> · {category}</p><p>{escape(group["reason"])}</p><div class="photos">'+''.join(images)+'</div></article>')
    comparisons = sum(group["kind"] == "existing" for group in decisions["groups"])
    replacements = sum(group["kind"] == "existing" and group["selected"] is not None for group in decisions["groups"])
    additions = sum(group["kind"] == "new" for group in decisions["groups"])
    drafts = sum(group["kind"] == "new" and not group["published"] for group in decisions["groups"])
    html = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Website photo import review</title><style>
body{background:#192127;color:#e6e8e5;font:16px system-ui;margin:0 auto;padding:30px;max-width:1400px}h1{font-weight:500}p{max-width:950px;line-height:1.6;color:#bac4c9}nav{position:sticky;top:0;background:#192127;padding:16px 0;z-index:1}button{padding:10px 18px;margin:4px;border:1px solid #788b94;background:#2c3a44;color:inherit;cursor:pointer}button[aria-pressed=true]{background:#657c86}article{border-top:1px solid #56636c;padding:20px 0 36px}.photos{display:flex;flex-wrap:wrap;gap:22px}figure{margin:0;flex:1 1 350px;max-width:650px}img{width:100%;height:520px;object-fit:contain;background:#11171b}figcaption{font-size:13px;overflow-wrap:anywhere;margin:10px 0;color:#bac4c9}[hidden]{display:none!important}@media(max-width:600px){body{padding:16px}img{height:400px}figure{flex-basis:100%}}
</style><h1>Website photo import review</h1><p>Untouched archive downloaded from HillarySanders.com on {downloaded}. Compare {comparisons} existing works, including {replacements} preferred replacements; {additions} additional works are cataloged, with {drafts} retained as drafts. Click a photo to open its full original. These previews are for comparison; color fidelity cannot be established from photographs alone.</p><p>All source files remain preserved. Titles are descriptive placeholders; dates, physical measurements, prices and availability have not been guessed. Similar but distinct sunflower, fruit and landscape studies remain separate.</p><nav>'''
    html = html.replace("{downloaded}", downloaded).replace("{comparisons}", str(comparisons)).replace("{replacements}", str(replacements)).replace("{additions}", str(additions)).replace("{drafts}", str(drafts))
    for key, label in [("comparisons",f"{comparisons} comparisons"),("added",f"{additions - drafts} added works"),("drafts",f"{drafts} drafts"),("all","Everything")]:
        html += f'<button data-filter="{key}" aria-pressed="false">{label}</button>'
    html += '</nav>'+''.join(sections)+'''<script>function select(kind){document.querySelectorAll('article').forEach(article=>article.hidden=kind!=='all'&&article.dataset.kind!==kind);document.querySelectorAll('button').forEach(button=>button.setAttribute('aria-pressed',button.dataset.filter===kind))}document.querySelector('nav').onclick=event=>{if(event.target.dataset.filter)select(event.target.dataset.filter)};select('comparisons');</script></html>'''
    output = decisions_path.parent / "review.html"
    output.write_text(html)
    print(output)
    return output


# %% Command-line entry
if __name__ == "__main__" and not IN_NOTEBOOK:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decisions", type=Path)
    build_review(parser.parse_args().decisions)
