import {mediaCategories,categoryForMedium} from "./media.mjs";
import {picture, gallerySizes, viewerSizes} from "./images.mjs";
import {watchPhotos} from "./photo-loading.mjs";
import {emptyFilters, dimensionKey, dimensionLabel, matches, priceLabel, statusLabel, escapeHtml as esc, artworkSpan, masonryPositions, artworkGroups} from "./gallery.mjs?v=artwork-series";
const query = selector => document.querySelector(selector);
const grid = query("#art-grid");
watchPhotos(grid);
const dialog = query("#art-dialog");
const zoom = query("#zoom-dialog");
const state = emptyFilters();
let artworks, site, visible, currentId, opener;
let layout = "uniform";
const options = (items, all) => '<option value="all">' + all + "</option>" + items.map(([value, label]) => '<option value="' + esc(value) + '">' + esc(label) + "</option>").join("");
const select = (name, label, items) => '<label class="filter-select"><span>' + label + '</span><select id="filter-' + name + '" data-filter="' + name + '" aria-label="' + label + '">' + options(items, "All " + label.toLowerCase()) + "</select></label>";
const soldDot = art => art.availability === "sold" ? '<span class="sold-dot" title="Sold"><span class="visually-hidden">Sold</span></span>' : "";
const artworkLabel = art => art.title || (art.themes.length ? art.themes.join(" / ") + " painting" : "Painting");
const summary = art => [[art.medium, art.surface].filter(Boolean).join(" on ") || art.themes.join(" · "), dimensionLabel(art)].filter(Boolean).map(esc).join("<span> · </span>");
const card = (art, index) => {
  const image = art.images[0];
  const photo = picture(art, {sizes:gallerySizes(layout, artworkSpan(art)), maxEdge:site.gallery_image_max_edge, loading:index < 4 ? "eager" : "lazy", priority:index === 0 ? "high" : "auto", alt:art.description || artworkLabel(art)});
  return '<article class="art-card" data-span="' + artworkSpan(art) + '" data-panorama="' + (image.width / image.height > 2) + '"><button class="image-surface" data-art="' + art.id + '" aria-label="View ' + esc(artworkLabel(art)) + '">' + photo + '<span class="card-expand" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/></svg></span></button><div class="card-caption"><div class="card-title-row"><h3' + (art.title ? "" : ' class="visually-hidden"') + '>' + esc(artworkLabel(art)) + '</h3>' + soldDot(art) + '</div><div class="card-details"><p class="card-meta">' + summary(art) + '</p><p class="card-availability">' + statusLabel(art) + (art.availability === "available" && priceLabel(art) ? " · " + esc(priceLabel(art)) : "") + '</p></div></div></article>';
};

