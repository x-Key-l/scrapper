"""Real HTTP files, redirects, buttons and range transfers for packaged Windows QA."""
import atexit
import io
import json
import ssl
import subprocess
import tempfile
from pathlib import Path
import os
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer


def start_fixture():
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('SceneTrace-native-download-test.bin',os.urandom(6*1024*1024))
    data=stream.getvalue()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path=='/redirect':
                self.send_response(302);self.send_header('Location','/slow.zip');self.end_headers();return
            if self.path.startswith('/slow.zip'):
                offset=int(self.headers.get('Range','bytes=0-').split('=')[1].split('-')[0])
                self.send_response(206 if offset else 200)
                self.send_header('Content-Type','application/zip')
                self.send_header('Content-Disposition','attachment; filename="native-test.zip"')
                self.send_header('Content-Length',str(len(data)-offset));self.send_header('Accept-Ranges','bytes')
                self.send_header('ETag','"scenetrace-native-fixture-v1"')
                if offset:self.send_header('Content-Range',f'bytes {offset}-{len(data)-1}/{len(data)}')
                self.end_headers()
                try:
                    for start in range(offset,len(data),32768):
                        self.wfile.write(data[start:start+32768]);self.wfile.flush();time.sleep(.015)
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
                return
            html=b'''<!doctype html><title>Native download fixture</title><h1>Ordinary website buttons</h1>
            <a id="download" href="/slow.zip">Download ZIP</a>
            <a id="redirect" href="/redirect">Redirected download</a>
            <button id="popup" onclick="window.open('/slow.zip','_blank')">Download in new window</button>
            <button id="blank" onclick="const w=window.open('about:blank');w.document.write('<title>Popup relationship</title><p>Opened by its original website</p>');">Open related popup</button>'''
            self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(html)));self.end_headers();self.wfile.write(html)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    # The real browser applies insecure-download policy to HTTP ZIP files. Use a
    # short-lived certificate trusted only in the disposable Windows CI user.
    # No production certificate validation or browser policy is disabled.
    if os.name == 'nt':
        directory=tempfile.TemporaryDirectory(prefix='scenetrace-qa-tls-')
        root=Path(directory.name)
        script=r"""
$ErrorActionPreference='Stop'
$cert=New-SelfSignedCertificate -DnsName 'download.scenetrace.test' -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddDays(1) -Type SSLServerAuthentication
$certPem=$cert.ExportCertificatePem()
$key=[System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($cert)
[IO.File]::WriteAllText((Join-Path $env:SCENETRACE_QA_CERT_DIR 'cert.pem'),$certPem)
[IO.File]::WriteAllText((Join-Path $env:SCENETRACE_QA_CERT_DIR 'key.pem'),$key.ExportPkcs8PrivateKeyPem())
Export-Certificate -Cert $cert -FilePath (Join-Path $env:SCENETRACE_QA_CERT_DIR 'cert.cer') | Out-Null
Import-Certificate -FilePath (Join-Path $env:SCENETRACE_QA_CERT_DIR 'cert.cer') -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
$cert.Thumbprint
"""
        thumbprint=subprocess.check_output(['pwsh','-NoProfile','-NonInteractive','-Command',script],env=dict(os.environ,SCENETRACE_QA_CERT_DIR=str(root)),text=True).strip()
        def cleanup():
            subprocess.run(['pwsh','-NoProfile','-NonInteractive','-Command',
                f"Remove-Item 'Cert:\\CurrentUser\\Root\\{thumbprint}','Cert:\\CurrentUser\\My\\{thumbprint}' -ErrorAction SilentlyContinue"],check=False)
            directory.cleanup()
        atexit.register(cleanup)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(root/'cert.pem',root/'key.pem')
        server.socket=context.wrap_socket(server.socket,server_side=True)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server,data
