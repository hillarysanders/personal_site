/** Shared HTML expansion for the local preview and the static build. */
const escapeHtml=value=>String(value).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
export function renderHtml(html,navigation,site) {
  return html.replaceAll("<!-- SITE_NAV -->",navigation)
    .replaceAll("<!-- COPYRIGHT_OWNER -->",escapeHtml(site.copyright_owner))
    .replaceAll("<!-- ARTWORK_CARDS -->","")
    .replaceAll("Selected Works",escapeHtml(site.site_title));
}
