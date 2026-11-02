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

stage=Path('release')/'SceneTrace'
if stage.exists():shutil.rmtree(stage)
shutil.copytree('dist/SceneTrace',stage)
for name in ('README.md','START-HERE.txt','THIRD-PARTY-NOTICES.md'):
    shutil.copyfile(name,stage/name)
shutil.copytree('docs',stage/'docs',dirs_exist_ok=True)
licenses=stage/'licenses'
licenses.mkdir(exist_ok=True)
for name in ('yt-dlp','imageio-ffmpeg','pyinstaller'):
    d=importlib.metadata.distribution(name)
    for p in d.files:
        if 'LICENSE' in str(p).upper() or Path(str(p)).name.upper().startswith('COPYING'):
            source=Path(d.locate_file(p))
            if source.is_file():
                shutil.copyfile(source,licenses/(name+'-'+source.name))
ffmpeg=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-L'],capture_output=True,text=True)
(licenses/'FFmpeg-build-and-license.txt').write_text(ffmpeg.stdout+ffmpeg.stderr,encoding='utf-8')
if Path('live-results.json').exists():shutil.copyfile('live-results.json',stage/'docs'/'live-results.json')
(stage/'docs'/'BUILD.json').write_text(json.dumps({'version':'2.0.0','commit':os.environ.get('GITHUB_SHA','local'),
    'python':sys.version,'os':sys.platform,'yt_dlp':importlib.metadata.version('yt-dlp'),
    'imageio_ffmpeg':importlib.metadata.version('imageio-ffmpeg'),'verification':'Source tests and packaged executable HTTP smoke test precede packaging in CI.'},indent=2),encoding='utf-8')
archive=shutil.make_archive('SceneTrace-Windows-x64','zip','release','SceneTrace')
digest=hashlib.sha256(Path(archive).read_bytes()).hexdigest()
Path('SceneTrace-Windows-x64.sha256').write_text(digest+'  SceneTrace-Windows-x64.zip\n')
print('Packaged '+archive)
