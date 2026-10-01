import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {execFileSync} from "node:child_process";
import {fileURLToPath} from "node:url";
import {validatePublication,publicationId} from "../tools/publication-schema.mjs";
import {picture} from "../site/art/images.mjs";

const root=fileURLToPath(new URL("../",import.meta.url));
const catalog=JSON.parse(await fs.readFile(new URL("../site/art/catalog.json",import.meta.url),"utf8"));
const images=JSON.parse(await fs.readFile(new URL("../site/art/images.json",import.meta.url),"utf8"));

test("published records reference one current filename per size and format",()=>{
  validatePublication(catalog,images);
  assert.equal(new Set(images.files.map(file=>file.path)).size,images.files.length);
  assert(images.files.every(file=>!/-[a-f0-9]{12}\./.test(file.path)));
  const markup=picture(catalog.artworks[0],{sizes:"300px",maxEdge:900});
  assert.match(markup,/type="image\/avif"/);assert.match(markup,/\?v=[a-f0-9]{12}/);
});
test("public boundary rejects notes, editor state, and missing photos",()=>{
  const leaked=structuredClone(catalog);leaked.artworks[0].notes="Private note";
  assert.throws(()=>validatePublication(leaked,images),/Unexpected\/private/);
  const admin=structuredClone(catalog);admin.site.canAdmin=true;
  assert.throws(()=>validatePublication(admin,images),/local editor/);
  const privateManifest=structuredClone(images);privateManifest.files[0].source="private-library/photo.NEF";
  assert.throws(()=>validatePublication(catalog,privateManifest),/private image metadata/);
  assert.throws(()=>validatePublication(catalog,{...images,files:images.files.slice(1)}),/Image missing/);
});
test("an empty local collection prepares correctly and status detects a changed Git snapshot",async()=>{
  const isolated=await fs.mkdtemp(path.join(os.tmpdir(),"art-empty-publication-"));
  try {
    for(const directory of ["site","config","tools/editor"])await fs.cp(path.join(root,directory),path.join(isolated,directory),{recursive:true});
    for(const name of ["publication.mjs","publication-schema.mjs"])await fs.copyFile(path.join(root,"tools",name),path.join(isolated,"tools",name));
    const settings=JSON.parse(await fs.readFile(path.join(isolated,"config/paths.json"),"utf8"));settings.library="library";
    await fs.writeFile(path.join(isolated,"config/paths.json"),JSON.stringify(settings));
    await fs.mkdir(path.join(isolated,".local"));await fs.mkdir(path.join(isolated,"library/output/web"),{recursive:true});
    await fs.writeFile(path.join(isolated,".local/catalog-seed.json"),'{"artworks":[]}');
    await fs.writeFile(path.join(isolated,"library/output/web/manifest.json"),'{}');
    const run=command=>execFileSync(process.execPath,[path.join(isolated,"tools/publication.mjs"),command],{cwd:os.tmpdir(),encoding:"utf8",stdio:["ignore","pipe","pipe"]});
    run("prepare");
    const prepared=JSON.parse(await fs.readFile(path.join(isolated,".local/publication/prepared.json"),"utf8"));assert.equal(prepared.artworks,0);assert.equal(prepared.images,0);
    assert.match(run("status"),/state: 'prepared'/);
    const filename=path.join(isolated,"site/art/catalog.json"),changed=JSON.parse(await fs.readFile(filename,"utf8"));changed.site.site_title="A different Git snapshot";
    await fs.writeFile(filename,JSON.stringify(changed));assert.match(run("status"),/Public snapshot changed/);
  }finally{await fs.rm(isolated,{recursive:true,force:true});}
});
test("publication identity changes for a catalog edit without changing any photo paths",()=>{
  const edited=structuredClone(catalog);edited.artworks[0].title+=" revised";
  assert.notEqual(publicationId(catalog,images),publicationId(edited,images));
  assert.deepEqual(edited.artworks[0].images,catalog.artworks[0].images);
});
test("clean public checkout builds without a private database or image library",async()=>{
  const isolated=await fs.mkdtemp(path.join(os.tmpdir(),"art-static-build-"));
  try {
    for(const directory of ["site","config"])await fs.cp(path.join(root,directory),path.join(isolated,directory),{recursive:true});
    await fs.mkdir(path.join(isolated,"tools"));
    for(const name of ["build.mjs","html.mjs","publication-schema.mjs"])await fs.copyFile(path.join(root,"tools",name),path.join(isolated,"tools",name));
    await fs.copyFile(path.join(root,"package.json"),path.join(isolated,"package.json"));
    execFileSync(process.execPath,[path.join(isolated,"tools/build.mjs")],{cwd:os.tmpdir(),stdio:"pipe"});
    const output=path.join(isolated,"dist"),files=await fs.readdir(output,{recursive:true});
    for(const file of files)assert(!/(\.local|admin|\.sqlite|catalog-seed|\.NEF|\.tiff?$)/i.test(file),file);
    assert(files.includes("art/data.json"));assert(files.includes("resume.html"));assert(files.includes("art/.htaccess"));
    const html=await fs.readFile(path.join(output,"art/index.html"),"utf8");
    assert(html.includes('href="/art/"'));assert(!html.includes("<!-- SITE_NAV -->"));
    const headers=await fs.readFile(path.join(output,"art/.htaccess"),"utf8");
    assert(headers.includes("must-revalidate"));assert(!headers.includes("immutable"));
  }finally{await fs.rm(isolated,{recursive:true,force:true});}
});
