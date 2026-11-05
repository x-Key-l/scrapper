"""Launch the actual packaged executable and exercise its actual WebView2 host."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import psutil

parser = argparse.ArgumentParser()
parser.add_argument('--exe', default='dist/SceneTrace/SceneTrace.exe')
args = parser.parse_args()
exe = Path(args.exe).resolve()
artifacts = Path('artifacts/native-browser').resolve()
artifacts.mkdir(parents=True, exist_ok=True)


def post(address, path, body):
    request = urllib.request.Request(address+'/api/'+path, json.dumps(body).encode(),
                                     {'Content-Type':'application/json', 'X-SceneTrace':'local'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=8) as response:
        return json.load(response)


with tempfile.TemporaryDirectory(prefix='scenetrace-native-qa-', ignore_cleanup_errors=True) as profile:
    reports = []
    for index in range(2):
        report = artifacts / ('cold.json' if index == 0 else 'warm.json')
        report.unlink(missing_ok=True)
        env = dict(os.environ, SCENETRACE_DATA=profile, SCENETRACE_BROWSER_REPORT=str(report),
                   SCENETRACE_TEST_FIXTURES=str(Path('tests/browser-fixtures').resolve()))
        started = time.perf_counter()
        process = subprocess.Popen([str(exe)], env=env)
        address = None
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                try:
                    info = json.loads((Path(profile)/'instance.json').read_text())
                    address = info['url']
                    state = post(address, 'state', {})
                    break
                except (ValueError, OSError):
                    time.sleep(.1)
            else:
                raise RuntimeError('Packaged backend did not become ready.')
            backend_ready = time.perf_counter()-started
            backend_rss = psutil.Process(process.pid).memory_info().rss/1048576
            if index == 0:
                post(address, 'save', {'record':{'id':'upgrade:keep', 'title':'Keep through restart'}})
                post(address, 'search', {'query':'Caminandes', 'sources':['open-animation']})
                history = post(address, 'history/list', {})['entries']
                assert history
                post(address, 'history/delete', {'ids':[history[0]['id']]})
                post(address, 'settings', {'record_history': False})
            else:
                assert any(r['id']=='upgrade:keep' for r in state['saved'])
                assert state['settings']['record_history'] is False
                assert post(address, 'history/list', {})['entries'] == []
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline and not report.is_file():
                if process.poll() is not None:
                    raise RuntimeError('The packaged application exited without native browser evidence.')
                time.sleep(.2)
            result = json.loads(report.read_text())
            assert result['success'], result
            result.update(backend_ready_seconds=round(backend_ready, 3), backend_rss_mib=round(backend_rss, 2))
            process.wait(timeout=20)
            assert process.returncode == 0
            reports.append(result)
            report.write_text(json.dumps(result, indent=2))
        finally:
            if process.poll() is None:
                try:
                    if address: post(address, 'shutdown', {})
                    process.wait(timeout=15)
                except (OSError, subprocess.TimeoutExpired):
                    process.kill()
                    process.wait()
    print(json.dumps({'runs':reports, 'persistence':'Saved item, disabled recording and individual deletion survive restart'}, indent=2))
