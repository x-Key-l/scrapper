"""Exercise a real series through the application API and a completed file download."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

import imageio_ffmpeg


def run(command):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with tempfile.TemporaryDirectory(prefix='scenetrace-watch-qa-') as folder:
        root = Path(folder)
        env = dict(os.environ, SCENETRACE_DATA=folder)
        app = subprocess.Popen([*command, '--no-browser'], env=env)
        address = None
        try:
            for _ in range(300):
                try:
                    instance = json.loads((root / 'instance.json').read_text())
                    with opener.open(instance['url']+'/health', timeout=2) as reply:
                        if json.load(reply)['status'] == 'ok':
                            address = instance['url']
                            break
                except (OSError, ValueError):
                    time.sleep(.2)
            assert address, 'Packaged application did not become available'

            def post(path, payload):
                request = urllib.request.Request(address+'/api/'+path, json.dumps(payload).encode(),
                                                  {'Content-Type': 'application/json', 'X-SceneTrace': 'local'})
                try:
                    with opener.open(request, timeout=65) as reply:
                        return json.load(reply)
                except urllib.error.HTTPError as error:
                    detail = json.loads(error.read()).get('detail', str(error))
                    raise AssertionError(path + ' failed · ' + detail) from error

            report = []
            found = post('watch/search', {'query': 'Pocket Monsters', 'mode': 'anime', 'sources': ['pokemon-tv']})
            anime = next(row for row in found['results'] if row['source_id'] == 'pokemon-tv')
            episode_list = post('watch/details', {'record': anime})['episodes']
            assert len(episode_list) == 3
            episode = post('watch/play', {'ticket': episode_list[0]['ticket']})
            assert episode['original'] == 'https://www.youtube.com/watch?v=z3hMX65Khtg'
            assert not episode['formats']
            report.append({'source': 'Pokémon TV', 'search': 'Passed alternate title', 'episodes': len(episode_list),
                           'playback': 'Exact publisher handoff verified', 'embed_exposed': episode['playback'] == 'embed',
                           'embedded_frames': 'Owner test required', 'download': 'Publisher playback only'})

            found = post('watch/search', {'query': 'Caminandes', 'sources': ['open-animation']})
            movie = next(row for row in found['results'] if row['source_id'] == 'open-animation')
            episodes = post('watch/details', {'record': movie})['episodes']
            assert len(episodes) == 3
            episode = post('watch/play', {'ticket': episodes[2]['ticket']})
            assert episode['playback'] == 'direct', episode
            fmt = next(f for f in episode['formats'] if f['id'] == episode['playing_format_id'])
            transfer_started = time.perf_counter()
            job = post('download/add', {'analysis_id': episode['analysis_id'], 'format_id': fmt['id'],
                                        'destination': folder, 'authorized': True, 'output': 'original'})
            for _ in range(110):
                job = next(j for j in post('state', {})['downloads'] if j['id'] == job['id'])
                if job['status'] in ('completed', 'failed', 'cancelled'):
                    break
                time.sleep(1)
            assert job['status'] == 'completed', job
            transfer_seconds = time.perf_counter() - transfer_started
            output = Path(job['path'])
            assert output.stat().st_size > 100_000
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', str(output),
                            '-t', '2', '-f', 'null', '-'], capture_output=True, check=True, timeout=30)
            report.append({'source': 'Caminandes on Wikimedia Commons', 'search': 'Passed', 'episodes': len(episodes),
                           'playback': 'Player resolver checked real media bytes. Browser playback tested separately.',
                           'download': 'Complete and FFmpeg decoded', 'bytes': output.stat().st_size,
                           'queue_to_completion_seconds': round(transfer_seconds, 3),
                           'effective_mib_per_second': round(output.stat().st_size / 1048576 / transfer_seconds, 3),
                           'measurement_scope': 'One small licensed file on Windows CI; includes queue and one-second polling. Not an internet speed guarantee.',
                           'sha256': hashlib.sha256(output.read_bytes()).hexdigest()})
            Path('watch-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report, indent=2))
            post('shutdown', {})
            app.wait(timeout=25)
            assert app.returncode == 0
        finally:
            if app.poll() is None:
                app.kill()
                app.wait(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe')
    args = parser.parse_args()
    run([str(Path(args.exe).resolve())] if args.exe else [sys.executable, '-m', 'scenetrace'])
