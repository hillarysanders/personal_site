# Hillary Sanders · personal site and art collection

The public website is static. The catalog editor, photo processing and private
database run locally. The art gallery publishes at `https://hillarysanders.com/art/`.

## Where things live

| Directory | Purpose |
| --- | --- |
| `site/` | Maintained professional pages, shared navigation and gallery source |
| `site/art/catalog.json` | Generated **public** publication snapshot; committed to Git |
| `site/art/images.json` | Small public image manifest; committed to Git |
| `tools/editor/` | Local Node/SQLite editor and migrations |
| `tools/photos/` | Python processing, review, catalog preparation and image export |
| `config/` | Public site settings, path configuration and Git file-size policy |
| `.local/` | Private catalog seed, SQLite, backups and prepared images; ignored |
| `dist/` | Generated public deployment files; ignored |
| `../images/` | Local RAWs, recipes, masters, review history and web exports; outside Git |

Only edit source under this repository. `dist` is disposable. Paths derive from
`config/paths.json`, independent of the shell/notebook working directory.

## Local editing

Requires Node 22.13+ (CI uses Node 24). The website/editor has no npm dependencies.

```sh
npm run dev
```

- Editor: `http://127.0.0.1:8767/admin/`
- Current draft: `http://127.0.0.1:8767/art/`
- Professional pages: `http://127.0.0.1:8767/`

Saved changes stay in `.local/catalog.sqlite`. The seed in
`.local/catalog-seed.json` provides initial records; saved edits and series tables
remain authoritative. Back up both with the photo library. A fresh Git clone does
not contain private collection state. The local editor listens only on loopback;
it is never included in the public build.

For new/revised photos, see [the photo workflow](tools/photos/README.md).
All image development, correction and AVIF/WebP encoding runs locally.

## Prepare a publication

Use **Prepare publication** in the editor, or:

```sh
npm run prepare:publication
npm run check
npm run build
npm run check:git
```

Preparation freezes the public catalog, verifies current derivative files, and
stages the web images under `.local/publication/images/`. It never uploads,
commits or pushes. Review the changes to `site/art/catalog.json` and `images.json`.
The default build works in CI without the database, originals, or image binaries.
`node tools/build.mjs --with-images` includes staged photos for a standalone local
static preview; the editor's draft preview reads current local photos directly.

## Publishing to NearlyFreeSpeech.NET

Setup is intentionally separate from local development. Before the first live
deployment, inventory/back up the existing hosted files: Git does **not** contain
the old art photos or `images/beach.jpg`. Uploads preserve files outside our build;
the deployment scripts never run `rsync --delete` against the host.

The retired `paint.html`, `mixed.html`, `ink.html` and `graphite.html` galleries
are removed from the public source and host. `config/redirects.json` sends their
old URLs to `/art/` in both the local editor and the built Apache configuration.
The original photos remain in the local archive; removing a page never deletes
its photographs. Only explicitly retired files are removed from the host.

1. Copy `config/deploy.example.json` to `.local/deploy.json` and fill in the NFS
   SSH host/user, public root and site origin. Configure an SSH key and verify the
   host key against NFS's published fingerprints. Store the verified host-key line
   in `.local/nfs-known_hosts` (the config's `known_hosts` path); deployment uses
   this project-specific file with strict verification. Secrets never belong in Git.
2. Run `npm run publish:images`. This uploads only changed public photo files and
   verifies the bytes on the host. It does not deploy catalog/code or touch Git.
3. Commit/review the public catalog, manifest and intended code changes. Merge to
   the repository's current default branch, **master**, to trigger deployment.

For an explicitly requested local release before GitHub Actions is enabled, run
`npm run deploy:site` after the prepared images have uploaded successfully. This
publishes the prepared public snapshot and current site source directly to NFS;
it does not commit or push Git changes. Confirm the live `/art/` gallery and
`/art/release.json` afterward. Subsequent local editor changes need a new
preparation and release.

GitHub Actions checks code/catalog and publishes to NFS when production is enabled.
The `production` environment needs `NFS_SSH_PRIVATE_KEY`, `NFS_SSH_KNOWN_HOSTS`,
and `NFS_DEPLOY_CONFIG` secrets (the last is the deployment JSON). Set the repository
variable `NFS_DEPLOY_ENABLED=true` **after** checking the live host and initial
upload. Until then the deploy job is disabled. If the branch is renamed to `main`,
update its three references in `.github/workflows/deploy.yml` together.

The deployment checks that referenced photos exist, uploads code, then catalog
data, and records `art/release.json`. Jobs are serialized and stale commits are
skipped. NFS permits key-based automated uploads within its
[upload-frequency rules](https://faq.nearlyfreespeech.net/q/AutomatedSSH).

### One current photo version

NFS stores stable paths such as `art/assets/art-005-900.avif`. A replacement
overwrites that file immediately; it does not wait for a catalog/code merge.
The `?v=...` in the catalog is a browser cache hint, not a second hosted image.
Images revalidate through Apache cache headers. There is no hosted photo-version
archive and reverting a catalog commit does not revert the photographs.
The local processing archive remains available separately.

## Checks and recovery

```sh
npm run check                    # Catalog persistence, privacy, series and static build
npm run check:git                # Private/binary/large-file guard
uv sync --extra notebook         # Only needed for Python photo work
uv run python -m unittest discover -s tests/photos -v
```

The existing CV PDF is the only explicit exception to the 1 MiB Git file limit.
Artwork images, databases, RAWs, masters and prepared builds stay out of Git.
Code and public catalog can be reverted in Git. Recover an earlier photograph from
the local library and upload it explicitly if desired; old photo bytes are not
required for code deployment. Private editor changes are never rolled back by a
Git deployment.
