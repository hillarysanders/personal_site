import assert from 'node:assert/strict';
import test from 'node:test';
import {emptyFilters,matches} from '../site/art/gallery.mjs';

test('media filtering combines with subject and search, and resets to all works',()=>{
  const drawing={title:'Nautilus',description:'',themes:['Wildlife'],medium:'Pen and ink',year:'',sizeCategory:'Unclassified',width:null,height:null,availability:'',period:''};
  assert.equal(matches(drawing,emptyFilters()),true);
  assert.equal(matches(drawing,{...emptyFilters(),medium:'Pen and ink',theme:'Wildlife',search:'nautilus'}),true);
  assert.equal(matches(drawing,{...emptyFilters(),medium:'Graphite'}),false);
  assert.equal(matches(drawing,{...emptyFilters(),medium:'Pen and ink',theme:'Figures'}),false);
});
