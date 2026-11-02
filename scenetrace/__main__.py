"""Single-instance Windows launcher and loopback HTTP service."""
import argparse
import ctypes
import json
import logging
import logging.handlers
import os
import secrets
import signal
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from . import __version__
from .network import start_proxy
from .app import App

ROOT=Path(__file__).resolve().parent
PUBLIC=ROOT/'web'
MIME={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.svg':'image/svg+xml'}


class Handler(BaseHTTPRequestHandler):
    server_version='SceneTrace/'+__version__
    def setup(self):
        super().setup()
        self.connection.settimeout(40)
    def log_message(self,*args): pass
    def send(self,status,value,mime='application/json; charset=utf-8'):
        data=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status)
        for k,v in {'Content-Type':mime,'Content-Length':str(len(data)),'Cache-Control':'no-store',
                    'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
                    'Cross-Origin-Resource-Policy':'same-origin',
                    'Content-Security-Policy':"default-src 'self'; img-src 'self' https: data:; media-src https:; connect-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"}.items():
            self.send_header(k,v)
        self.end_headers()
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass
    def host_ok(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
    def do_GET(self):
        if not self.host_ok(): return self.send(403,{'detail':'Local access only.'})
        path=urlsplit(self.path).path
        if path=='/health':
            return self.send(200,{'app':'SceneTrace','status':'ok','version':__version__,'instance':self.server.instance})
        asset='index.html' if path=='/' else path.lstrip('/')
        # Serve only flat bundled assets, never arbitrary local paths.
        if asset not in ('index.html','style.css','app.js','icon.svg'):
            return self.send(404,{'detail':'Not found.'})
        file=PUBLIC/asset
        return self.send(200,file.read_bytes(),MIME.get(file.suffix,'application/octet-stream'))
    def do_POST(self):
        if not self.host_ok(): return self.send(403,{'detail':'Local access only.'})
        origins=(f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}')
        if self.headers.get('Origin') and self.headers['Origin'] not in origins:
            return self.send(403,{'detail':'External webpages cannot access this local API.'})
        if self.headers.get('Sec-Fetch-Site','same-origin') not in ('same-origin','none') or self.headers.get('X-SceneTrace')!='local':
            return self.send(403,{'detail':'Open SceneTrace in its own browser tab.'})
        if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json':
            return self.send(400,{'detail':'Use a JSON request.'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 2<=length<=48*1024*1024:
                return self.send(413,{'detail':'For large imports use Choose file on this PC; it streams the database without a browser upload.'})
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict): raise ValueError('Invalid request.')
            if self.path=='/api/shutdown':
                self.send(200,{'ok':True})
                threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            if not self.server.slots.acquire(False):
                return self.send(429,{'detail':'SceneTrace is busy. Wait for an operation to finish.'})
            try:
                result=self.server.app.call(self.path,body)
            finally:self.server.slots.release()
            return self.send(200,result)
        except ValueError as exc:return self.send(400,{'detail':str(exc)[:600]})
        except Exception as exc:
            logging.getLogger('scenetrace').warning('request_failed action=%s kind=%s',urlsplit(self.path).path,type(exc).__name__)
            return self.send(502,{'detail':'The operation could not finish. Check the source, destination or internet connection and try again.'})


def make_server(root,port=0):
    proxy=start_proxy()
    try:
        app=App(root,'http://127.0.0.1:'+str(proxy.server_port))
        server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    except BaseException:
        proxy.shutdown()
        raise
    server.daemon_threads=True
    server.instance=secrets.token_urlsafe(24)
    server.slots=threading.BoundedSemaphore(10)
    server.app=app
    server.proxy=proxy
    return server


def data_dir():
    if os.environ.get('SCENETRACE_DATA'):
        return Path(os.environ['SCENETRACE_DATA'])
    return Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local'/'share')))/'SceneTrace'


class Instance:
    def __init__(self,root):
        self.path=Path(root)/'instance.json'
        self.file=(Path(root)/'instance.lock').open('a+b')
    def acquire(self):
        try:
            if os.name=='nt':
                import msvcrt
                self.file.seek(0)
                if not self.file.read(1):
                    self.file.write(b'0');self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return True
        except (OSError,BlockingIOError):return False
    def existing(self):
        for _ in range(40):
            try:
                value=json.loads(self.path.read_text())
                u=urlsplit(value['url'])
                if u.scheme!='http' or u.hostname!='127.0.0.1':return None
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(value['url']+'/health',timeout=.5) as r:
                    health=json.load(r)
                if health.get('app')=='SceneTrace' and health.get('instance')==value['instance']:
                    return value['url']
            except Exception as exc:
                logging.getLogger('scenetrace').warning('instance_probe_failed kind=%s',type(exc).__name__)
            time.sleep(.1)
        return None
    def close(self):
        self.file.close()


def main():
    if '--worker' in sys.argv:
        from .media import worker
        try:
            print(json.dumps(worker(json.load(sys.stdin))),flush=True)
        except Exception:
            sys.exit(1)
        return
    parser=argparse.ArgumentParser()
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    if os.name=='nt' and not args.no_browser:
        # Hide only the console created for a double-click, never a caller's terminal.
        processes=(ctypes.c_uint32*2)()
        if ctypes.windll.kernel32.GetConsoleProcessList(processes,2)==1:
            window=ctypes.windll.kernel32.GetConsoleWindow()
            if window:ctypes.windll.user32.ShowWindow(window,0)
    root=data_dir()
    root.mkdir(parents=True,exist_ok=True)
    handler=logging.handlers.RotatingFileHandler(root/'diagnostics.log',maxBytes=512000,backupCount=2,encoding='utf-8')
    logging.getLogger('scenetrace').addHandler(handler)
    instance=Instance(root)
    if not instance.acquire():
        existing=instance.existing()
        instance.close()
        if existing:
            if not args.no_browser:webbrowser.open(existing)
            return
        raise RuntimeError('SceneTrace is already starting or closing. Wait a few seconds and open it again.')
    server=None
    try:
        server=make_server(root,args.port)
        address='http://127.0.0.1:'+str(server.server_port)
        instance.path.write_text(json.dumps({'url':address,'instance':server.instance}),encoding='utf-8')
        for sig in (signal.SIGINT,signal.SIGTERM):
            signal.signal(sig,lambda *_:threading.Thread(target=server.shutdown,daemon=True).start())
        if not args.no_browser:webbrowser.open(address)
        if sys.stdout:print('SceneTrace '+address,flush=True)
        server.serve_forever(poll_interval=.2)
    finally:
        if server:
            server.app.close()
            server.server_close()
            server.proxy.shutdown()
            server.proxy.server_close()
        instance.path.unlink(missing_ok=True)
        instance.close()


def entry():
    try:
        main()
    except Exception as exc:
        logging.getLogger('scenetrace').error('startup_failed kind=%s',type(exc).__name__)
        message='SceneTrace could not start. '+str(exc)[:300]+'\nTry extracting the full ZIP again. Diagnostics are in your SceneTrace settings folder.'
        if os.name=='nt' and '--worker' not in sys.argv:
            ctypes.windll.user32.MessageBoxW(None,message,'SceneTrace',0x10)
        elif sys.stderr:print(message,file=sys.stderr)
        raise SystemExit(1)


if __name__=='__main__':entry()
