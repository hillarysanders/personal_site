/** Two explicit operations: upload current photos locally, deploy public code/catalog from Git. */
import fs from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {spawn} from "node:child_process";
import {build,root,local,source,output,readJSON} from "./build.mjs";
import {digest,validatePublication,publicationId} from "./publication-schema.mjs";

const quote=value=>"'"+value.replaceAll("'","'\\''")+"'";
const run=(command,args,options={})=>new Promise((resolve,reject)=>{
  const child=spawn(command,args,{stdio:"inherit",...options});
  child.on("error",reject);child.on("exit",code=>code===0?resolve():reject(new Error(command+" exited "+code)));
});
async function deploymentConfig() {
  const filename=process.env.SITE_DEPLOY_CONFIG||path.join(local,"deploy.json");
  const config=await readJSON(filename);
  if(!/^[a-zA-Z0-9][a-zA-Z0-9.-]*$/.test(config.host)||!/^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$/.test(config.user))throw new Error("Invalid SSH host/user");
  if(!/^\/[a-zA-Z0-9_./-]+$/.test(config.root)||config.root==="/"||config.root.includes(".."))throw new Error("Use an explicit absolute public directory");
  const url=new URL(config.url);
  if(url.protocol!=="https:"||url.pathname!=="/"||url.username||url.password||url.search||url.hash)throw new Error("Expected the HTTPS site origin");
  return config;
}
async function verifyImages(config,manifest,{content=false}={}) {
  // A code release only needs current photos at stable URLs. Photo replacement
  // is independent of catalog merges; old manifests never pin old hosted bytes.
  let next=0;
  await Promise.all(Array.from({length:4},async()=>{
    while(next<manifest.files.length) {
      const file=manifest.files[next++];
      const url=new URL("art/"+file.path,config.url);
      url.searchParams.set("verify",file.sha256);
      const response=await fetch(url,{method:content?"GET":"HEAD",signal:AbortSignal.timeout(30000),cache:"no-store"});
      if(!response.ok)throw new Error("Image not uploaded: "+file.path+" ("+response.status+")");
      if(content) {
        const bytes=Buffer.from(await response.arrayBuffer());
        if(bytes.length!==file.bytes||digest(bytes)!==file.sha256)throw new Error("Hosted image upload verification failed: "+file.path);
      }
    }
  }));
}
async function publication() {
  const catalog=await readJSON(path.join(source,"art/catalog.json")),images=await readJSON(path.join(source,"art/images.json"));
  validatePublication(catalog,images);
  return {catalog,images,id:publicationId(catalog,images)};
}
export async function deploy(command) {
  const config=await deploymentConfig(),snapshot=await publication();
  // Pin the independently verified host key per project, including in CI.
  const knownHosts=path.resolve(root,config.known_hosts);
  await fs.access(knownHosts);
  const sshOptions=["-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","UserKnownHostsFile="+knownHosts];
  const remote=config.user+"@"+config.host,transport="ssh "+sshOptions.map(quote).join(" ");
  if(command==="images") {
    const staging=path.join(local,"publication/images/art");
    // A later draft must never replace the photos belonging to the prepared snapshot.
    for(const file of snapshot.images.files) {
      const bytes=await fs.readFile(path.join(staging,file.path));
      if(digest(bytes)!==file.sha256)throw new Error("Prepare this publication again: "+file.path);
    }
    const list=path.join(local,"publication/image-files.txt");
    await fs.writeFile(list,snapshot.images.files.map(file=>file.path).join("\n")+"\n");
    await run("ssh",[...sshOptions,remote,"mkdir -p "+quote(config.root+"/art/assets")]);
    await run("rsync",["-rt","--checksum","--itemize-changes","--files-from="+list,"-e",transport,staging+"/",remote+":"+config.root+"/art/"]);
    await verifyImages(config,snapshot.images,{content:true});
    console.log("Current photos uploaded and verified. Commit/review the catalog snapshot; merge publishes it.");
  } else if(command==="site") {
    await verifyImages(config,snapshot.images);
    await build();
    // No --delete: this host also contains older photos/assets absent from Git.
    // Images are overwritten separately; only small code/catalog files are deployed here.
    await run("rsync",["-rt","--checksum","--itemize-changes","--exclude=/art/assets/","--exclude=/art/data.json","--exclude=/art/images.json","-e",transport,output+"/",remote+":"+config.root+"/"]);
    await run("rsync",["-rt","--checksum","-e",transport,path.join(output,"art/data.json"),path.join(output,"art/images.json"),remote+":"+config.root+"/art/"]);
    const response=await fetch(new URL("art/data.json?verify="+snapshot.id,config.url),{signal:AbortSignal.timeout(30000),cache:"no-store"});
    if(!response.ok||JSON.stringify(await response.json())!==JSON.stringify(snapshot.catalog))throw new Error("Live catalog verification failed");
    const receipt={id:snapshot.id,publishedAt:new Date().toISOString(),commit:process.env.GITHUB_SHA||null};
    await fs.writeFile(path.join(output,"art/release.json"),JSON.stringify(receipt)+"\n");
    await run("rsync",["-rt","-e",transport,path.join(output,"art/release.json"),remote+":"+config.root+"/art/"]);
    console.log("Published "+snapshot.id+" at "+new URL("art/",config.url));
  } else throw new Error("Use images or site");
}
if(process.argv[1]&&process.argv[1]!=="-"&&await fs.realpath(process.argv[1])===fileURLToPath(import.meta.url))await deploy(process.argv[2]);
