/** Freeze local edits into a public catalog. This command never uploads or commits. */
import fs from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {paths,openCatalog,resolvedCatalog,publicCatalog,imageManifest} from "./editor/catalog.mjs";
import {digest,validatePublication,publicationId} from "./publication-schema.mjs";

export async function draftPublication() {
  const db=openCatalog();
  let catalog;
  try {catalog=publicCatalog(resolvedCatalog(db));} finally {db.close();}
  const manifest=imageManifest(),files=[],sources=[];
  for(const art of catalog.artworks)for(const variant of manifest[art.id])for(const [field,format] of [["file","webp"],["avif_file","avif"]]) {
    const source=path.join(paths.library,"output/web",path.basename(variant[field]));
    const bytes=await fs.readFile(source),sha256=digest(bytes);
    if(!path.basename(source).includes(sha256.slice(0,12)))throw new Error("Changed/corrupt derivative: "+source);
    const target=`assets/${art.id}-${variant.target_edge}.${format}`;
    files.push({path:target,sha256,bytes:bytes.length});sources.push({source,target});
  }
  const images={version:1,files:files.sort((left,right)=>left.path.localeCompare(right.path))};
  validatePublication(catalog,images);
  return {catalog,images,sources,id:publicationId(catalog,images)};
}

export async function preparePublication() {
  const draft=await draftPublication();
  const staging=path.join(paths.local,"publication/images/art");
  await fs.mkdir(staging,{recursive:true});
  for(const {source,target} of draft.sources) {
    const destination=path.join(staging,target);
    await fs.mkdir(path.dirname(destination),{recursive:true});await fs.copyFile(source,destination);
  }
  for(const [name,value] of [["catalog",draft.catalog],["images",draft.images]]) {
    const filename=path.join(paths.site,"art",name+".json");
    await fs.writeFile(filename+".tmp",JSON.stringify(value,null,2)+"\n");await fs.rename(filename+".tmp",filename);
  }
  const summary={id:draft.id,artworks:draft.catalog.artworks.length,images:draft.images.files.length,bytes:draft.images.files.reduce((sum,image)=>sum+image.bytes,0)};
  await fs.writeFile(path.join(paths.local,"publication/prepared.json"),JSON.stringify(summary,null,2)+"\n");
  return summary;
}

export async function publicationStatus() {
  const draft=await draftPublication();
  let prepared;
  try {prepared=JSON.parse(await fs.readFile(path.join(paths.local,"publication/prepared.json"),"utf8"));}
  catch(error) {if(error.code!=="ENOENT")throw error;return {state:"unpublished",message:"Saved locally · no publication prepared",preparedId:null};}
  if(prepared.id!==draft.id)return {state:"unpublished",message:"Saved locally · unpublished changes",preparedId:prepared.id};
  const [catalog,images]=await Promise.all(["catalog","images"].map(async name=>JSON.parse(await fs.readFile(path.join(paths.site,"art",name+".json"),"utf8"))));
  if(publicationId(catalog,images)!==prepared.id)return {state:"unpublished",message:"Public snapshot changed · prepare again to include local edits",preparedId:prepared.id};
  return {state:"prepared",message:"Publication prepared locally · live status not checked",preparedId:prepared.id};
}
if(process.argv[1]&&process.argv[1]!=="-"&&await fs.realpath(process.argv[1])===fileURLToPath(import.meta.url)) {
  const command=process.argv[2];
  if(!["prepare","status"].includes(command))throw new Error("Use prepare or status");
  console.log(await (command==="prepare"?preparePublication():publicationStatus()));
}
