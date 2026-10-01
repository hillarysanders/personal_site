/** Retry failed gallery requests twice, then leave an explicit manual retry. */
export function watchPhotos(grid) {
  const attempts=new WeakMap(),delays=[500,1500];
  function status(image,state,text) {
    const button=image.closest('.image-surface');
    if(!button.dataset.photoState)button.dataset.photoLabel=button.getAttribute('aria-label');
    button.dataset.photoState=state;
    button.setAttribute('aria-label',text+' '+button.dataset.photoLabel);
    let label=button.querySelector('.photo-status');
    if(!label){label=document.createElement('span');label.className='photo-status';label.setAttribute('role','status');button.append(label);}
    label.textContent=text;
  }
  function retry(image) {
    if(!image.isConnected)return;
    const url=new URL(image.currentSrc||image.src,location.href);
    url.searchParams.set('photo-retry',Date.now());
    // Retry the selected resolution without letting srcset retain its failed request.
    image.closest("picture").querySelector("source")?.remove();
    image.removeAttribute('srcset');
    image.src=url.href;
  }
  grid.addEventListener('error',event=>{
    const image=event.target;
    if(!image.matches('.image-surface img'))return;
    const attempt=attempts.get(image)||0;
    if(attempt<delays.length){
      attempts.set(image,attempt+1);
      status(image,'loading','Retrying photo…');
      setTimeout(()=>retry(image),delays[attempt]);
    }else status(image,'failed','Photo couldn’t load. Click to retry.');
  },true);
  grid.addEventListener('load',event=>{
    const image=event.target;
    if(!image.matches('.image-surface img'))return;
    const button=image.closest('.image-surface');
    if(button.dataset.photoState)button.setAttribute('aria-label',button.dataset.photoLabel);
    delete button.dataset.photoLabel;
    delete button.dataset.photoState;
    button.querySelector('.photo-status')?.remove();
    attempts.delete(image);
  },true);
  grid.addEventListener('click',event=>{
    const button=event.target.closest('.image-surface[data-photo-state]');
    if(!button)return;
    event.stopPropagation();
    if(button.dataset.photoState!=='failed')return;
    const image=button.querySelector('img');
    attempts.delete(image);
    status(image,'loading','Retrying photo…');
    retry(image);
  });
}
