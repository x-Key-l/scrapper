"""Build self-contained onedir bundle with yt-dlp, Tk dialogs and FFmpeg."""
import subprocess
import sys
import imageio_ffmpeg

subprocess.run([sys.executable,'-m','PyInstaller','--clean','--noconfirm','--onedir',
                '--console','--name','SceneTrace','--collect-all','yt_dlp',
                '--collect-all','imageio_ffmpeg','--hidden-import','tkinter',
                '--hidden-import','tkinter.filedialog','--add-data','scenetrace/web'+(';' if sys.platform=='win32' else ':')+'scenetrace/web',
                'desktop.py'],check=True)
