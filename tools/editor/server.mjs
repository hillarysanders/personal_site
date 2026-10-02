/** Loopback-only editor. Only the public site tree and explicit local photo routes are served. */
import fs from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {paths,siteConfig,openCatalog,resolvedCatalog,saveArtwork,publicCatalog,catalogCsv,imageManifest,InputError} from "./catalog.mjs";
import {preparePublication,publicationStatus} from "../publication.mjs";
import {renderHtml} from "../html.mjs";

const editor=fileURLToPath(new URL("./",import.meta.url));
const redirects=JSON.parse(await fs.readFile(new URL("../../config/redirects.json",import.meta.url),"utf8"));
const types={".html":"text/html; charset=utf-8",".css":"text/css; charset=utf-8",".js":"text/javascript; charset=utf-8",".mjs":"text/javascript; charset=utf-8",".json":"application/json; charset=utf-8",".svg":"image/svg+xml",".webp":"image/webp",".avif":"image/avif",".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",".ico":"image/x-icon",".woff2":"font/woff2",".woff":"font/woff",".ttf":"font/ttf",".pdf":"application/pdf"};
const reply=(body,status=200,headers={})=>new Response(body,{status,headers:{"Cache-Control":"no-store","X-Content-Type-Options":"nosniff",...headers}});
const json=(body,status=200)=>reply(JSON.stringify(body),status,{"Content-Type":types[".json"]});
const inside=(root,filename)=>filename.startsWith(root+path.sep);

async function file(filename,root) {
  const real=await fs.realpath(filename);
  if(!inside(await fs.realpath(root),real))throw new InputError("Not found.",404);
  let body=await fs.readFile(real);
  if(path.extname(real)===".html")body=renderHtml(body.toString(),await fs.readFile(path.join(paths.site,"_includes/nav.html"),"utf8"),siteConfig());
  return reply(body,200,{"Content-Type":types[path.extname(real)]||"application/octet-stream"});
}

/** Dependencies can be supplied by route tests without a private library or database. */
export function createHandler(db,{catalogInputs,publication={preparePublication,publicationStatus}}={}) {
  const catalog=()=>resolvedCatalog(db,catalogInputs);
  return async request=>{
    try {
      const url=new URL(request.url),pathname=decodeURIComponent(url.pathname);
      if(!["127.0.0.1","localhost"].includes(url.hostname))throw new InputError("This editor is only available on localhost.",403);
      if(!["GET","HEAD"].includes(request.method)) {
        if(request.headers.get("Origin")!==url.origin)throw new InputError("Open the editor on this local address before saving.",403);
        if(request.headers.get("Content-Type")?.split(";")[0]!=="application/json")throw new InputError("Send JSON artwork details.",415);
      }
      if(pathname==="/api/admin/catalog"&&request.method==="GET")return json({artworks:catalog()});
      const edit=pathname.match(/^\/api\/admin\/artworks\/(art-\d+)$/);
      if(edit&&request.method==="PATCH") {
        let body;
        try {body=await request.json();}catch {throw new InputError("Invalid JSON.");}
        const artwork=saveArtwork(db,edit[1],body,catalogInputs);
        return json({artwork,artworks:catalog()});
      }
      if(pathname==="/api/admin/export"&&request.method==="GET")return reply(catalogCsv(catalog()),200,{"Content-Type":"text/csv; charset=utf-8","Content-Disposition":'attachment; filename="local-artwork-catalog.csv"'});
      if(pathname==="/api/publication/status"&&request.method==="GET")return json(await publication.publicationStatus());
      if(pathname==="/api/publication/prepare"&&request.method==="POST")return json(await publication.preparePublication());
      if(!["GET","HEAD"].includes(request.method))throw new InputError("Not found.",404);
      if(Object.hasOwn(redirects,pathname))return reply(null,301,{Location:redirects[pathname]+url.search});
      if(["/art/data.json","/art/catalog.json"].includes(pathname)) {
        const draft=publicCatalog(catalog());draft.site.canAdmin=true;return json(draft);
      }
      if(["/admin","/art"].includes(pathname))return reply(null,302,{Location:pathname+"/"+url.search});
      if(pathname==="/admin/")return await file(path.join(editor,"admin.html"),editor);
      if(/^\/admin\/(admin\.(css|js)|review\.mjs)$/.test(pathname))return await file(path.join(editor,path.basename(pathname)),editor);
      const reference=pathname.match(/^\/admin-photos\/(art-\d+\.jpg)$/);
      if(reference)return await file(path.join(paths.local,"reference-photos",reference[1]),path.join(paths.local,"reference-photos"));
      const image=pathname.match(/^\/art\/assets\/(art-\d+)-(\d+)\.(webp|avif)$/);
      if(image) {
        const manifest=imageManifest(),record=manifest[image[1]]?.find(record=>record.target_edge===Number(image[2]));
        if(!record)throw new InputError("Image not found.",404);
        // The revision query busts caches; stable image paths always serve the current export.
        const field=image[3]==="webp"?"file":"avif_file";
        const directory=path.join(paths.library,"output/web");
        return await file(path.join(directory,path.basename(record[field])),directory);
      }
      const filename=path.resolve(paths.site,"."+pathname+(pathname.endsWith("/")?"index.html":""));
      if(!inside(paths.site,filename))throw new InputError("Not found.",404);
      return await file(filename,paths.site);
    }catch(error) {
      if(error.code==="ENOENT"||error.code==="ENOTDIR")return json({error:"Not found."},404);
      if(error instanceof InputError)return json({error:error.message},error.status);
      console.error(error);return json({error:error.message},500);
    }
  };
}

export function createEditorServer(db=openCatalog()) {
  const handle=createHandler(db);
  const server=http.createServer(async(incoming,outgoing)=>{
    try {
      const chunks=[];
      for await(const chunk of incoming)chunks.push(chunk);
      const request=new Request("http://"+incoming.headers.host+incoming.url,{method:incoming.method,headers:incoming.headers,...(["GET","HEAD"].includes(incoming.method)?{}:{body:Buffer.concat(chunks)})});
      const response=await handle(request);
      outgoing.writeHead(response.status,Object.fromEntries(response.headers));
      outgoing.end(incoming.method==="HEAD"?undefined:Buffer.from(await response.arrayBuffer()));
    }catch(error){console.error(error);outgoing.writeHead(500);outgoing.end("Local editor request failed.");}
  });
  server.on("close",()=>db.close());
  return server;
}

if(process.argv[1]===fileURLToPath(import.meta.url)) {
  const port=process.env.PORT===undefined?8767:Number(process.env.PORT);
  if(!Number.isInteger(port)||port<1||port>65535)throw new Error("PORT must be an integer from 1 to 65535");
  createEditorServer().listen(port,"127.0.0.1",()=>console.log(`Local editor: http://127.0.0.1:${port}/admin/\nDraft gallery: http://127.0.0.1:${port}/art/`));
}
