import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {test} from "node:test";
import {EDITABLE,PUBLIC_FIELDS,openCatalog,resolvedCatalog,saveArtwork,publicCatalog,imageVariants,catalogCsv} from "../tools/editor/catalog.mjs";
import {createHandler} from "../tools/editor/server.mjs";

// The editor and migrations must work in CI without .local or a photo library.
const record=(id,edge,hash="111111111111")=>({target_edge:edge,width:edge*3/4,height:edge,file:`images/output/web/${id}-${edge}-${hash}.webp`,avif_file:`images/output/web/${id}-${edge}-222222222222.avif`});
function fixture() {
  const art=(id,order,finished=true)=>({id,title:id,description:"Fixture",theme:"Figures",themes:["Figures","Abstract"],period:"",year:"",medium:"Oil",surface:"Canvas",width:9,height:12,dimensionsConfirmed:true,sizeCategory:"Medium",price:null,currency:"USD",availability:"private",purchaseUrl:"",order,images:finished?[{src:"obsolete.webp"}]:[],referenceImage:finished?null:`admin-photos/${id}.jpg`,published:finished,photoStatus:finished?"ready":"needs_photo",notes:"Private, quoted \"note\"",qualityNotes:"Private review",issues:["Private source note"],revision:0,seriesId:"",seriesTitle:"",seriesPosition:0});
  const seed={artworks:[art("art-013",90),art("art-008",30),art("art-100",100,false)]};
  const manifest=Object.fromEntries(seed.artworks.filter(art=>art.images.length).map(art=>[art.id,[480,900,1600,2400].map(edge=>record(art.id,edge))]));
  return {seed,manifest};
}
const values=art=>Object.fromEntries(EDITABLE.map(field=>[field,art[field]]));
const artwork=(db,inputs,id)=>resolvedCatalog(db,inputs).find(art=>art.id===id);

test("migrations preserve saved edits and series across reopen",()=>{
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),"art-editor-")),filename=path.join(directory,"catalog.sqlite");
  try {
    let db=openCatalog(filename);const inputs=fixture();
    const original=artwork(db,inputs,"art-013");
    saveArtwork(db,original.id,{revision:0,values:{...values(original),title:"Saved local title"}},inputs);
    const before=db.prepare("SELECT * FROM artwork_edits ORDER BY artwork_id").all();db.close();db=openCatalog(filename);
    assert.deepEqual(db.prepare("SELECT * FROM artwork_edits ORDER BY artwork_id").all(),before);
    assert.equal(db.prepare("SELECT count(*) AS count FROM local_migrations").get().count,3);
    assert.equal(db.prepare("SELECT count(*) AS count FROM series_members").get().count,8);
    assert.equal(artwork(db,inputs,"art-013").title,"Saved local title");db.close();
  }finally{fs.rmSync(directory,{recursive:true});}
});

test("series order updates companions atomically while preserving their metadata",()=>{
  const db=openCatalog(":memory:"),inputs=fixture();
  try {
    db.prepare("INSERT INTO artwork_edits VALUES (?,?,?,?,?)").run("art-008",JSON.stringify({title:"Companion title",notes:"Companion private notes"}),1,"earlier","test");
    const original=artwork(db,inputs,"art-013");assert.equal(original.order,30);
    const saved=saveArtwork(db,original.id,{revision:0,values:{...values(original),order:12,themes:["Wildlife","Abstract"]}},inputs);
    const companion=artwork(db,inputs,"art-008");
    assert.equal(saved.order,12);assert.equal(companion.order,12);assert.equal(companion.revision,2);
    assert.equal(companion.title,"Companion title");assert.equal(companion.notes,"Companion private notes");
    assert.deepEqual(saved.themes,["Wildlife","Abstract"]);assert.equal(saved.theme,"Wildlife");
    assert.throws(()=>saveArtwork(db,original.id,{revision:0,values:values(saved)},inputs),error=>error.status===409);
    assert.equal(artwork(db,inputs,original.id).revision,1);
  }finally{db.close();}
});

test("current image exports supersede seed paths and finished reference photos become usable",()=>{
  const db=openCatalog(":memory:"),inputs=fixture();
  try {
    const original=artwork(db,inputs,"art-013");assert.equal(original.images[0].src,"assets/art-013-480.webp?v=111111111111");
    inputs.manifest["art-013"][0]=record("art-013",480,"abcdefabcdef");
    assert.equal(artwork(db,inputs,"art-013").images[0].src,"assets/art-013-480.webp?v=abcdefabcdef");
    const unfinished=artwork(db,inputs,"art-100");
    assert.throws(()=>saveArtwork(db,unfinished.id,{revision:0,values:{...values(unfinished),published:true}},inputs),/finished photo/);
    inputs.manifest["art-100"]=[record("art-100",480)];
    const finished=artwork(db,inputs,"art-100");assert.equal(finished.referenceImage,null);
    assert.equal(saveArtwork(db,finished.id,{revision:0,values:{...values(finished),published:true}},inputs).published,true);
    delete inputs.manifest["art-013"];assert.throws(()=>resolvedCatalog(db,inputs),/missing from the image manifest/);
    assert.throws(()=>imageVariants("art-100",[record("art-013",480)]),/Invalid image export/);
  }finally{db.close();}
});

