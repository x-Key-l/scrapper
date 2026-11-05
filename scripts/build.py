"""Build self-contained onedir bundle with yt-dlp, Tk dialogs and FFmpeg."""
import subprocess
import sys
import imageio_ffmpeg
from pathlib import Path
import shutil

subprocess.run([sys.executable,'-m','PyInstaller','--clean','--noconfirm','--onedir',
                '--console','--name','SceneTrace','--collect-all','yt_dlp',
                '--collect-all','imageio_ffmpeg','--hidden-import','tkinter',
                '--hidden-import','tkinter.filedialog','--add-data','scenetrace/web'+(';' if sys.platform=='win32' else ':')+'scenetrace/web',
                'desktop.py'],check=True)
if sys.platform == 'win32':
    subprocess.run(['dotnet', 'build', 'native/SceneTrace.Browser.csproj', '-c', 'Release'], check=True)
    native = Path('native/bin/Release/net48')
    for name in ('SceneTrace.Browser.exe', 'SceneTrace.Browser.exe.config',
                 'Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll'):
        shutil.copyfile(native/name, Path('dist/SceneTrace')/name)
    loader = next(native.rglob('WebView2Loader.dll'))
    candidates = [p for p in native.rglob('WebView2Loader.dll') if 'win-x64' in str(p) or '\\x64\\' in str(p)]
    if candidates: loader = candidates[0]
    shutil.copyfile(loader, 'dist/SceneTrace/WebView2Loader.dll')
