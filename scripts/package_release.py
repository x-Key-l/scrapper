"""Stage portable bundle, dependency notices, evidence and checksums."""
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import imageio_ffmpeg
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scenetrace import __version__

stage=Path('release')/'SceneTrace'
if stage.exists():shutil.rmtree(stage)
shutil.copytree('dist/SceneTrace',stage)
for name in ('README.md','START-HERE.txt','THIRD-PARTY-NOTICES.md'):
    shutil.copyfile(name,stage/name)
shutil.copytree('docs',stage/'docs',dirs_exist_ok=True)
licenses=stage/'licenses'
licenses.mkdir(exist_ok=True)
for source in Path("native/Filters").glob("*"):
    if source.name.endswith((".txt.gz.b64", "-HaGeZi.txt")):
        shutil.copyfile(source,licenses/source.name)
for name in ('yt-dlp','imageio-ffmpeg','pyinstaller','beautifulsoup4','soupsieve','truststore'):
    d=importlib.metadata.distribution(name)
    for p in d.files:
        if 'LICENSE' in str(p).upper() or Path(str(p)).name.upper().startswith('COPYING'):
            source=Path(d.locate_file(p))
            if source.is_file():
                shutil.copyfile(source,licenses/(name+'-'+source.name))
ffmpeg=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-L'],capture_output=True,text=True)
(licenses/'FFmpeg-build-and-license.txt').write_text(ffmpeg.stdout+ffmpeg.stderr,encoding='utf-8')
for name in ('live-results.json', 'watch-results.json'):
    if Path(name).exists():
        shutil.copyfile(name, stage/'docs'/name)
for name in ('cold.json', 'warm.json'):
    path = Path('artifacts/native-browser')/name
    if path.exists(): shutil.copyfile(path, stage/'docs'/('native-browser-'+name))
benchmark=Path('artifacts/library-benchmark.json')
if benchmark.exists():shutil.copyfile(benchmark,stage/'docs'/benchmark.name)
path = Path('artifacts/v4-live/results.json')
if path.exists(): shutil.copyfile(path, stage/'docs'/'website-live-results.json')
sdk = Path.home()/'.nuget/packages/microsoft.web.webview2/1.0.3537.50'
for path in sdk.rglob('*'):
    if path.is_file() and path.name.lower() in ('license.txt', 'license.md', 'license', 'thirdpartynotices.txt'):
        shutil.copyfile(path, licenses/('WebView2-'+path.name))
(stage/'docs'/'BUILD.json').write_text(json.dumps({'version':__version__,'commit':os.environ.get('GITHUB_SHA','local'),
    'python':sys.version,'os':sys.platform,'yt_dlp':importlib.metadata.version('yt-dlp'),
    'imageio_ffmpeg':importlib.metadata.version('imageio-ffmpeg'),'verification':'Source tests, packaged executable HTTP/restart checks, native WebView2 isolation/navigation/crash recovery/playback, licensed download and browser UI workflows precede packaging in CI.'},indent=2),encoding='utf-8')
archive=shutil.make_archive('SceneTrace-Windows-x64','zip','release','SceneTrace')
digest=hashlib.sha256(Path(archive).read_bytes()).hexdigest()
Path('SceneTrace-Windows-x64.sha256').write_text(digest+'  SceneTrace-Windows-x64.zip\n')
print('Packaged '+archive)
