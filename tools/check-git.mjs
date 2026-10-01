/** Check tracked and pending files before a commit; large/private files must stay local. */
import fs from "node:fs/promises";
import path from "node:path";
import {execFileSync} from "node:child_process";
import {fileURLToPath} from "node:url";
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const policy=JSON.parse(await fs.readFile(path.join(root,"config/git-policy.json"),"utf8"));
const files=execFileSync("git",["ls-files","--cached","--others","--exclude-standard","-z"],{cwd:root,encoding:"utf8"}).split("\0").filter(Boolean);
const failures=[];
for(const name of new Set(files)) {
  let stat;
  try {stat=await fs.stat(path.join(root,name));}catch(error){if(error.code==="ENOENT")continue;throw error;}
  if(/(^|\/)(\.local|\.env(?:\..*)?|dist|node_modules|\.cache|raw|output)(\/|$)|catalog-seed\.json$|\.(nef|tiff?|sqlite[^/]*|db|avif|webp)$/i.test(name))failures.push(name+": private/generated asset");
  if(stat.size>policy.max_file_bytes&&!policy.allowed_large_files.includes(name))failures.push(name+": exceeds Git file-size policy");
}
if(failures.length)throw new Error("Keep these files out of Git:\n"+failures.join("\n"));
console.log("Git boundary passed: no private catalog, generated artwork images, or unexpected large files.");
