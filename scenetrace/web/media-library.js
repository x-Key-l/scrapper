'use strict';
const mediaLibraryState={items:[],selected:new Set(),query:'',offset:0,more:false,categories:[],loaded:false};
async function loadMediaLibrary(more=false){
    const result=await api('library/list',{query:mediaLibraryState.query,offset:more?mediaLibraryState.offset+100:0});
    mediaLibraryState.offset=more?mediaLibraryState.offset+100:0;
    mediaLibraryState.items=more?[...mediaLibraryState.items,...result.items]:result.items;
    mediaLibraryState.categories=result.categories;mediaLibraryState.more=result.has_more;mediaLibraryState.loaded=true;
    if(state.view==='media')renderPage();
}
function mediaLibraryPage(){
    const m=mediaLibraryState;
    return title('ON THIS PC','Media Library','Your downloaded videos, organized independently of the download queue.')+
        '<form data-media-form="search" class="searchbar"><input name="query" aria-label="Search media library" placeholder="Find a series, category, website or filename" value="'+esc(m.query)+'"><button>Search</button></form>'+
        '<div class="toolbar"><button class="primary" data-media="import">Import a video folder</button><button data-media="edit">Organize selected</button><button data-media="move">Move selected files</button><button data-media="refresh">Refresh</button></div>'+
        '<details class="panel"><summary>Automatic organization</summary><form data-media-form="preferences"><label class="check"><input type="checkbox" name="organize_by_source"'+(state.data.settings.organize_by_source?' checked':'')+'> Put new downloads in website folders</label><label class="check"><input type="checkbox" name="organize_by_series"'+(state.data.settings.organize_by_series?' checked':'')+'> Add category and recognized series folders for analyzer downloads</label><p class="meta">Existing files stay in place. Unknown categories remain Unsorted; edit them below. Browser Save As can override the suggested folder.</p><button>Save organization preferences</button></form></details>'+tasksMarkup()+
        (m.items.length?'<div class="media-list">'+m.items.map(item=>'<article class="media-row"><label class="media-select"><input type="checkbox" data-media-select="'+esc(item.id)+'"'+(m.selected.has(item.id)?' checked':'')+' aria-label="Select '+esc(item.title)+'"></label><div><h3>'+esc(item.title)+'</h3><p class="meta">'+esc([item.collection||'No collection',item.season!=null?'Season '+item.season:'',item.episode!=null?'Episode '+item.episode:'',item.category,item.website].filter(Boolean).join(' · '))+'</p><p class="media-path">'+esc(item.path)+'</p>'+(item.suggestions?.length?'<p class="meta">Possible match: '+esc(item.suggestions.map(s=>s.title).join(', '))+'. Review with Edit.</p>':'')+(!item.available?'<p class="inline-error">File missing. Reconnect its drive or import its new folder.</p>':'')+'</div><div class="actions"><button data-media="open" data-id="'+esc(item.id)+'"'+(!item.available?' disabled':'')+'>Play</button><button data-media="folder" data-id="'+esc(item.id)+'">Folder</button><button data-media="edit" data-id="'+esc(item.id)+'">Edit</button><button data-media="rename" data-id="'+esc(item.id)+'">Rename file</button></div></article>').join('')+'</div>':empty(m.loaded?'No videos in this view':'Loading media library…','Completed video downloads appear here automatically. You can also import an existing folder.'))+
        (m.more?'<button data-media="more">More videos</button>':'');
}
function editMedia(ids){
    if(!ids.length)return toast('Select one or more videos.');
    const single=ids.length===1;const item=single?mediaLibraryState.items.find(x=>x.id===ids[0]):{};
    const fields=[['title','Video title'],['series','Series'],['collection','Collection'],['category','Category'],['season','Season'],['episode','Episode'],['source','Source webpage']];
    dialog(single?'Edit video':'Organize '+ids.length+' videos','<form data-media-form="edit" data-ids="'+esc(JSON.stringify(ids))+'"><p class="meta">'+(single?'Edit the catalog information; the file name stays unchanged.':'Filled fields apply to all selected videos. Use a shared collection to merge groups, or a new collection to split a group.')+'</p><div class="form-grid">'+fields.map(([key,label])=>'<div><label for="media-'+key+'">'+label+'</label><input id="media-'+key+'" name="'+key+'" value="'+esc(single?item[key]??'':'')+'"'+(['season','episode'].includes(key)?' type="number" min="0"':'')+(key==='category'?' list="media-categories"':'')+' placeholder="'+(single?'': 'Leave unchanged')+'"></div>').join('')+'</div><datalist id="media-categories">'+mediaLibraryState.categories.map(c=>'<option>'+esc(c)+'</option>').join('')+'</datalist><button class="primary">Save details</button></form>');
}
document.addEventListener('change',event=>{const key=event.target.dataset.mediaSelect;if(key){if(event.target.checked)mediaLibraryState.selected.add(key);else mediaLibraryState.selected.delete(key);}});
document.addEventListener('click',async event=>{
    const b=event.target.closest('[data-media]');if(!b)return;
    const action=b.dataset.media;const ids=b.dataset.id?[b.dataset.id]:[...mediaLibraryState.selected];
    try{
        if(action==='edit')return editMedia(ids);
        if(action==='open'||action==='folder')return await api('library/open',{id:b.dataset.id,folder:action==='folder'});
        if(action==='refresh'||action==='more')return await loadMediaLibrary(action==='more');
        if(action==='import'){
            const result=await api('native/pick',{kind:'folder'});if(result.cancelled)return;
            await api('library/import',{folder:result.path});await reload(true);toast('Indexing folder. Files remain in their current locations.');return;
        }
        if(action==='move'||action==='rename'){
            if(!ids.length)return toast('Select videos to move.');
            const item=mediaLibraryState.items.find(x=>x.id===ids[0]);
            dialog(action==='rename'?'Rename file':'Move '+ids.length+' files','<form data-media-form="move" data-ids="'+esc(JSON.stringify(ids))+'"><label for="media-destination">Destination folder</label><input id="media-destination" name="destination" required value="'+esc(item.path.replace(/[\\/][^\\/]+$/,''))+'"><button type="button" data-action="pick-folder" data-target="media-destination">Browse</button>'+(action==='rename'?'<label for="media-rename">New filename</label><input id="media-rename" name="rename" required value="'+esc(item.filename)+'">':'')+'<p class="meta">Existing files are never overwritten. A numbered filename is used for collisions. Catalog information is preserved.</p><button class="primary">'+(action==='rename'?'Rename file':'Move files')+'</button></form>');
        }
    }catch(error){toast(error.message,true);}
});
document.addEventListener('submit',async event=>{
    const form=event.target;if(!form.dataset.mediaForm)return;event.preventDefault();
    const values=Object.fromEntries(new FormData(form));
    try{
        if(form.dataset.mediaForm==='search'){mediaLibraryState.query=values.query;return await loadMediaLibrary();}
        if(form.dataset.mediaForm==='preferences'){
            await api('settings',{organize_by_source:values.organize_by_source==='on',organize_by_series:values.organize_by_series==='on'});await reload(true);return toast('Organization preferences saved.');
        }
        const ids=JSON.parse(form.dataset.ids);
        if(form.dataset.mediaForm==='edit')await api('library/edit',{ids,values:ids.length>1?Object.fromEntries(Object.entries(values).filter(([,v])=>v!=='')):values});
        if(form.dataset.mediaForm==='move'){
            if(!confirm('Move '+ids.length+' file(s) to '+values.destination+'?'))return;
            await api('library/move',{ids,...values});await reload();
        }
        $('dialog').close();await loadMediaLibrary();toast('Media library updated.');
    }catch(error){toast(error.message,true);}
});
