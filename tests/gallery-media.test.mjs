import assert from 'node:assert/strict';
import test from 'node:test';
import {emptyFilters,matches} from '../site/art/gallery.mjs';
import {categoryForMedium} from '../site/art/media.mjs';

test('media filtering combines with subject and search, and resets to all works',()=>{
  const drawing={title:'Nautilus',description:'',themes:['Wildlife'],medium:'Pen and ink on paper',mediaCategory:'Pen and ink',year:'',sizeCategory:'Unclassified',width:null,height:null,availability:'',period:''};
  assert.equal(matches(drawing,emptyFilters()),true);
  assert.equal(matches(drawing,{...emptyFilters(),medium:'Pen and ink',theme:'Wildlife',search:'nautilus'}),true);
  assert.equal(matches(drawing,{...emptyFilters(),medium:'Graphite'}),false);
  assert.equal(matches(drawing,{...emptyFilters(),medium:'Pen and ink',theme:'Figures'}),false);
});

test('broad media groups ignore surfaces and do not guess unspecified paintings',()=>{
  for(const medium of ['Oil on canvas','Oil on wood','Oil on plywood','Oil on wood panel'])assert.equal(categoryForMedium(medium),'Oil paintings');
  assert.equal(categoryForMedium('Acrylic on panel'),'Acrylic paintings');
  for(const medium of ['Acrylic and oil on canvas','Mixed media and oil','Cut wood blocks and oil paint'])assert.equal(categoryForMedium(medium),'Mixed media');
  for(const medium of ['','Painting','Watercolor'])assert.equal(categoryForMedium(medium),'');
  const art={title:'Pear',description:'',themes:['Still Life'],medium:'Oil on plywood',mediaCategory:'Oil paintings',year:'',sizeCategory:'Small',width:6,height:6,availability:'',period:''};
  assert(matches(art,{...emptyFilters(),medium:'Oil paintings',search:'plywood'}));
  assert(!matches(art,{...emptyFilters(),medium:'Acrylic paintings'}));
});
