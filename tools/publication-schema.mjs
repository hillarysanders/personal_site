/** The public release contract is shared by local export, CI and deployment. */
import assert from "node:assert/strict";
import {createHash} from "node:crypto";

export const digest=bytes=>createHash("sha256").update(bytes).digest("hex");
export const PUBLIC_FIELDS=["id","title","description","theme","themes","period","year","medium","surface","width","height","dimensionsConfirmed","sizeCategory","price","currency","availability","purchaseUrl","order","seriesId","seriesTitle","seriesPosition","images"];
export function validatePublication(catalog,manifest) {
  assert.deepEqual(Object.keys(catalog).sort(),["artworks","site"]);
  assert.deepEqual(Object.keys(catalog.site).sort(),["artist_name","site_title","inquiry_email","category_aliases","copyright_owner","gallery_image_max_edge","canAdmin"].sort());
  assert.equal(catalog.site.canAdmin,false,"Publication must not enable the local editor");
  assert.deepEqual(Object.keys(manifest).sort(),["files","version"],"Unexpected/private image manifest fields");
  assert.equal(manifest.version,1);
  const files=new Map();
  for(const file of manifest.files) {
    assert.deepEqual(Object.keys(file).sort(),["bytes","path","sha256"],"Unexpected/private image metadata");
    assert.match(file.path,/^assets\/art-\d+-\d+\.(avif|webp)$/);
    assert.match(file.sha256,/^[a-f0-9]{64}$/);
    assert(Number.isSafeInteger(file.bytes)&&file.bytes>0);
    assert(!files.has(file.path),"Duplicate image target");files.set(file.path,file);
  }
  const referenced=new Set(),ids=new Set();
  for(const artwork of catalog.artworks) {
    assert.match(artwork.id,/^art-\d+$/);assert(!ids.has(artwork.id));ids.add(artwork.id);
    assert.deepEqual(Object.keys(artwork).sort(),[...PUBLIC_FIELDS].sort(),"Unexpected/private catalog fields");
    assert(artwork.images.length>0,"Published artwork requires a photo");
    for(const image of artwork.images) {
      assert.deepEqual(Object.keys(image).sort(),["src","avif","width","height","edge"].sort());
      assert([image.width,image.height,image.edge].every(value=>Number.isSafeInteger(value)&&value>0));
      for(const field of ["src","avif"]) {
        const url=new URL(image[field],"https://local.invalid/art/");
        assert.equal(url.origin,"https://local.invalid");
        const filename=url.pathname.slice("/art/".length),file=files.get(filename);
        assert(file,"Image missing from publication: "+image[field]);
        const format=field==="src"?"webp":"avif";
        assert.equal(filename,`assets/${artwork.id}-${image.edge}.${format}`,"Image must belong to this artwork and size");
        assert.equal(image[field],filename+"?v="+file.sha256.slice(0,12),"Use relative artwork image URLs with one revision query");
        assert.equal(url.searchParams.get("v"),file.sha256.slice(0,12));
        referenced.add(filename);
      }
    }
  }
  assert.equal(referenced.size,files.size,"Only referenced public images belong in a publication");
}
export const publicationId=(catalog,manifest)=>digest(JSON.stringify({catalog,manifest})).slice(0,16);
