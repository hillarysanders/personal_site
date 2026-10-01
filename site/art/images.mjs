import {escapeHtml as esc} from "./gallery.mjs";

/** These slot widths mirror style.css, including the capped shell and both layouts. */
export function gallerySizes(layout, span) {
  if (layout === "uniform") return "(max-width:600px) calc(100vw - 40px), (max-width:720px) calc((100vw - 58px)/2), (max-width:1050px) calc((100vw - 89px)/2), calc((min(1320px, 100vw - 112px) - 84px)/4)";
  const slots = span === 2
    ? ["calc(100vw - 40px)", "calc(100vw - 64px)", "calc((100vw - 92px)/2)", "calc((min(1320px, 100vw - 112px) - 28px)/2)"]
    : ["calc((100vw - 58px)/2)", "calc((100vw - 82px)/2)", "calc((100vw - 148px)/4)", "calc((min(1320px, 100vw - 112px) - 84px)/4)"];
  return `(max-width:380px) calc(100vw - 40px), (max-width:720px) ${slots[0]}, (max-width:900px) ${slots[1]}, (max-width:1050px) ${slots[2]}, ${slots[3]}`;
}

/** Contained artwork can be height-limited; screen width alone overfetches portraits. */
export function viewerSizes(art, zoom = false) {
  const image = art.images.at(-1), ratio = image.width / image.height;
  if (zoom) return `min(calc(100vw - 64px), calc((100dvh - 94px)*${ratio}))`;
  return `(max-width:720px) min(calc(100vw - 76px), calc(55dvh*${ratio})), (max-width:1050px) min(calc((100vw - 142px)*${1.65 / 2.65} - 36px), calc(100vw - 458px), calc((100dvh - 250px)*${ratio})), min(calc((min(1380px, 100vw - 64px) - 116px)*${1.65 / 2.65} - 52px), calc(min(1380px, 100vw - 64px) - 448px), calc((100dvh - 250px)*${ratio}))`;
}

/** Both codecs describe the same pixels; the browser downloads only its chosen format/size. */
export function picture(art, {sizes, maxEdge = Infinity, loading = "eager", priority = "auto", id = "", alt}) {
  // Several requested tiers may share the native width of a small master.
  const images = art.images.filter(image => image.edge <= maxEdge).filter((image, index, variants) => index === 0 || image.width !== variants[index - 1].width), largest = images.at(-1);
  const srcset = field => images.map(image => `${image[field]} ${image.width}w`).join(", ");
  const slots = (loading === "lazy" ? "auto, " : "") + sizes;
  return `<picture><source type="image/avif" srcset="${srcset("avif")}" sizes="${slots}"><img ${id ? `id="${id}"` : ""} src="${images[0].src}" srcset="${srcset("src")}" sizes="${slots}" width="${largest.width}" height="${largest.height}" alt="${esc(alt)}" loading="${loading}" fetchpriority="${priority}" decoding="async"></picture>`;
}
