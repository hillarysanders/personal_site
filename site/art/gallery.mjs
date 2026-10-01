/** Shared catalog semantics: the visible controls and page tools use the same state. */
export const emptyFilters = () => ({theme:"all", medium:"all", size:"all", dimensions:"all", availability:"all", period:"all", search:""});
export const dimensionKey = art => art.width && art.height ? art.width + "x" + art.height : "";
export const dimensionLabel = art => art.width && art.height ? art.width + " × " + art.height + " in" : "";
export const matches = (art, state) =>
  (state.theme === "all" || art.themes.includes(state.theme)) &&
  (state.medium === "all" || art.mediaCategory === state.medium) &&
  (state.size === "all" || art.sizeCategory === state.size) &&
  (state.dimensions === "all" || dimensionKey(art) === state.dimensions) &&
  (state.availability === "all" || art.availability === state.availability) &&
  (state.period === "all" || art.period === state.period) &&
  [art.title, art.description, ...art.themes, art.medium, art.mediaCategory, art.year].join(" ").toLowerCase().includes(state.search.trim().toLowerCase());
export const priceLabel = art => art.price === null ? "" : new Intl.NumberFormat("en-US", {style:"currency", currency:art.currency, maximumFractionDigits:art.price % 1 ? 2 : 0}).format(art.price);
export const statusLabel = art => ({sold:"Sold", private:"Private collection", available:"Available", "":""})[art.availability];
export const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);

/** Treat each series as one ordered block, retaining its deliberate member order. */
export function artworkGroups(artworks){
  const groups=new Map();
  for(const art of artworks){
    const key=art.seriesId||art.id;
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(art);
  }
  return [...groups.values()].map(members=>members.sort((a,b)=>a.seriesPosition-b.seriesPosition||a.id.localeCompare(b.id)))
    .sort((a,b)=>Math.min(...a.map(art=>art.order))-Math.min(...b.map(art=>art.order))||(a[0].seriesId||a[0].id).localeCompare(b[0].seriesId||b[0].id));
}
export const sortArtworks=artworks=>artworkGroups(artworks).flat();

/** Compare painted area rather than the longest edge, so narrow panoramas also count. */
export const galleryLayout = {largeAreaIn2:144};
/** Known large works keep their larger placement while exact measurements are pending. */
export const artworkSpan = art => (art.width !== null && art.height !== null ? art.width * art.height >= galleryLayout.largeAreaIn2 : art.sizeCategory === "Large") ? 2 : 1;

/** Pack artwork or whole-series blocks into the earliest free rectangle. */
export function masonryPositions(items, columns) {
  const placed = [];
  for (const item of items) {
    const width = Math.min(item.columns, columns);
    const candidateRows = [...new Set([0, ...placed.map(card => card.row + card.rows)])].sort((first, second) => first - second);
    let position;
    for (const row of candidateRows) {
      for (let column = 0; column <= columns - width; column++) {
        const overlaps = placed.some(card => column < card.column + card.columns && column + width > card.column && row < card.row + card.rows && row + item.rows > card.row);
        if (!overlaps) { position = {...item, columns:width, row, column}; break; }
      }
      if (position) break;
    }
    if (!position) throw new Error("No gallery position for " + item.id);
    placed.push(position);
  }
  return placed;
}
