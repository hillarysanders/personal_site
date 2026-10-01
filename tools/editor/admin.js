import {mediaCategories,categoryForMedium} from "/art/media.mjs";
import {escapeHtml as esc,dimensionLabel,sortArtworks} from "/art/gallery.mjs";
const query=selector=>document.querySelector(selector);
const fields=["title","description","themes","period","year","medium","mediaCategory","surface","width","height","dimensionsConfirmed","sizeCategory","price","currency","availability","published","photoStatus","order","purchaseUrl","notes"];
import {photoLabels,photoReviewNote,detailChecks,detailIssues,matchesReview} from "./review.mjs";
query("#review-filter").innerHTML='<option value="all">All Work</option><option value="attention">Anything needing review</option><option value="clear">Nothing flagged</option><optgroup label="Photos"><option value="curated">Photo review recorded</option><option value="photo">Photo needs attention</option>'+Object.entries(photoLabels).map(([value,label])=>'<option value="'+value+'">'+label+'</option>').join('')+'<option value="unfinished">Reference photos</option></optgroup><optgroup label="Artwork details"><option value="details">Artwork details need review</option>'+detailChecks.map(check=>'<option value="'+check.id+'">'+check.label+'</option>').join('')+'</optgroup>';
const form=query("#edit-form"),dialog=query("#editor");
form.elements.mediaCategory.innerHTML='<option value="">Not assigned</option>'+mediaCategories.map(category=>'<option>'+category+'</option>').join("");
form.elements.medium.addEventListener("change",()=>{
  const category=categoryForMedium(form.elements.medium.value);
  if(category)form.elements.mediaCategory.value=category;
  updateDetailReview();
});
let artworks=[],visible=[],editing=null,dirty=false,busy=false;
const selected=new Set();
async function api(url,options={}){
  const response=await fetch(url,{cache:"no-store",...options});
  const body=await response.json();
  if(!response.ok) throw new Error(body.error);
  return body;
}
function message(text,error=false){query("#admin-message").textContent=text;query("#admin-message").classList.toggle("error",error);}
// A reference photo is visible in admin without enabling publication.
function artworkPhoto(art,index){
  const src=art.images.length?"art/"+art.images[index].src:art.referenceImage;
  return src?'<img src="/'+esc(src)+'" alt="'+esc(art.description||art.title)+'" loading="lazy">':'<span class="no-photo">Photo needed</span>';
}
function values(art){return Object.fromEntries(fields.map(field=>[field,art[field]]));}
function selection(){
  query("#prepare-publication").disabled=busy;
  query("#selected-count").textContent=selected.size+" selected";
  query("#bulk-show").disabled=busy||selected.size===0;
  query("#bulk-hide").disabled=busy||selected.size===0;
  const count=visible.filter(art=>selected.has(art.id)).length;
  query("#select-visible").checked=visible.length>0&&count===visible.length;
  query("#select-visible").indeterminate=count>0&&count<visible.length;
}
function render(){
  artworks=sortArtworks(artworks);
  const search=query("#admin-search").value.trim().toLowerCase();
  const visibility=query("#visibility-filter").value,review=query("#review-filter").value,sale=query("#sale-filter").value;
  visible=artworks.filter(art=>
    [art.title,art.id,art.description,art.notes,...art.themes].join(" ").toLowerCase().includes(search)&&
    (visibility==="all"||(visibility==="shown")===art.published)&&
    matchesReview(art,review)&&
    (sale==="all"||(sale==="unassigned"?!art.availability:art.availability===sale)));
  query("#admin-count").textContent=visible.length+" of "+artworks.length+" artworks · "+artworks.filter(art=>art.published).length+" included in the draft";
  query("#admin-grid").innerHTML=visible.map(art=>'<article class="admin-card"><label class="card-select"><input type="checkbox" data-select="'+art.id+'" aria-label="Select '+esc(art.title||art.id)+'" '+(selected.has(art.id)?"checked":"")+'></label><button class="admin-image" data-edit="'+art.id+'" aria-label="Edit '+esc(art.title||art.id)+'">'+artworkPhoto(art,0)+'</button><p class="admin-card-id">'+art.id.toUpperCase()+(dimensionLabel(art)?" · "+dimensionLabel(art):"")+'</p><h3><button data-edit="'+art.id+'">'+esc(art.title||"No title")+'</button></h3><div class="review-tags"><span class="quality-tag '+art.photoStatus+'">'+(art.images.length?photoLabels[art.photoStatus]:"Reference photo only")+'</span>'+detailIssues(art).map(issue=>'<span class="quality-tag detail-tag">'+issue.label+'</span>').join("")+'</div>'+(photoReviewNote(art)?'<p class="photo-recommendation">'+esc(photoReviewNote(art))+'</p>':'')+'<button class="visibility-toggle" role="switch" aria-checked="'+art.published+'" data-visibility="'+art.id+'" '+(!art.images.length||busy?"disabled":"")+'><span>'+ (art.published?"Included in draft":"Excluded from draft")+'</span><span class="toggle-track" aria-hidden="true"></span></button></article>').join("");
  query("#admin-empty").hidden=visible.length>0;
  selection();
}
async function persist(art,next){
  const result=await api("/api/admin/artworks/"+art.id,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({revision:art.revision,values:next})});
  artworks=result.artworks;
  query("#publication-status").textContent="Saved locally · prepare again to include these changes";
  return result.artwork;
}
const selectedThemes=()=>[...form.querySelectorAll('[name="themes"]:checked')].map(input=>input.value);
function themeChoices(selected){
  const themes=[...new Set([...artworks.flatMap(art=>art.themes),...selected])].sort();
  query("#theme-choices").innerHTML=themes.map(theme=>'<label class="check-field"><input type="checkbox" name="themes" value="'+esc(theme)+'" '+(selected.includes(theme)?'checked':'')+'>'+esc(theme)+'</label>').join('');
}
query("#add-theme").addEventListener("click",()=>{
  const input=query("#new-theme"),theme=input.value.trim();
  if(!theme)return;
  themeChoices([...new Set([...selectedThemes(),theme])]);input.value="";updateDetailReview();
  dirty=true;query("#save-message").textContent="Unsaved changes";
});
function updateDetailReview(){
  const details={...editing,themes:selectedThemes()};
  for(const field of ["medium","mediaCategory","surface","width","height","dimensionsConfirmed"]){
    const control=form.elements.namedItem(field);
    details[field]=control.type==="checkbox"?control.checked:["width","height"].includes(field)?(control.value===""?null:Number(control.value)):control.value;
  }
  const issues=detailIssues(details);
  query("#detail-notes").textContent=issues.length?issues.map(issue=>issue.label).join(" · "):"Dimensions, medium, surface and categories are recorded; measurements are confirmed.";
}
function openEditor(id){
  editing=artworks.find(art=>art.id===id);dirty=false;
  query("#editor-id").textContent=editing.id.toUpperCase();
  query("#editor-title").textContent=editing.title||"Artwork details";
  const members=artworks.filter(art=>art.seriesId&&art.seriesId===editing.seriesId);
  query("#series-info").hidden=!editing.seriesId;
  query("#series-info").textContent=editing.seriesTitle+" · "+members.length+" linked works. Changing display order moves the whole series.";
  query("#order-label").textContent=editing.seriesId?"Series display order":"Display order";
  query("#editor-preview").innerHTML=artworkPhoto(editing,2);
  query("#photo-notes").textContent=photoReviewNote(editing)||editing.qualityNotes||"No photo issues recorded.";
  query("#original-notes").textContent=editing.issues.join(" ");
  query("#original-notes-section").hidden=!editing.issues.length;
  query("#original-notes-section").open=false;
  for(const field of fields){
    if(field==="themes"){themeChoices(editing.themes);query("#new-theme").value="";continue;}
    const control=form.elements.namedItem(field);
    if(control.type==="checkbox") control.checked=editing[field];else control.value=editing[field]===null?"":editing[field];
  }
  updateDetailReview();
  form.elements.published.disabled=!editing.images.length;
  query("#save-message").textContent="";
  query("#save-message").classList.remove("error");
  query("#save-artwork").disabled=false;
  dialog.showModal();dialog.scrollTop=0;
}
function closeEditor(){
  if(busy) return;
  if(dirty&&!confirm("Discard unsaved changes to this artwork?")) return;
  dialog.close();editing=null;dirty=false;
}
query("#admin-grid").addEventListener("click",async event=>{
  if(busy)return;
  const edit=event.target.closest("[data-edit]");
  if(edit){openEditor(edit.dataset.edit);return;}
  const toggle=event.target.closest("[data-visibility]");
  if(!toggle||busy) return;
  const art=artworks.find(item=>item.id===toggle.dataset.visibility);
  busy=true;toggle.disabled=true;selection();message("");
  try{await persist(art,{...values(art),published:!art.published});message("Visibility saved locally.");}
  catch(error){message(error.message,true);}
  finally{busy=false;render();}
});
query("#admin-grid").addEventListener("change",event=>{
  const id=event.target.dataset.select;if(!id)return;
  if(event.target.checked)selected.add(id);else selected.delete(id);
  selection();
});
for(const selector of ["#visibility-filter","#review-filter","#sale-filter"])query(selector).addEventListener("change",render);
query("#admin-search").addEventListener("input",render);
query("#select-visible").addEventListener("change",event=>{for(const art of visible)if(event.target.checked)selected.add(art.id);else selected.delete(art.id);render();});
async function bulk(published){
  if(busy)return;
  const items=artworks.filter(art=>selected.has(art.id));
  if(published&&items.some(art=>!art.images.length)){message("Deselect artworks without a finished photo before showing this selection.",true);return;}
  busy=true;render();let saved=0;
  try{
    for(const {id} of items){
      // A preceding series member can update this artwork’s revision.
      const art=artworks.find(art=>art.id===id);
      await persist(art,{...values(art),published});selected.delete(id);saved++;message("Saved "+saved+" of "+items.length+" artworks.");}
    message(saved+" artworks "+(published?"included in":"excluded from")+" the local draft.");
  }catch(error){message(saved+" saved. "+error.message+" Remaining artworks are still selected.",true);}
  finally{busy=false;render();}
}
query("#bulk-show").addEventListener("click",()=>bulk(true));
query("#bulk-hide").addEventListener("click",()=>bulk(false));
query("#close-editor").addEventListener("click",closeEditor);
query("#cancel-editor").addEventListener("click",closeEditor);
dialog.addEventListener("cancel",event=>{event.preventDefault();closeEditor();});
// Follow the filtered grid; arrow keys inside controls retain their normal behavior.
dialog.addEventListener("keydown",event=>{
  if(!dialog.open||event.defaultPrevented||event.isComposing||event.altKey||event.ctrlKey||event.metaKey||event.shiftKey)return;
  if(!["ArrowLeft","ArrowRight"].includes(event.key)||event.target.closest("input,textarea,select")||event.target.isContentEditable)return;
  event.preventDefault();
  if(busy||event.repeat)return;
  const index=visible.findIndex(art=>art.id===editing.id)+(event.key==="ArrowRight"?1:-1);
  if(index<0||index>=visible.length)return;
  if(dirty){query("#save-message").textContent="Save or cancel your changes before switching paintings.";return;}
  openEditor(visible[index].id);
});
form.addEventListener("input",()=>{updateDetailReview();dirty=true;query("#save-message").textContent="Unsaved changes";});
form.addEventListener("submit",async event=>{
  event.preventDefault();if(busy)return;
  const next={};
  for(const field of fields){
    if(field==="themes"){next.themes=selectedThemes();continue;}
    const control=form.elements.namedItem(field);
    next[field]=control.type==="checkbox"?control.checked:["width","height","price","order"].includes(field)?(control.value===""?null:Number(control.value)):control.value.trim();
  }
  next.currency=next.currency.toUpperCase();
  busy=true;query("#save-artwork").disabled=true;query("#save-message").textContent="Saving…";
  try{
    const saved=await persist(editing,next);dirty=false;editing=saved;
    dialog.close();message("Saved "+(saved.title||saved.id)+" locally.");
  }catch(error){query("#save-message").textContent=error.message;query("#save-message").classList.add("error");}
  finally{busy=false;query("#save-artwork").disabled=false;render();}
});
addEventListener("beforeunload",event=>{if(dirty){event.preventDefault();event.returnValue="";}});
try{
  const data=await api("/api/admin/catalog");artworks=sortArtworks(data.artworks);
  // Review links open the same editable collection with ordinary filters already selected.
  const params=new URLSearchParams(location.search);
  if(params.has("search"))query("#admin-search").value=params.get("search");
  for(const filter of ["visibility","review","sale"]){
    if(!params.has(filter))continue;
    const select=query("#"+filter+"-filter"),value=params.get(filter);
    if(![...select.options].some(option=>option.value===value))throw new Error("Unknown "+filter+" filter: "+value);
    select.value=value;
  }
  render();
}catch(error){message(error.message,true);query("#admin-count").textContent="Collection unavailable";}

query("#prepare-publication").addEventListener("click",async()=>{
  if(busy)return;
  busy=true;selection();const status=query("#publication-status");status.textContent="Preparing local publication…";status.classList.remove("error");
  try{const result=await api("/api/publication/prepare",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});status.textContent="Prepared "+result.artworks+" artworks locally · nothing uploaded or published";}
  catch(error){status.textContent=error.message;status.classList.add("error");}
  finally{busy=false;render();}
});
try{query("#publication-status").textContent=(await api("/api/publication/status")).message;}
catch(error){query("#publication-status").textContent=error.message;query("#publication-status").classList.add("error");}
