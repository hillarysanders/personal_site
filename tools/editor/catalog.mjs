/** Local catalog state: imported defaults + durable edits, with current image exports. */
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {DatabaseSync} from "node:sqlite";
import {sortArtworks} from "../../site/art/gallery.mjs";
import {PUBLIC_FIELDS} from "../publication-schema.mjs";
export {PUBLIC_FIELDS} from "../publication-schema.mjs";

const root=fileURLToPath(new URL("../../",import.meta.url));
const readJson=filename=>JSON.parse(fs.readFileSync(filename,"utf8"));
export const paths={root,...Object.fromEntries(Object.entries(readJson(path.join(root,"config/paths.json"))).map(([key,value])=>[key,path.resolve(root,value)]))};
export const siteConfig=()=>readJson(path.join(root,"config/site.json"));
export const imageManifest=()=>readJson(path.join(paths.library,"output/web/manifest.json"));
const seedCatalog=()=>readJson(path.join(paths.local,"catalog-seed.json"));
export const EDITABLE=["title","description","themes","period","year","medium","surface","width","height","dimensionsConfirmed","sizeCategory","price","currency","availability","published","photoStatus","order","purchaseUrl","notes"];
export class InputError extends Error {
  constructor(message,status=400){super(message);this.status=status;}
}

/** Reuse the original migration ledger so copying a working database never reseeds it. */
export function openCatalog(filename=path.join(paths.local,"catalog.sqlite")) {
  if(filename!==":memory:")fs.mkdirSync(path.dirname(filename),{recursive:true});
  const db=new DatabaseSync(filename);
  db.exec("PRAGMA foreign_keys=ON; CREATE TABLE IF NOT EXISTS local_migrations (name TEXT PRIMARY KEY)");
  const directory=fileURLToPath(new URL("./migrations/",import.meta.url));
  for(const name of fs.readdirSync(directory).filter(name=>name.endsWith(".sql")).sort()){
    if(db.prepare("SELECT name FROM local_migrations WHERE name=?").get(name))continue;
    db.exec("BEGIN");
    try {
      db.exec(fs.readFileSync(path.join(directory,name),"utf8"));
      db.prepare("INSERT INTO local_migrations VALUES (?)").run(name);
      db.exec("COMMIT");
    }catch(error){db.exec("ROLLBACK");db.close();throw error;}
  }
  return db;
}

/** Stable delivery filenames carry a content revision; TIFFs/hashed source history stay local. */
export function imageVariants(id,records) {
  const url=(record,field,format)=>{
    const match=path.basename(record[field]).match(/^(art-\d+)-(\d+)-([a-f0-9]{12})\.(webp|avif)$/);
    if(!match||match[1]!==id||Number(match[2])!==record.target_edge||match[4]!==format)throw new Error("Invalid image export: "+record[field]);
    return `assets/${id}-${record.target_edge}.${format}?v=${match[3]}`;
  };
  return records.map(record=>({src:url(record,"file","webp"),avif:url(record,"avif_file","avif"),width:record.width,height:record.height,edge:record.target_edge}));
}

const sizeCategory=(art,config)=>art.width===null||art.height===null?art.sizeCategory:Math.max(art.width,art.height)<config.size_limits.small_under_in?"Small":Math.max(art.width,art.height)<=config.size_limits.medium_up_to_in?"Medium":"Large";
/** Older saved single-category documents retain the other seeded categories. */
function categoryValues(values,original,config) {
  const category=name=>config.category_aliases[name]||name;
  if(Object.hasOwn(values,"themes"))return Array.isArray(values.themes)?{...values,themes:values.themes.map(category)}:values;
  if(!Object.hasOwn(values,"theme"))return values;
  const {theme:oldTheme,...rest}=values,theme=category(oldTheme);
  if(typeof theme!=="string")throw new InputError("Invalid category.");
  return {...rest,themes:[theme,...original.themes.filter(item=>item!==original.theme&&item!==theme)].filter(Boolean)};
}

/** Read seed and exports each time, so new local image versions appear without a restart. */
export function resolvedCatalog(db,{seed=seedCatalog(),manifest=imageManifest(),config=siteConfig()}={}) {
  const edits=new Map(db.prepare("SELECT artwork_id,document,revision,updated_at FROM artwork_edits").all().map(row=>[row.artwork_id,row]));
  const membership=new Map(db.prepare("SELECT artwork_id,series_id,position,title FROM series_members JOIN artwork_series ON series_id=artwork_series.id").all().map(member=>[member.artwork_id,member]));
  const artworks=seed.artworks.map(original=>{
    const edit=edits.get(original.id),member=membership.get(original.id);
    const art=edit?{...original,...categoryValues(JSON.parse(edit.document),original,config),revision:edit.revision,updatedAt:edit.updated_at}:{...original};
    if(original.images.length&&!Object.hasOwn(manifest,art.id))throw new Error("Finished artwork is missing from the image manifest: "+art.id);
    const images=Object.hasOwn(manifest,art.id)?imageVariants(art.id,manifest[art.id]):[];
    return {...art,images,referenceImage:images.length?null:original.referenceImage,theme:art.themes[0]||"",sizeCategory:sizeCategory(art,config),
      seriesId:member?member.series_id:"",seriesTitle:member?member.title:"",seriesPosition:member?member.position:0};
  });
  const orders=new Map();
  for(const art of artworks)if(art.seriesId)orders.set(art.seriesId,Math.min(orders.get(art.seriesId)??Infinity,art.order));
  return sortArtworks(artworks.map(art=>art.seriesId?{...art,order:orders.get(art.seriesId)}:art));
}