function updateUrl() {
  const url = new URL(location.href);
  for (const [key, value] of Object.entries(state)) {
    if (value !== "all" && value !== "") url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }
  if (layout !== "uniform") url.searchParams.set("layout", layout);
  else url.searchParams.delete("layout");
  if (currentId) url.searchParams.set("art", currentId);
  else url.searchParams.delete("art");
  history.replaceState(null, "", url);
}
let packingFrame, packingColumns;
const masonryObserver = new ResizeObserver(() => {
  cancelAnimationFrame(packingFrame);
  packingFrame = requestAnimationFrame(packGallery);
});
function packGallery() {
  if (layout !== "size") return;
  const style = getComputedStyle(grid);
  const unit = parseFloat(style.gridAutoRows), gap = parseFloat(style.getPropertyValue("--card-gap"));
  const columns = Number(style.getPropertyValue("--gallery-columns"));
  // Overlays stay outside the flow; pack only the natural image heights.
  const cards = [...grid.children];
  if (columns !== packingColumns) {
    for (const card of cards) {
      card.style.removeProperty("grid-column");
      card.style.removeProperty("grid-row");
    }
    packingColumns = columns;
  }
  const items = cards.map(card => ({id:card.querySelector("[data-art]").dataset.art, columns:Number(card.dataset.span), rows:Math.ceil((card.getBoundingClientRect().height + gap) / unit)}));
  masonryPositions(items, columns).forEach((position, index) => {
    cards[index].style.gridRow = (position.row + 1) + " / span " + position.rows;
    cards[index].style.gridColumn = (position.column + 1) + " / span " + position.columns;
  });
}
function watchGallery() {
  masonryObserver.disconnect();
  cancelAnimationFrame(packingFrame);
  if (layout === "size") {
    packGallery();
    for (const card of grid.children) masonryObserver.observe(card);
  } else {
    for (const card of grid.children) {
      card.style.removeProperty("grid-row");
      card.style.removeProperty("grid-column");
    }
  }
}
function setLayout(value, {render = true} = {}) {
  if (!["size", "uniform"].includes(value)) throw new Error("Unknown gallery layout: " + value);
  layout = value;
  grid.dataset.layout = layout;
  query("#size-layout").setAttribute("aria-checked", String(layout === "size"));
  if (render) renderCollection({announce:false});
}
function renderCollection({announce = true} = {}) {
  visible = artworks.filter(art => matches(art, state));
  let cardIndex = 0;
  const renderCard = art => card(art, cardIndex++);
  grid.innerHTML = artworkGroups(visible).map(members=>members.length===1?renderCard(members[0]):
    '<div class="art-group" role="group" aria-label="'+esc(members[0].seriesTitle)+'" data-span="'+Math.max(...members.map(artworkSpan))+'">'+members.map(renderCard).join('')+'</div>').join("");
  watchGallery();
  query("#artwork-count").textContent = visible.length + (visible.length === 1 ? " work" : " works");
  query("#empty-state").hidden = visible.length > 0;
  document.querySelectorAll("[data-theme]").forEach(button => {
    const active = button.dataset.theme === state.theme;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  for (const [key, value] of Object.entries(state)) {
    const control = query('[data-filter="' + key + '"]');
    if (control) control.value = value;
  }
  query("#reset-filters").hidden = Object.entries(state).every(([key, value]) => value === emptyFilters()[key]);
  if (announce) query("#live-status").textContent = visible.length + " artworks shown";
  updateUrl();
}
function setFilters(patch) {
  // Preserve links created before medium descriptions became broad filter categories.
  if(Object.hasOwn(patch,"medium") && patch.medium!=="all" && !mediaCategories.includes(patch.medium)){
    const category=categoryForMedium(patch.medium);
    if(category)patch={...patch,medium:category};
  }
  if(Object.hasOwn(patch,"theme"))patch={...patch,theme:site.category_aliases[patch.theme]||patch.theme};
  for (const [key, value] of Object.entries(patch)) {
    if (!(key in state) || typeof value !== "string") throw new Error("Invalid filter: " + key);
    if (key !== "search") {
      const allowed = key === "theme" ? ["all", ...artworks.flatMap(art => art.themes)] : [...query('[data-filter="' + key + '"]').options].map(option => option.value);
      if (!allowed.includes(value)) throw new Error("Unknown " + key + ": " + value);
    }
  }
  Object.assign(state, patch);
  renderCollection();
  return {count:visible.length, artworkIds:visible.map(art => art.id)};
}
function inquiryLink(art) {
  return "mailto:" + site.inquiry_email + "?subject=" + encodeURIComponent("Artwork inquiry: " + art.title + " (" + art.id + ")") + "&body=" + encodeURIComponent("Hello,\n\nI'm interested in " + art.title + ". Could you share more details?\n\n");
}
function updateZoom(art) {
  query("#zoom-content").innerHTML = picture(art, {sizes:viewerSizes(art, true), id:"zoom-image", alt:art.description || artworkLabel(art)});
  zoom.setAttribute("aria-label", "Enlarged artwork: " + artworkLabel(art));
}
function showArtwork(id, trigger = null) {
  const art = artworks.find(item => item.id === id);
  if (!art) throw new Error("Unknown artwork: " + id);
  if (!dialog.open) opener = trigger || document.activeElement;
  // Rendering replaces the focused image/share button; retain keyboard focus.
  const focusInDetails = query("#detail-content").contains(document.activeElement);
  currentId = id;
  const photo = picture(art, {sizes:viewerSizes(art), alt:art.description || artworkLabel(art)});
  const specs = [
    ["Dimensions", dimensionLabel(art)], ["Medium", art.medium], ["Surface", art.surface], ["Year", art.year],
    ["Series / period", art.period], ["Categories", art.themes.join(" · ")]
  ].filter(([, value]) => value);
  const purchase = art.availability === "available" && art.purchaseUrl ? '<a class="primary-link" href="' + esc(art.purchaseUrl) + '" target="_blank" rel="noopener noreferrer">Purchase this work ↗</a>' :
    art.availability === "available" && site.inquiry_email ? '<a class="primary-link" href="' + esc(inquiryLink(art)) + '">Inquire about this work ↗</a>' : "";
  query("#detail-content").innerHTML = '<div class="detail-layout"><div class="detail-art"><button id="enlarge-art" aria-label="Enlarge ' + esc(artworkLabel(art)) + '">' + photo + '</button></div><div class="detail-copy"><p class="eyebrow">' + esc(art.themes.join(" · ")) + '</p><div class="detail-title-row"><h2 id="detail-title"' + (art.title ? "" : ' class="visually-hidden"') + '>' + esc(artworkLabel(art)) + '</h2>' + soldDot(art) + '</div><p class="description">' + esc(art.description) + '</p><dl>' + specs.map(([label, value]) => '<div><dt>' + label + '</dt><dd>' + esc(value) + '</dd></div>').join("") + '</dl>' + (art.availability ? '<div class="detail-sale"><p>' + statusLabel(art) + '</p>' + (art.availability === "available" ? '<p class="price">' + (priceLabel(art) ? esc(priceLabel(art)) : "Price on request") + '</p>' : "") + '</div>' : "") + purchase + '<button class="share-link" id="share-art"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg><span>Copy link</span></button><p class="share-status" id="share-status" role="status"></p></div></div>';
  query("#previous-art").disabled = visible.length < 2;
  query("#next-art").disabled = visible.length < 2;
  query("#enlarge-art").addEventListener("click", () => {
    updateZoom(art);
    zoom.showModal();
  });
  query("#share-art").addEventListener("click", async () => {
    const url = new URL(location.href);
    url.search = "";
    url.searchParams.set("art", art.id);
    url.hash = "";
    try {
      await navigator.clipboard.writeText(url.href);
      query("#share-status").textContent = "Link copied.";
    } catch {
      query("#share-status").textContent = url.href;
    }
  });
  if (!dialog.open) {
    dialog.showModal();
    dialog.focus({preventScroll:true});
  } else if (focusInDetails && !zoom.open) dialog.focus({preventScroll:true});
  if (zoom.open) updateZoom(art);
  dialog.scrollTop = 0;
  updateUrl();
}
function stepArtwork(delta) {
  if (visible.length < 2) return;
  const index = visible.findIndex(art => art.id === currentId);
  const next = index < 0 ? (delta > 0 ? 0 : visible.length - 1) : (index + delta + visible.length) % visible.length;
  showArtwork(visible[next].id);
}
function setupControls() {
  const themes = [...new Set(artworks.flatMap(art => art.themes).filter(Boolean))];
  query(".theme-tabs").innerHTML = [["all", "All Work"], ...themes.map(theme => [theme, theme])].map(([value, label]) => '<button data-theme="' + esc(value) + '" aria-pressed="false">' + esc(label) + '</button>').join("");
  const unique = key => [...new Set(artworks.map(art => art[key]).filter(Boolean))].sort().map(value => [value, value]);
  const sizes = ["Small", "Medium", "Large"].filter(value => artworks.some(art => art.sizeCategory === value)).map(value => [value, value + " works"]);
  const dimensions = [...new Map(artworks.filter(art => dimensionKey(art)).sort((first, second) => first.width - second.width || first.height - second.height).map(art => [dimensionKey(art), [dimensionKey(art), art.width + " × " + art.height + " in"]])).values()];
  query("#filter-controls").innerHTML = '<div class="filter-bar"><div class="selects">' + select("medium", "Media", mediaCategories.map(category => [category, category])) + select("size", "Sizes", sizes) + select("dimensions", "Dimensions", dimensions) + select("availability", "Availability", [["available","Available"],["private","Private collection"],["sold","Sold"]]) + '<span' + (unique("period").length ? "" : " hidden") + '>' + select("period", "Periods", unique("period")) + '</span></div><button id="size-layout" type="button" role="switch" aria-checked="false"><span>Larger paintings get more space</span><span class="switch-track" aria-hidden="true"></span></button><label class="search"><span class="visually-hidden">Search titles, descriptions, subjects, media or years</span><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6.5"/><path d="m15 15 5 5"/></svg><input type="search" data-filter="search" placeholder="Search title, subject, medium or year" title="Search titles, descriptions, subjects, media or years" aria-label="Search titles, descriptions, subjects, media or years"></label><button id="reset-filters" class="reset-filters" data-reset hidden>Clear filters</button></div>';
  query("#filter-controls").addEventListener("change", event => {
    if (event.target.dataset.filter) setFilters({[event.target.dataset.filter]:event.target.value});
  });
  query('[data-filter="search"]').addEventListener("input", event => setFilters({search:event.target.value}));
  query("#size-layout").addEventListener("click", () => setLayout(layout === "size" ? "uniform" : "size"));
  document.addEventListener("click", event => {
    const artwork = event.target.closest("[data-art]");
    const theme = event.target.closest("[data-theme]");
    if (artwork) showArtwork(artwork.dataset.art, artwork);
    if (theme) setFilters({theme:theme.dataset.theme});
    if (event.target.closest("[data-reset]")) setFilters(emptyFilters());
  });
  query("#close-detail").addEventListener("click", () => dialog.close());
  query("#close-zoom").addEventListener("click", () => zoom.close());
  query("#previous-art").addEventListener("click", () => stepArtwork(-1));
  query("#next-art").addEventListener("click", () => stepArtwork(1));
  // Both modal viewers share navigation, including after their content changes.
  document.addEventListener("keydown", event => {
    if ((!dialog.open && !zoom.open) || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.target.closest("input, textarea, select, [contenteditable]")) return;
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    stepArtwork(event.key === "ArrowLeft" ? -1 : 1);
  });
  zoom.addEventListener("close", () => {
    if (dialog.open) query("#enlarge-art").focus({preventScroll:true});
  });
  dialog.addEventListener("close", () => {
    currentId = null;
    updateUrl();
    if (opener?.isConnected) opener.focus({preventScroll:true});
  });
  for (const modal of [dialog, zoom]) modal.addEventListener("click", event => {
    if (event.target === modal) {
      const rect = modal.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) modal.close();
    }
  });
}
async function registerPageTools() {
  if (!document.modelContext?.registerTool) return;
  const lifecycle = new AbortController();
  addEventListener("pagehide", () => lifecycle.abort(), {once:true});
  const result = value => ({content:[{type:"text", text:JSON.stringify(value)}]});
  await document.modelContext.registerTool({
    name:"filter_artworks", description:"Filter the visible artwork gallery by theme, medium, size, dimensions, availability, period or search text. Use all to clear a category.",
    inputSchema:{type:"object", properties:Object.fromEntries(Object.keys(state).map(key => [key,{type:"string"}])), additionalProperties:false},
    execute:async args => result(setFilters(args))
  }, {signal:lifecycle.signal});
  await document.modelContext.registerTool({
    name:"open_artwork", description:"Open a published artwork in the visible artwork detail view.",
    inputSchema:{type:"object",properties:{artwork_id:{type:"string"}},required:["artwork_id"],additionalProperties:false},
    execute:async ({artwork_id}) => {showArtwork(artwork_id); return result({opened:artwork_id});}
  }, {signal:lifecycle.signal});
  await document.modelContext.registerTool({
    name:"list_artworks", description:"List the currently filtered artworks with their IDs, titles and available catalog details.",
    inputSchema:{type:"object",properties:{},additionalProperties:false},
    execute:async () => result(visible.map(({id,title,themes,availability,width,height,dimensionsConfirmed}) => ({id,title,themes,availability,width,height,dimensionsConfirmed})))
  }, {signal:lifecycle.signal});
}
async function start() {
  const initialCatalog = query("#initial-catalog");
  if (initialCatalog) ({artworks, site} = JSON.parse(initialCatalog.textContent));
  else {
    const response = await fetch("data.json", {cache:"no-cache"});
    if (!response.ok) throw new Error("Artwork catalog could not load: " + response.status);
    ({artworks, site} = await response.json());
  }
  if (site.canAdmin) {
    const link = document.createElement("a");
    link.href = "/admin/"; link.textContent = "Admin";
    const navigation = query(".site-header nav");
    navigation.append(link);
    navigation.hidden = false;
  }
  setupControls();
  query("[data-copyright-owner]").textContent = site.copyright_owner;
  document.querySelectorAll("[data-artist]").forEach(element => element.textContent = site.artist_name);
  document.querySelectorAll(".inquiry-nav").forEach(link => {
    link.hidden = !site.inquiry_email;
    if (site.inquiry_email) link.href = "mailto:" + site.inquiry_email;
  });
  const params = new URL(location.href).searchParams;
  const requestedArt = params.get("art");
  const initial = {};
  for (const key of Object.keys(state)) if (params.has(key)) initial[key] = params.get(key);
  // Apply initial layout and filters before making the first image requests.
  setLayout(params.get("layout") || "uniform", {render:false});
  setFilters(initial);
  if (requestedArt && artworks.some(art => art.id === requestedArt)) showArtwork(requestedArt);
  registerPageTools().catch(error => console.error("Page tools unavailable:", error));
}
start().catch(error => {
  console.error(error);
  query("#filter-controls").innerHTML = '<p class="load-error">The interactive collection could not load. Please refresh to try again.</p>';
});
