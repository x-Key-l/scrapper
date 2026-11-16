"""Integration contracts for PR #4 persistence and PR #5 media metadata."""
import json
import time
from pathlib import Path
import pytest
from scenetrace.store import Store
from scenetrace.app import App
from scenetrace.library import MediaLibrary
from scenetrace.downloads import DownloadManager
from scenetrace import websites, media
from bs4 import BeautifulSoup


def test_existing_database_migrates_without_moving_media(tmp_path):
    root=tmp_path/'state';store=Store(root)
    store.set_setting('destination',str(tmp_path))
    store.set_setting('organize_by_source',False)
    store.set_setting('filename_template','%(title)s.%(ext)s')
    store.save({'id':'old','title':'Saved title'})
    store.history('Remember me')
    store.bookmarks('https://example.org/title','Bookmark')
    file=tmp_path/'Existing.mp4';file.write_bytes(b'existing user file')
    store.job(dict(id='legacy',title='Existing',source='https://example.org/watch',path=str(file),status='completed',bytes=file.stat().st_size,created=1))
    # v4.0 has no media_library table; initialize v5 over the pre-existing store.
    lib=MediaLibrary(Store(root));manager=DownloadManager(Store(root),'proxy',workers=0,completed=lib.completed)
    try:
        assert store.setting('destination')==str(tmp_path)
        assert store.setting('organize_by_source') is False
        assert lib.listing()['items'][0]['path']==str(file)
        assert file.read_bytes()==b'existing user file'
        assert store.saved()[0]['id']=='old'
        assert store.history()[0]['query']=='Remember me'
        assert store.bookmarks()[0]['title']=='Bookmark'
        assert manager.all()[0]['status']=='completed'
    finally: manager.close()
    again=MediaLibrary(Store(root))
    assert len(again.listing()['items'])==1


def test_template_subtitle_sidecars_do_not_overwrite(tmp_path):
    store=Store(tmp_path/'state');store.set_setting('organize_by_source',False)
    store.set_setting('filename_template','%(title)s - %(height)sp.%(ext)s')
    manager=DownloadManager(store,'proxy',workers=0)
    try:
        fmt=dict(id='1',extractor_id='audio+video',extractor_url='https://example.org/manifest.mpd',ext='mkv',height=720,method='extractor')
        info=dict(title='Episode',url='https://example.org/page',selected_subtitles=['en'],subtitles=[{'language':'en'}])
        result=manager.add(info,fmt,str(tmp_path))
        job=manager.items[result['id']]
        assert Path(job['path']).name=='Episode - 720p.mkv'
        assert job['extractor_url']==fmt['extractor_url']
        Path(job['part']).with_suffix('.en.vtt').write_text('WEBVTT\n\n')
        Path(job['path']).with_suffix('.nfo').write_text('KEEP')
        manager._sidecars(job)
        assert Path(job['path']+'.en.vtt').read_text()=='WEBVTT\n\n'
        assert Path(job['path']).with_suffix('.nfo').read_text()=='KEEP'
        assert '<title>Episode</title>' in Path(job['path']+'.nfo').read_text()
    finally: manager.close()


def test_subtitles_reject_path_injection(tmp_path):
    app=App(tmp_path/'state','proxy')
    try:
        analysis=app.register_analysis(dict(title='Test',url='https://example.org',analyzed=time.time(),formats=[dict(id='a',ext='mp4')],subtitles=[{'language':'../outside'}]))
        with pytest.raises(ValueError,match='subtitles'):
            app.download(dict(analysis_id=analysis['analysis_id'],format_id='a',subtitles=['../outside'],destination=str(tmp_path)))
    finally: app.close()


def test_website_manifest_uses_its_own_extractor_url(monkeypatch):
    source={'endpoint':'https://example.org','web_config':{'render_browser':False,'playback_selector':''}}
    page=BeautifulSoup('<title>Episode</title><video src="/stream.m3u8"></video><script>var segment="https://example.org/chunk.m4s";</script>','html.parser')
    monkeypatch.setattr(websites,'fetch_page',lambda *a:(page,'https://example.org/watch'))
    monkeypatch.setattr(media,'analyze',lambda value,proxy:{'formats':[dict(id='a',ext='mp4',method='extractor',video=True,audio=True)]})
    result=websites.resolve(source,'https://example.org/watch','proxy')
    assert len(result['formats'])==1
    fmt=result['formats'][0]
    assert fmt['extractor_url']=='https://example.org/stream.m3u8' and fmt['extractor_id']=='a'
