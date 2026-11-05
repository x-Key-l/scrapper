"""Small native WebView2 host lifecycle. The website processes have no backend token."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import threading
import webbrowser


def focus_existing(info):
    if os.name != 'nt' or not info.get('focus_event'):
        return False
    kernel = ctypes.windll.kernel32
    kernel.OpenEventW.restype = ctypes.c_void_p
    kernel.OpenEventW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    kernel.SetEvent.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenEventW(2, False, info['focus_event'])
    if not handle:
        return False
    try:
        return bool(kernel.SetEvent(handle))
    finally:
        kernel.CloseHandle(handle)


def launch(server, address, root, info):
    if os.name != 'nt':
        webbrowser.open(address)
        return
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1] / 'native/bin/Release/net48'
    executable = base / 'SceneTrace.Browser.exe'
    if not executable.is_file():
        webbrowser.open(address)
        return
    event = 'Local\\SceneTrace-' + server.instance
    info['focus_event'] = event
    environment = dict(os.environ, SCENETRACE_APP_URL=address, SCENETRACE_DESKTOP_TOKEN=server.app.desktop_token,
                       SCENETRACE_BROWSER_PROFILE=str(root / 'browser'), SCENETRACE_FOCUS_EVENT=event)
    process = subprocess.Popen([str(executable)], env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
    info['browser_pid'] = process.pid

    def monitor():
        code = process.wait()
        server.app.native_browser = False
        if code in (2, 3):
            webbrowser.open(address)
        else:
            server.shutdown()
    threading.Thread(target=monitor, name='browser-lifecycle', daemon=True).start()
    server.app.browser_process = process
