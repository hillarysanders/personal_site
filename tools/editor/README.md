# Local collection editor

Run `npm run dev`, then open `http://127.0.0.1:8767/admin/`. The server binds only to this computer. Set `PORT` to change the port.

The imported `.local/catalog-seed.json` supplies defaults; `.local/catalog.sqlite` stores edits and linked-series order. Existing migration names are preserved so reopening a copied database never reseeds saved edits. Current image variants come from the local photo library manifest, so regenerated photos appear after reloading the draft.

**Save locally** updates SQLite. **View draft gallery** previews those saved edits at `/art/`. **Prepare publication** freezes a public snapshot through `tools/publication.mjs`; it does not upload or publish. The CSV export contains private notes and is for local use.

Dated `Photo review (...)` lines in private notes appear on collection cards and in the photo assessment. Use **Photo review recorded** to find reviewed works, **Photo needs review** for borderline captures, or **Excluded from draft** to revisit hidden works. Recommendations describe the review at its recorded date; the visibility switch remains authoritative. Review links can preset `search`, `visibility`, `review`, and `sale` filters through URL parameters.

Only the public `site/` tree, editor assets, and explicit local photo routes are served. Saves require a same-origin request. No account, hosted database, image processor, or cloud authentication is involved.

Run `node --test tests/editor.test.mjs` for synthetic catalog and route checks; these need no private database or photo library.
