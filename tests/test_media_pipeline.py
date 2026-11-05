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
            if self.path == '/throttled.mp4' and len(received) == 1:
                self.send_response(429)
                self.send_header('Retry-After', '1')
                self.end_headers()
                return
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


@pytest.mark.parametrize('output,throttled',[('original',False),('mp4',False),('mp3',False),('original',True)])
def test_http_download_and_real_ffmpeg_processing(tmp_path,fixture_server,fixture_video,output,throttled):
    value,received=fixture_server
    if throttled:
        value = value.replace('/sample.mp4', '/throttled.mp4')
    manager=DownloadManager(Store(tmp_path/'state'),'proxy',workers=1)
    try:
        start = time.monotonic()
        job=manager.add({'title':'Fixture','url':value},{'id':'0','ext':'mp4','method':'direct','url':value,'size':len(fixture_video)},str(tmp_path),True,output)
        done=wait(manager,job['id'])
        path=Path(done['path'])
        assert path.stat().st_size>100
        if output=='original':assert path.read_bytes()==fixture_video
        check=subprocess.run([media.ffmpeg_path(),'-v','error','-i',str(path),'-f','null','-'],capture_output=True)
        assert check.returncode==0,check.stderr
        assert received
        if throttled:
            assert len(received) == 2 and time.monotonic() - start >= 1
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


@pytest.mark.parametrize('container', ['hls', 'dash'])
def test_real_adaptive_manifest_download_and_decode(tmp_path, monkeypatch, container):
    """Real FFmpeg manifests, real HTTP segments, real yt-dlp child, actual decode."""
    from functools import partial
    from http.server import SimpleHTTPRequestHandler
    folder = tmp_path/'server'
    folder.mkdir()
    manifest = folder/('index.m3u8' if container == 'hls' else 'index.mpd')
    args = [media.ffmpeg_path(), '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
            'testsrc2=s=96x64:r=10', '-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=22050',
            '-t', '2', '-c:v', 'libx264', '-g', '10', '-c:a', 'aac']
    args += ['-f','hls','-hls_time','1','-hls_list_size','0'] if container == 'hls' else ['-f','dash','-seg_duration','1']
    subprocess.run(args+[str(manifest)], check=True, capture_output=True)
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
    host = ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(folder)))
    threading.Thread(target=host.serve_forever,daemon=True).start()
    original = network.target
    def target(value):
        parsed=urlsplit(value)
        if parsed.hostname=='adaptive.example': return parsed,parsed.hostname,host.server_port,'127.0.0.1'
        return original(value)
    monkeypatch.setattr(network,'target',target)
    proxy=network.start_proxy()
    manager=None
    try:
        proxy_url='http://127.0.0.1:'+str(proxy.server_port)
        info=media.analyze('http://adaptive.example/'+manifest.name,proxy_url)
        assert info['formats'], info
        fmt=next((f for f in info['formats'] if f['video'] and f['audio']),None)
        assert fmt,info
        original_popen=subprocess.Popen
        worker_log=tmp_path/'worker-diagnostic.txt'
        log_file=worker_log.open('w')
        def diagnostic_popen(args,**kwargs):
            if '--worker' in args: kwargs['stderr']=log_file
            return original_popen(args,**kwargs)
        monkeypatch.setattr(subprocess,'Popen',diagnostic_popen)
        manager=DownloadManager(Store(tmp_path/'state'),proxy_url,workers=1)
        job=manager.add(info,fmt,str(tmp_path))
        try:
            done=wait(manager,job['id'])
        except AssertionError as error:
            log_file.flush()
            raise AssertionError(str(error)+'\nControlled fixture worker: '+worker_log.read_text()) from error
        finally:
            log_file.close()

        subprocess.run([media.ffmpeg_path(),'-v','error','-i',done['path'],'-map','0:v:0','-map','0:a:0','-f','null','-'],check=True,capture_output=True,timeout=15)
    finally:
        if manager: manager.close()
        proxy.shutdown();proxy.server_close();host.shutdown();host.server_close()


def test_format_compatibility_does_not_invent_container_restrictions():
    for protocol in ['http','https','m3u8_native','http_dash_segments']:
        assert not media.format_issue({'ext':'mkv','protocol':protocol})
    assert media.format_issue({'ext':'../exe','protocol':'https'})
    assert media.format_issue({'ext':'mp4','protocol':'https','has_drm':True})
    assert media.failure_detail('SSL: CERTIFICATE_VERIFY_FAILED')['code']=='certificate'
    assert media.failure_detail('unrecognized extraction failure https://secret/?token=private')['code']=='extraction'
    assert 'private' not in str(media.failure_detail('unrecognized extraction failure https://secret/?token=private'))