test("legacy categories survive and the public projection excludes unpublished/private data",()=>{
  const db=openCatalog(":memory:"),inputs=fixture();
  try {
    db.prepare("INSERT INTO artwork_edits VALUES (?,?,?,?,?)").run("art-013",JSON.stringify({theme:"Birds & wildlife"}),1,"earlier","test");
    const all=resolvedCatalog(db,inputs),catalog=publicCatalog(all);
    assert.deepEqual(artwork(db,inputs,"art-013").themes,["Wildlife","Abstract"]);
    assert.equal(catalog.site.canAdmin,false);assert.equal(catalog.artworks.length,2);
    for(const art of catalog.artworks)assert.deepEqual(Object.keys(art).sort(),[...PUBLIC_FIELDS].sort());
    for(const text of ["Private review","Private source note","Private, quoted","art-100"])assert(!JSON.stringify(catalog).includes(text));
    const csv=catalogCsv(all);assert(csv.includes('"Private, quoted ""note"""'));assert(csv.includes("art-100"));
  }finally{db.close();}
});

test("validation rejects incomplete, invalid and unsafe details",()=>{
  const db=openCatalog(":memory:"),inputs=fixture();
  try {
    const original=artwork(db,inputs,"art-013"),valid=values(original);
    for(const change of [{width:null},{dimensionsConfirmed:true,width:null,height:null},{order:2.2},{themes:["Figures","Figures"]},{purchaseUrl:"javascript:alert(1)"},{purchaseUrl:"https://user:pass@example.com"},{currency:"usd"},{extra:"unknown"}])
      assert.throws(()=>saveArtwork(db,original.id,{revision:0,values:{...valid,...change}},inputs),error=>error.status===400);
    const {notes,...incomplete}=valid;assert.throws(()=>saveArtwork(db,original.id,{revision:0,values:incomplete},inputs),/Incomplete/);
    assert.equal(artwork(db,inputs,original.id).revision,0);
  }finally{db.close();}
});

test("media category upgrades preserve details and explicit owner overrides",()=>{
  const db=openCatalog(":memory:"),inputs=fixture();
  inputs.seed.artworks[0].medium="Oil on plywood";
  inputs.seed.artworks[0].themes=["Still lifes"];
  try {
    const original=artwork(db,inputs,"art-013");
    assert.equal(original.mediaCategory,"Oil paintings");
    assert.deepEqual(original.themes,["Still Life"]);
    assert.throws(()=>saveArtwork(db,original.id,{revision:0,values:{...values(original),mediaCategory:"Plywood"}},inputs),/Invalid media category/);
    const saved=saveArtwork(db,original.id,{revision:0,values:{...values(original),mediaCategory:"Mixed media"}},inputs);
    assert.equal(saved.medium,"Oil on plywood");
    assert.equal(artwork(db,inputs,original.id).mediaCategory,"Mixed media");
    saveArtwork(db,original.id,{revision:saved.revision,values:{...values(saved),mediaCategory:""}},inputs);
    assert.equal(artwork(db,inputs,original.id).mediaCategory,"");
  }finally{db.close();}
});

test("loopback routes provide local drafts and reject private paths/cross-origin writes",async()=>{
  const db=openCatalog(":memory:"),inputs=fixture();let prepared=0;
  const handle=createHandler(db,{catalogInputs:inputs,publication:{publicationStatus:async()=>({state:"unpublished",message:"Saved locally"}),preparePublication:async()=>{prepared++;return {id:"fixture",artworks:2,images:16,bytes:123};}}});
  const request=(route,options={})=>handle(new Request("http://127.0.0.1:8767"+route,options));
  const mutation={method:"PATCH",headers:{"Content-Type":"application/json",Origin:"http://127.0.0.1:8767"},body:JSON.stringify({revision:0,values:{...values(artwork(db,inputs,"art-013")),title:"Saved through local API"}})};
  try {
    const draft=await (await request("/art/data.json")).json();assert.equal(draft.site.canAdmin,true);assert.equal(draft.artworks.length,2);
    const catalog=await (await request("/api/admin/catalog")).json();assert.equal(catalog.artworks.length,3);
    const admin=await request("/admin/");assert.equal(admin.status,200);assert((await admin.text()).includes("Prepare publication"));
    const gallery=await request("/art/");assert.equal(gallery.status,200);assert(!(await gallery.text()).includes("<!-- SITE_NAV -->"));
    for(const route of ["/tools/editor/catalog.mjs","/.local/catalog.sqlite","/config/paths.json","/%2e%2e%2f.local/catalog.sqlite"])
      assert.equal((await request(route)).status,404,route);
    assert.equal((await handle(new Request("http://evil.test/api/admin/catalog"))).status,403);
    assert.equal((await request("/api/admin/artworks/art-013",{...mutation,headers:{"Content-Type":"application/json"}})).status,403);
    assert.equal((await request("/api/admin/artworks/art-013",{...mutation,headers:{"Content-Type":"application/json",Origin:"https://evil.test"}})).status,403);
    assert.equal((await request("/api/admin/artworks/art-013",mutation)).status,200);
    assert.equal((await request("/api/admin/artworks/art-013",mutation)).status,409);
    assert.equal(artwork(db,inputs,"art-013").title,"Saved through local API");
    assert.equal((await request("/api/admin/export")).headers.get("Content-Type"),"text/csv; charset=utf-8");
    assert.equal((await request("/api/publication/prepare",{...mutation,method:"POST"})).status,200);assert.equal(prepared,1);
    assert.equal((await (await request("/api/publication/status")).json()).state,"unpublished");
  }finally{db.close();}
});
