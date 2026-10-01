/** Broad browsing categories are separate from the artwork's detailed medium. */
export const mediaCategories=["Acrylic paintings","Oil paintings","Graphite","Mixed media","Pen and ink"];
const rules=[
  [/\bmixed media\b|\bcut wood\b|(?=.*\bacrylic\b)(?=.*\boil\b)/i,"Mixed media"],
  [/\bacrylic\b/i,"Acrylic paintings"],
  [/\boil\b/i,"Oil paintings"],
  [/\bgraphite\b/i,"Graphite"],
  [/\bpen\b|\bink\b/i,"Pen and ink"]
];
// Unspecified "Painting" records stay unassigned; photographs cannot identify the binder.
export const categoryForMedium=medium=>rules.find(([pattern])=>pattern.test(medium))?.[1]||"";
