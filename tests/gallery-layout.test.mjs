import assert from 'node:assert/strict';
import test from 'node:test';
import {artworkSpan,masonryPositions,sortArtworks} from '../site/art/gallery.mjs';
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

test('later works cannot jump ahead by filling holes beside an earlier full-width painting',()=>{
  const items=[{id:'first',columns:1,rows:30},{id:'wide',columns:4,rows:10},{id:'last',columns:1,rows:5}];
  assert.deepEqual(masonryPositions(items,4).map(({id,row,column})=>({id,row,column})),[
    {id:'first',row:0,column:0},{id:'wide',row:30,column:0},{id:'last',row:40,column:0}
  ]);
  const varied=Array.from({length:30},(_,index)=>({id:String(index),columns:[1,2,4][index%3],rows:[40,10,25,60][index%4]}));
  for(const columns of [4,2,1])for(const uniform of [false,true]){
    const placed=masonryPositions(varied.map(item=>({...item,columns:uniform?1:item.columns})),columns);
    for(let index=1;index<placed.length;index++){
      const previous=placed[index-1],current=placed[index];
      assert(current.row>previous.row || current.row===previous.row && current.column>previous.column);
    }
  }
});

test('tied priorities stay deterministic and series members remain together',()=>{
  const works=[
    {id:'art-003',order:10,seriesId:'',seriesPosition:0},
    {id:'art-002',order:10,seriesId:'',seriesPosition:0},
    {id:'art-005',order:5,seriesId:'pair',seriesPosition:2},
    {id:'art-004',order:5,seriesId:'pair',seriesPosition:1}
  ];
  assert.deepEqual(sortArtworks(works).map(art=>art.id),['art-004','art-005','art-002','art-003']);
  assert.deepEqual(sortArtworks([...works].reverse()),sortArtworks(works));
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
