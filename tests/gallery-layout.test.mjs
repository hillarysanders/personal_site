import assert from 'node:assert/strict';
import test from 'node:test';
import {artworkSpan,masonryPositions} from '../site/art/gallery.mjs';
import {gallerySizes} from '../site/art/images.mjs';

test('36-inch width takes precedence over area without treating tall works as wide',()=>{
  const art={width:35.9,height:12,sizeCategory:'Large'};
  assert.equal(artworkSpan(art),2);
  assert.equal(artworkSpan({...art,width:36}),4);
  assert.equal(artworkSpan({...art,width:48,height:2}),4);
  assert.equal(artworkSpan({...art,width:12,height:48}),2);
  assert.equal(artworkSpan({...art,width:6,height:6}),1);
  assert.equal(artworkSpan({...art,width:null,height:null}),2);
  assert.equal(artworkSpan({...art,width:36,height:null}),4);
});

test('full-width artwork fits desktop and narrow grids without overlapping adjacent works',()=>{
  const items=[{id:'small',columns:1,rows:20},{id:'wide',columns:4,rows:40},{id:'medium',columns:2,rows:30}];
  for(const columns of [4,2,1]){
    const placed=masonryPositions(items,columns);
    assert.equal(placed[1].columns,columns);
    assert.equal(placed[1].column,0);
    for(const [index,card] of placed.entries())for(const other of placed.slice(index+1)){
      assert(card.column+card.columns<=other.column || other.column+other.columns<=card.column || card.row+card.rows<=other.row || other.row+other.rows<=card.row);
    }
  }
  assert.equal(gallerySizes('uniform',4),gallerySizes('uniform',1));
  assert.notEqual(gallerySizes('size',4),gallerySizes('size',2));
});
