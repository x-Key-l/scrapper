"""Reproducible v3 baseline and public website diagnosis. Run on both CI platforms."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.robotparser

import psutil

parser = argparse.ArgumentParser()
parser.add_argument('--root', default='.')
args = parser.parse_args()
root = Path(args.root).resolve()
sys.path.insert(0, str(root))
from scenetrace import network, websites

out = Path('artifacts/v4-baseline')
out.mkdir(parents=True, exist_ok=True)
report = {'platform': sys.platform, 'revision': '5383d468d3ce0fe2c21e2b86f80636399707869b'}


def post(address, path, body):
    request = urllib.request.Request(address + '/api/' + path, json.dumps(body).encode(),
                                     {'Content-Type': 'application/json', 'X-SceneTrace': 'local'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=40) as reply:
        return json.load(reply)


def memory(process):
    try:
        tree = [psutil.Process(process.pid)]
        tree += tree[0].children(recursive=True)
        return round(sum(p.memory_info().rss for p in tree if p.is_running()) / 1048576, 2)
    except psutil.Error:
        return None


with tempfile.TemporaryDirectory(prefix='scenetrace-v3-benchmark-') as folder:
    measurements = []
    for attempt in range(2):
        start = time.perf_counter()
        process = subprocess.Popen([sys.executable, '-m', 'scenetrace', '--no-browser'], cwd=root,
                                   env=dict(os.environ, SCENETRACE_DATA=folder), stdout=subprocess.DEVNULL)
        try:
            for _ in range(200):
                try:
                    address = json.loads((Path(folder) / 'instance.json').read_text())['url']
                    state = post(address, 'state', {})
                    break
                except (OSError, ValueError):
                    time.sleep(.05)
            else:
                raise RuntimeError('Baseline startup failed')
            elapsed = time.perf_counter() - start
            idle = memory(process)
            start = time.perf_counter()
            result = post(address, 'watch/search', {'query': 'Caminandes', 'sources': ['open-animation']})
            quick = time.perf_counter() - start
            start = time.perf_counter()
            deep = post(address, 'search', {'query': 'llama Patagonia', 'mode': 'memory', 'sources': ['open-animation']})
            measurements.append({'launch': 'fresh profile' if attempt == 0 else 'existing profile',
                                 'backend_ready_seconds': round(elapsed, 3), 'backend_rss_mib': idle,
                                 'local_quick_seconds': round(quick, 4),
                                 'local_memory_seconds': round(time.perf_counter() - start, 4),
                                 'quick_count': len(result['results']), 'memory_count': len(deep['results'])})
            post(address, 'shutdown', {})
            process.wait(timeout=20)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    report['backend'] = measurements
    report['measurement_scope'] = 'Source application on shared CI hardware. Browser process measurements are recorded separately.'

value = 'https://hianime.ms/'
diagnostic = {'website': value, 'query': 'Naruto'}
try:
    try:
        raw, _, _ = network.fetch(value + 'robots.txt')
        robot = urllib.robotparser.RobotFileParser()
        robot.parse(raw.decode(errors='replace').splitlines())
        diagnostic['robots'] = raw.decode(errors='replace')[:6000]
        if not robot.can_fetch('SceneTrace', value + 'search?keyword=Naruto'):
            raise ValueError('The published robots rules disallow automated search. Manual browsing remains available.')
    except network.SourceError as error:
        diagnostic['robots_request'] = str(error)
    detected = websites.inspect(value)
    diagnostic['detected'] = detected
    source = dict(id='hianime-audit', name='HiAnime', endpoint=detected['endpoint'],
                  categories=['anime'], web_config=websites.validate(detected))
    target = websites.search_url(source, 'Naruto', 1)
    diagnostic['generated_url'] = target
    page, final = websites.fetch_page(target)
    diagnostic['final_url'] = final
    diagnostic['title'] = page.title.get_text() if page.title else ''
    diagnostic['forms'] = [{'method': form.get('method'), 'action': form.get('action'),
                           'fields': [{'name': x.get('name'), 'type': x.get('type'), 'value': x.get('value')}
                                      for x in form.select('input[name]')]} for form in page.select('form')]
    diagnostic['naruto_links'] = [{'href': a.get('href'), 'text': a.get_text(' ', strip=True)[:180],
                                  'class': a.get('class'), 'parent_class': a.parent.get('class')}
                                 for a in page.select('a[href]') if 'naruto' in str(a).lower()][:30]
    diagnostic['matching_selector_count'] = len(page.select(source['web_config']['result_selector']))
    rows, _ = websites.search(source, 'Naruto', 1)
    diagnostic['original_result_count'] = len(rows)
    diagnostic['results'] = [{'title': row['title'], 'url': row['url']} for row in rows[:10]]
    (out / 'hianime-search.html').write_text(str(page), encoding='utf-8')
except Exception as error:
    diagnostic['error_type'] = type(error).__name__
    diagnostic['error'] = str(error)
report['hianime'] = diagnostic
(out / 'baseline.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=True, indent=2))
