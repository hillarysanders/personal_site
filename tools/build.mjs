/** Build exclusively from public tracked source; no local database or photo processing. */
import fs from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {validatePublication} from "./publication-schema.mjs";
import {renderHtml} from "./html.mjs";

export const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const config=JSON.parse(await fs.readFile(path.join(root,"config/paths.json"),"utf8"));
export const source=path.resolve(root,config.site),output=path.resolve(root,config.output),local=path.resolve(root,config.local);
export const readJSON=async filename=>JSON.parse(await fs.readFile(filename,"utf8"));

export async function build({withImages=false}={}) {
  if(!output.startsWith(root+path.sep)||[source,local,path.resolve(root,config.library)].some(directory=>directory===output||directory.startsWith(output+path.sep)||output.startsWith(directory+path.sep)))throw new Error("Build output must be a separate directory inside this repository, outside source and private data");
  const catalog=await readJSON(path.join(source,"art/catalog.json"));
  const images=await readJSON(path.join(source,"art/images.json"));
  validatePublication(catalog,images);
  const navigation=await fs.readFile(path.join(source,"_includes/nav.html"),"utf8");
  await fs.rm(output,{recursive:true,force:true});
  await fs.mkdir(output,{recursive:true});
  async function copy(directory,relative="") {
    for(const entry of await fs.readdir(directory,{withFileTypes:true})) {
      const name=path.posix.join(relative,entry.name);
      if(entry.name.startsWith("_")||(entry.name.startsWith(".")&&entry.name!==".htaccess")||["art/catalog.json","art/images.json","art/assets"].includes(name))continue;
      const origin=path.join(directory,entry.name),target=path.join(output,name);
      if(entry.isDirectory()) {await fs.mkdir(target,{recursive:true});await copy(origin,name);}
      else if(entry.isFile()) {
        if(path.extname(name)===".html") {
          const html=renderHtml(await fs.readFile(origin,"utf8"),navigation,catalog.site);
          await fs.writeFile(target,html);
        } else await fs.copyFile(origin,target);
      } else throw new Error("Unexpected non-file in public source: "+name);
    }
  }
  await copy(source);
  const redirects=await readJSON(path.join(root,"config/redirects.json"));
  const redirectRules=Object.entries(redirects).map(([from,to])=>`RedirectMatch 301 ^${from.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")}$ ${to}`);
  await fs.appendFile(path.join(output,".htaccess"),"\n# Retired pages: keep old links pointing at the current collection.\n"+redirectRules.join("\n")+"\n");
  await fs.writeFile(path.join(output,"art/data.json"),JSON.stringify(catalog)+"\n");
  await fs.copyFile(path.join(source,"art/images.json"),path.join(output,"art/images.json"));
  if(withImages) {
    const staging=path.join(local,"publication/images/art");
    for(const image of images.files) {
      const target=path.join(output,"art",image.path);
      await fs.mkdir(path.dirname(target),{recursive:true});
      await fs.copyFile(path.join(staging,image.path),target);
    }
  }
  return {output,artworks:catalog.artworks.length,images:images.files.length};
}
if(process.argv[1]&&process.argv[1]!=="-"&&await fs.realpath(process.argv[1])===fileURLToPath(import.meta.url)) console.log(await build({withImages:process.argv.includes("--with-images")}));
