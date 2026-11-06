from pathlib import Path
import uuid
import pytest
from scenetrace.store import Store
from scenetrace.library import MediaLibrary,episode_metadata,destination_folder
from scenetrace.downloads import DownloadManager

@pytest.mark.parametrize('name,season,episode', [('Example Anime Ep 5.mp4',None,5),('Example Anime Episode 005.mkv',None,5),('Example Anime S1E05.mp4',1,5),('[Group] Example Anime - 05 [1080p].mkv',None,5)])
def test_episode_recognition(name,season,episode):
    r=episode_metadata(name)
    assert r['series']=='Example Anime' and r['episode']==episode and r['season']==season

def test_library_import_edit_merge_split_move_collision_restart(tmp_path):
    store=Store(tmp_path/'state');library=MediaLibrary(store)
    files=tmp_path/'files';files.mkdir()
    for name in ('Example Anime Ep 5.mp4','Example Anime Episode 006.mkv','Unrelated.mp4'):
        (files/name).write_bytes(name.encode())
    assert library.import_folder(files)['indexed']==3
    items=library.listing()['items'];first=next(x for x in items if x['episode']==5);second=next(x for x in items if x['episode']==6)
    assert first['collection']==second['collection']=='Example Anime'
    library.edit([first['id'],second['id']],{'category':'Anime','collection':'My collection'})
    library.edit([second['id']],{'collection':'Separated'})
    destination=tmp_path/'organized';destination.mkdir();(destination/'Example Anime Ep 5.mp4').write_bytes(b'KEEP')
    moved=library.move([first['id']],str(destination))['items'][0]
    assert Path(moved['path']).name=='Example Anime Ep 5 (1).mp4'
    assert Path(moved['path']).read_bytes()==b'Example Anime Ep 5.mp4'
    assert (destination/'Example Anime Ep 5.mp4').read_bytes()==b'KEEP'
    restarted=MediaLibrary(Store(tmp_path/'state'))
    assert restarted.get(first['id'])['category']=='Anime'
    assert restarted.get(second['id'])['collection']=='Separated'
    assert restarted.import_folder(destination)['indexed']==2
    assert len(restarted.listing()['items'])==4

def test_source_folders_and_conservative_aliases(tmp_path):
    store=Store(tmp_path/'state');lib=MediaLibrary(store)
    store.put_records([{'id':'anilist:1','source_id':'anilist','title':'Example Anime','alternatives':['Nihongo Title'], 'description':'','category':'anime'}])
    path=tmp_path/'Nihongo Title E05.mp4';path.write_bytes(b'video')
    item=lib.add(path,'https://www.example.org/watch')
    assert item['series']=='Example Anime' and item['category']=='Anime'
    folder=destination_folder(store,tmp_path,'https://www.example.org/video')
    assert folder==tmp_path/'example.org'
    store.set_setting('organize_by_source',False)
    assert destination_folder(store,tmp_path,'https://www.example.org/video')==tmp_path
    unrelated=tmp_path/'Example Anime Movie.mp4';unrelated.write_bytes(b'video')
    assert lib.add(unrelated)['collection']==''

def test_native_completed_transfer_migrates_without_moving_files(tmp_path):
    store=Store(tmp_path/'state');library=MediaLibrary(store)
    path=tmp_path/'Episode 1.mp4';path.write_bytes(b'video')
    key=uuid.uuid4().hex
    manager=DownloadManager(store,'proxy',workers=0,completed=library.completed)
    data=dict(id=key,title=path.name,path=str(path),source='https://example.org',status='downloading',bytes=2,total=5,can_resume=True)
    manager.browser_sync([data]);manager.control(key,'pause')
    assert manager.browser_sync([])['commands']==[{'id':key,'action':'pause'}]
    manager.browser_sync([dict(data,status='completed',bytes=5)])
    assert library.listing()['items'][0]['path']==str(path)
    manager.control(key,'remove')
    assert path.read_bytes()==b'video' and len(library.listing()['items'])==1
    manager.close()

def test_native_restart_never_claims_it_can_resume_a_lost_operation(tmp_path):
    store=Store(tmp_path/'state')
    store.job(dict(id=uuid.uuid4().hex,engine='browser',title='x',path=str(tmp_path/'file.zip'),status='downloading',created=1,can_resume=True))
    manager=DownloadManager(store,'proxy',workers=0)
    job=manager.all()[0]
    assert job['status']=='failed' and not job['can_resume']
    with pytest.raises(ValueError,match='cannot resume'):manager.control(job['id'],'resume')
    manager.close()


def test_bulk_edit_validates_every_item_before_changing_catalog(tmp_path):
    library=MediaLibrary(Store(tmp_path/'state'))
    path=tmp_path/'Series E01.mp4';path.write_bytes(b'video')
    item=library.add(path)
    with pytest.raises(ValueError):
        library.edit([item['id'],'missing'],{'category':'Anime'})
    assert library.get(item['id'])['category']=='Unsorted'
    with pytest.raises(ValueError):
        library.edit([item['id']],{'category':'Anime','episode':'not a number'})
    assert library.get(item['id'])['category']=='Unsorted'
