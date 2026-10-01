/** Photo judgments are manual; missing artwork details are calculated from saved fields. */
export const photoLabels={ready:"Photo ready",review:"Photo needs review",needs_photo:"Needs a new photo"};
// Dated recommendations stay in private, editable notes; visibility remains the owner's choice.
export const photoReviewNote=art=>art.notes.split("\n").findLast(line=>line.startsWith("Photo review ("))||"";
// Older catalog entries keep the surface in the medium (e.g. "Oil on canvas").
const hasSurface=art=>Boolean(art.surface.trim())||/\b(canvas|panels?|plywood|wood|boards?|paper|linen|cardboard|masonite|hardboard)\b/i.test(art.medium);
export const detailChecks=[
  {id:"dimensions",label:"Missing dimensions",missing:art=>art.width===null||art.height===null},
  {id:"measurements",label:"Measurements unconfirmed",missing:art=>art.width!==null&&art.height!==null&&!art.dimensionsConfirmed},
  {id:"medium",label:"Missing medium",missing:art=>!art.medium.trim()},
  {id:"surface",label:"Missing surface",missing:art=>!hasSurface(art)},
  {id:"categories",label:"Missing categories",missing:art=>!art.themes.length}
];
export const detailIssues=art=>detailChecks.filter(check=>check.missing(art));
export const photoNeedsAttention=art=>!art.images.length||art.photoStatus!=="ready";
export function matchesReview(art,filter){
  if(filter==="all")return true;
  if(filter==="curated")return Boolean(photoReviewNote(art));
  if(filter==="attention")return photoNeedsAttention(art)||detailIssues(art).length>0;
  if(filter==="clear")return !photoNeedsAttention(art)&&!detailIssues(art).length;
  if(filter==="photo")return photoNeedsAttention(art);
  if(filter==="unfinished")return !art.images.length;
  if(Object.hasOwn(photoLabels,filter))return art.photoStatus===filter&&(filter!=="ready"||art.images.length>0);
  if(filter==="details")return detailIssues(art).length>0;
  return detailChecks.find(check=>check.id===filter).missing(art);
}
