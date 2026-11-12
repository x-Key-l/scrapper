"""Media branch contracts; provider fixtures are not live-service verification."""
import ast
import inspect
import time
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from scenetrace import media, websites, viewing
from scenetrace.app import App
from scenetrace.store import Store
from scenetrace.downloads import DownloadManager


@pytest.mark.parametrize('protocol', ['m3u8_native', 'http_dash_segments', 'dash', 'rtmp', 'https'])
def test_protocols_and_drm_are_enumerated(protocol):
    class Extractor:
        def __init__(self, options):
            assert options['allow_unplayable_formats']
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, *args, **kwargs):
            return {'title': 'Fixture', 'age_limit': 18, 'formats': [
                {'url': 'https://example.com/video', 'format_id': 'main', 'ext': 'mp4',
                 'protocol': protocol, 'has_drm': True, 'vcodec': 'h264', 'acodec': 'aac'}]}
    with patch('yt_dlp.YoutubeDL', Extractor):
        result = media.worker({'url': 'https://example.com', 'proxy': ''})
    assert result['restricted']
    assert len(result['formats']) == 1
    assert result['formats'][0]['permitted'] is True
    assert result['formats'][0]['label'].endswith(' · DRM')


def test_no_format_loop_filters_on_protocol():
    tree = ast.parse(inspect.getsource(media.worker))
    loops = [node for node in ast.walk(tree) if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == 'x']
    assert loops
    for loop in loops:
        for conditional in (node for node in ast.walk(loop) if isinstance(node, ast.If)):
            if any(isinstance(node, ast.Continue) for node in ast.walk(conditional)):
                assert 'protocol' not in ast.unparse(conditional.test)


def test_official_handoff_reaches_media_analysis():
    service = viewing.Viewing(SimpleNamespace())
    episode = {'kind':'official', 'url':'https://example.com/episode', 'title':'Episode', 'source':'Example'}
    with patch.object(service, 'play_media', return_value={'formats':['found']}) as resolve:
        assert service.play(service.ticket('episode', episode))['formats'] == ['found']
        resolve.assert_called_once()


@pytest.mark.parametrize('path', ['/shorts/', '/embed/', '/live/', '/v/'])
def test_youtube_variants(path):
    assert viewing.youtube_id('http://m.youtube.com'+path+'HtVdAasjOgU') == 'HtVdAasjOgU'


def test_site_detection_without_license_and_script_manifest(monkeypatch):
    source = {'endpoint':'https://example.com', 'web_config':{'render_browser':False}}
    doc = websites.parse_page('<video src="https://media.example.com/video.mp4"></video><script>var v="https:\\/\\/media.example.com/live.m3u8";</script>')
    monkeypatch.setattr(websites, 'fetch_page', lambda *args:(doc, 'https://watch.example.com/player'))
    monkeypatch.setattr(media, 'analyze', lambda *args:{'formats':[{'id':'hls', 'ext':'mp4','url':'https://media.example.com/live.m3u8','method':'extractor'}]})
    result = websites.resolve(source, 'https://watch.example.com/player', 'proxy')
    assert len(result['formats']) == 2
    assert all(f['permitted'] for f in result['formats'])
    assert result['download_allowed']


def test_format_sort_never_preselects_drm():
    app = App.__new__(App)
    app.analyses = {}
    result = app.register_analysis({'analyzed':time.time(), 'formats':[
        {'id':'protected','drm':True,'video':True,'audio':True,'height':2160},
        {'id':'video','video':True,'audio':False,'height':1080},
        {'id':'muxed','video':True,'audio':True,'height':720}]})
    assert [f['id'] for f in result['formats']] == ['muxed', 'video', 'protected']


def test_template_and_unsafe_extension_stay_in_destination(tmp_path):
    store = Store(tmp_path/'state')
    store.set_setting('filename_template', '%(title)s E01.%(ext)s')
    manager = DownloadManager(store, '', workers=0)
    try:
        job = manager.add({'title':'../Example','url':'https://example.com/v'}, {'ext':'../../evil','method':'direct'}, str(tmp_path))
        from pathlib import Path
        assert Path(job['path']).parent == tmp_path
        assert Path(job['path']).name.endswith(' E01.bin')
    finally:
        manager.close()


@pytest.mark.parametrize('drm,expected', [(True, 'Protected stream. yt-dlp could not decrypt it.'), (False, 'fixture diagnostic')])
def test_real_worker_stderr_and_drm_error(tmp_path, monkeypatch, drm, expected):
    import sys
    monkeypatch.setattr(media, 'worker_args', lambda:[sys.executable, '-c', 'import sys; sys.stdin.read(); print("fixture diagnostic", file=sys.stderr); sys.exit(1)'])
    manager = DownloadManager(Store(tmp_path/'state'), '', workers=1)
    try:
        job = manager.add({'title':'Failure','url':'https://example.com'}, {'ext':'mp4','id':'main','method':'extractor','drm':drm}, str(tmp_path))
        deadline = time.monotonic()+5
        while time.monotonic()<deadline:
            actual = manager.items[job['id']]
            if actual['status']=='failed' and not actual.get('_running'):
                break
            time.sleep(.02)
        assert actual['status']=='failed'
        if drm: assert actual['error']==expected
        else: assert expected in actual['error']
    finally: manager.close()


def test_combined_format_keeps_audio_drm_label():
    class Extractor:
        def __init__(self, options): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, *args, **kwargs):
            return {'title':'Fixture', 'formats':[
                {'format_id':'video','ext':'mp4','url':'https://example.com/v','vcodec':'h264','acodec':'none'},
                {'format_id':'audio','ext':'m4a','url':'https://example.com/a','vcodec':'none','acodec':'aac','has_drm':True}]}
    with patch('yt_dlp.YoutubeDL', Extractor), patch.object(media, 'ffmpeg_path', return_value='ffmpeg'):
        combined = media.worker({'url':'https://example.com', 'proxy':''})['formats'][0]
    assert combined['id']=='video+audio' and combined['drm']
    assert combined['label'].endswith(' · DRM')
