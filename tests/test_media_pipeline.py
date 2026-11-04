"""Actual HTTP, yt-dlp subprocess and FFmpeg tests against a controlled fixture."""
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch
import pytest
from scenetrace import media, network
from scenetrace.downloads import DownloadManager
from scenetrace.store import Store


@pytest.fixture
def fixture_video(tmp_path):
    ffmpeg=media.ffmpeg_path()
    assert ffmpeg, 'The release requires bundled FFmpeg.'
    sample=tmp_path/'sample.mp4'
    subprocess.run([ffmpeg,'-nostdin','-v','error','-f','lavfi','-i','color=c=blue:s=64x64:r=10',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=22050','-t','0.5',
                    '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-y',str(sample)],check=True)
    return sample.read_bytes()


@pytest.fixture
def fixture_server(fixture_video):
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_HEAD(self):self.respond(False)
        def do_GET(self):self.respond(True)
        def respond(self,body):
            received.append(dict(self.headers))
            offset=int(self.headers.get('Range','bytes=0-').split('=')[1].split('-')[0])
            partial='Range' in self.headers
            self.send_response(206 if partial else 200)
            self.send_header('Content-Type','video/mp4')
            self.send_header('Content-Length',str(len(fixture_video)-offset))
            self.send_header('Accept-Ranges','bytes')
            self.send_header('ETag','"fixture-v1"')
            if partial:self.send_header('Content-Range',f'bytes {offset}-{len(fixture_video)-1}/{len(fixture_video)}')
            self.end_headers()
            if body:self.wfile.write(fixture_video[offset:])
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    threading.Thread(target=server.serve_forever,daemon=True).start()
    original_target=network.target
    def fixture_target(value):
        p=urlsplit(value)
        if p.hostname=='fixture.example':
            return p,'fixture.example',server.server_port,'127.0.0.1'
        return original_target(value)
    try:
        # Scoped only to this test's parent process. Production transport is unchanged.
        with patch('scenetrace.network.target',side_effect=fixture_target):
            yield 'http://fixture.example/sample.mp4',received
    finally:
        server.shutdown();server.server_close()


def wait(manager,key):
    end=time.monotonic()+25
    while time.monotonic()<end:
        job=manager.items[key]
        if job['status'] in ('failed','completed') and not job.get('_running'):
            assert job['status']=='completed',job.get('error')
            return job
        time.sleep(.05)
    raise AssertionError('Fixture transfer timed out')


@pytest.mark.parametrize('output',['original','mp4','mp3'])
def test_http_download_and_real_ffmpeg_processing(tmp_path,fixture_server,fixture_video,output):
    value,received=fixture_server
    manager=DownloadManager(Store(tmp_path/'state'),'proxy',workers=1)
    try:
        job=manager.add({'title':'Fixture','url':value},{'id':'0','ext':'mp4','method':'direct','url':value,'size':len(fixture_video)},str(tmp_path),True,output)
        done=wait(manager,job['id'])
        path=Path(done['path'])
        assert path.stat().st_size>100
        if output=='original':assert path.read_bytes()==fixture_video
        check=subprocess.run([media.ffmpeg_path(),'-v','error','-i',str(path),'-f','null','-'],capture_output=True)
        assert check.returncode==0,check.stderr
        assert received
    finally:manager.close()


def test_yt_dlp_worker_uses_validating_proxy_and_downloads_reported_format(tmp_path,fixture_server):
    value,_=fixture_server
    proxy=network.start_proxy()
    manager=None
    try:
        proxy_url='http://127.0.0.1:'+str(proxy.server_port)
        info=media.analyze(value,proxy_url)
        assert info['formats'] and info['extractor']=='Generic'
        manager=DownloadManager(Store(tmp_path/'state'),proxy_url,workers=1)
        job=manager.add(info,info['formats'][0],str(tmp_path),True)
        done=wait(manager,job['id'])
        assert Path(done['path']).is_file()
    finally:
        if manager:manager.close()
        proxy.shutdown();proxy.server_close()


def test_yt_dlp_merges_separate_authorized_http_tracks(tmp_path, fixture_video, monkeypatch):
    """Supply a deterministic extractor manifest and exercise real transfers and FFmpeg."""
    from functools import partial
    from http.server import SimpleHTTPRequestHandler
    import yt_dlp

    original = tmp_path / 'input.mp4'
    original.write_bytes(fixture_video)
    ffmpeg = media.ffmpeg_path()
    for selector, name in [('0:v:0', 'video.mp4'), ('0:a:0', 'audio.m4a')]:
        subprocess.run([ffmpeg, '-v', 'error', '-i', str(original), '-map', selector,
                        '-c', 'copy', str(tmp_path / name)], check=True)

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    host = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(tmp_path)))
    threading.Thread(target=host.serve_forever, daemon=True).start()
    proxy = network.start_proxy()
    target = network.target
    def resolve(value):
        parsed = urlsplit(value)
        if parsed.hostname == 'tracks.example':
            return parsed, parsed.hostname, host.server_port, '127.0.0.1'
        return target(value)

    def extract(self, value, download=True, **kwargs):
        return self.process_ie_result({
            'id': 'fixture', 'title': 'Authorized two-track video',
            'extractor': 'fixture', 'webpage_url': value,
            'formats': [
                {'format_id': 'video1', 'url': 'http://tracks.example/video.mp4', 'ext': 'mp4',
                 'protocol': 'http', 'vcodec': 'h264', 'acodec': 'none', 'height': 64},
                {'format_id': 'audio1', 'url': 'http://tracks.example/audio.m4a', 'ext': 'm4a',
                 'protocol': 'http', 'vcodec': 'none', 'acodec': 'aac'},
            ],
        }, download=download)

    monkeypatch.setattr(network, 'target', resolve)
    monkeypatch.setattr(yt_dlp.YoutubeDL, 'extract_info', extract)
    output = tmp_path / 'combined.mkv'
    request = {'url': 'http://tracks.example/player', 'proxy': 'http://127.0.0.1:' + str(proxy.server_port)}
    try:
        formats = media.worker(request)['formats']
        pair = next(item for item in formats if item['id'] == 'video1+audio1')
        assert pair['ext'] == 'mkv' and pair['audio'] and pair['video']
        assert media.worker(dict(request, download=True, format_id=pair['id'], output=str(output)))['complete']
        subprocess.run([ffmpeg, '-v', 'error', '-i', str(output), '-map', '0:v:0', '-map', '0:a:0',
                        '-f', 'null', '-'], capture_output=True, check=True, timeout=15)
    finally:
        host.shutdown()
        host.server_close()
        proxy.shutdown()
        proxy.server_close()