export function validate(values,original) {
  if(!values||Array.isArray(values)||typeof values!=="object")throw new InputError("Artwork details are required.");
  const config=siteConfig();
  values=categoryValues(values,original,config);
  if(Object.keys(values).length!==EDITABLE.length||EDITABLE.some(key=>!Object.hasOwn(values,key)))throw new InputError("Incomplete or unknown artwork fields.");
  for(const field of ["title","description","period","year","medium","surface","currency","availability","sizeCategory","photoStatus","purchaseUrl","notes"]){
    if(typeof values[field]!=="string"||values[field].length>(["description","notes"].includes(field)?4000:field==="purchaseUrl"?2000:180))throw new InputError("Invalid "+field+".");
  }
  if(!Array.isArray(values.themes)||values.themes.length>20||new Set(values.themes).size!==values.themes.length||values.themes.some(theme=>typeof theme!=="string"||!theme.trim()||theme!==theme.trim()||theme.length>180||theme.includes(";")))throw new InputError("Choose distinct, nonempty categories (up to 20).");
  for(const field of ["published","dimensionsConfirmed"])if(typeof values[field]!=="boolean")throw new InputError("Invalid "+field+".");
  for(const field of ["width","height","price"])if(values[field]!==null&&(typeof values[field]!=="number"||!Number.isFinite(values[field])||values[field]<0||(field!=="price"&&values[field]===0)))throw new InputError("Enter a valid "+field+".");
  if((values.width===null)!==(values.height===null))throw new InputError("Enter both dimensions, or leave both blank.");
  if(values.dimensionsConfirmed&&values.width===null)throw new InputError("Confirmed measurements need width and height.");
  if(!Number.isInteger(values.order)||values.order<0)throw new InputError("Display order must be a positive whole number or zero.");
  for(const [field,allowed] of Object.entries({availability:["","available","private","sold"],photoStatus:["ready","review","needs_photo"],sizeCategory:["Small","Medium","Large","Unclassified"]}))if(!allowed.includes(values[field]))throw new InputError("Invalid "+field+".");
  if(!/^[A-Z]{3}$/.test(values.currency))throw new InputError("Use a three-letter currency code, such as USD.");
  if(values.published&&!original.images.length)throw new InputError("This artwork needs a finished photo before it can be shown.");
  if(values.purchaseUrl){
    let url;
    try{url=new URL(values.purchaseUrl);}catch{throw new InputError("Enter a complete HTTPS purchase link.");}
    if(url.protocol!=="https:"||url.username||url.password)throw new InputError("Purchase links must use HTTPS.");
  }
  return {...values,sizeCategory:sizeCategory(values,config)};
}

/** The existing SQLite triggers move companion series members in the same statement. */
export function saveArtwork(db,id,body,inputs) {
  if(!body||typeof body!=="object"||Array.isArray(body))throw new InputError("Artwork details are required.");
  const original=resolvedCatalog(db,inputs).find(art=>art.id===id);
  if(!original)throw new InputError("Artwork not found.",404);
  if(!Number.isInteger(body.revision)||body.revision<0)throw new InputError("A revision is required.");
  if(body.revision!==original.revision)throw new InputError("This artwork changed in another session. Reload its saved details before trying again.",409);
  const values=validate(body.values,original),revision=original.revision+1,updatedAt=new Date().toISOString();
  const result=db.prepare("INSERT INTO artwork_edits (artwork_id,document,revision,updated_at,updated_by) VALUES (?,?,?,?,?) ON CONFLICT(artwork_id) DO UPDATE SET document=excluded.document,revision=excluded.revision,updated_at=excluded.updated_at,updated_by=excluded.updated_by WHERE artwork_edits.revision=?")
    .run(id,JSON.stringify(values),revision,updatedAt,"local-editor",body.revision);
  if(result.changes===0)throw new InputError("Another edit was saved first. Reload this artwork before trying again.",409);
  return resolvedCatalog(db,inputs).find(art=>art.id===id);
}

/** This is the only catalog projection suitable for a publication snapshot. */
export function publicCatalog(artworks) {
  const config=siteConfig();
  const site=Object.fromEntries(["artist_name","site_title","inquiry_email","category_aliases","copyright_owner","gallery_image_max_edge"].map(field=>[field,config[field]]));
  return {site:{...site,canAdmin:false},artworks:sortArtworks(artworks.filter(art=>art.published&&art.images.length)).map(art=>Object.fromEntries(PUBLIC_FIELDS.map(field=>[field,art[field]])))};
}

export function catalogCsv(artworks) {
  const columns=["artwork_id",...EDITABLE,"seriesId","seriesTitle","seriesPosition","qualityNotes","revision"];
  const quote=value=>'"'+String(value??"").replaceAll('"','""')+'"';
  const rows=artworks.map(art=>columns.map(key=>key==="artwork_id"?art.id:key==="themes"?art.themes.join("; "):art[key]));
  return [columns,...rows].map(row=>row.map(quote).join(",")).join("\r\n")+"\r\n";
}
