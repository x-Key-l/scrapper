"""Pinned public-network transport, adapted from SceneTrace PC security.py."""
import http.client
import ipaddress
import json
import select
import socket
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin, urlsplit


class SourceError(ValueError):
    pass


class UnsafeURL(SourceError):
    pass


def target(url):
    if not isinstance(url, str) or len(url) > 16384 or any(ord(c) < 33 for c in url):
        raise UnsafeURL('Enter a valid public HTTP or HTTPS URL.')
    try:
        p = urlsplit(url)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
            raise UnsafeURL('Use a public HTTP(S) URL without embedded credentials.')
        host = p.hostname.encode('idna').decode('ascii').lower()
        port = p.port or (443 if p.scheme == 'https' else 80)
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            raise UnsafeURL('Local and private network addresses cannot be fetched.')
        ips = [a[4][0] for a in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise UnsafeURL('Private, reserved, and mixed DNS addresses are blocked.')
        return p, host, port, ips[0]
    except (ValueError, UnicodeError, socket.gaierror) as e:
        raise UnsafeURL('The public hostname could not be safely resolved.') from e


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.ip = ip

    def connect(self):
        sock = socket.create_connection((self.ip, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def open_url(url, method='GET', data=None, headers=None, timeout=12):
    extra = dict(headers or {})
    original_host = urlsplit(url).hostname
    for _ in range(6):
        p, host, port, ip = target(url)
        if host != original_host:
            extra = {k: v for k, v in extra.items() if k.lower() not in ('authorization', 'x-api-key', 'api-key')}
        conn = PinnedHTTPS(host, port, ip, timeout) if p.scheme == 'https' else http.client.HTTPConnection(ip, port, timeout=timeout)
        try:
            conn.request(method, (p.path or '/') + ('?' + p.query if p.query else ''), data,
                         {'Host': p.netloc, 'User-Agent': 'SceneTrace/2.0 (desktop video discovery)', 'Accept-Encoding': 'identity', **extra})
            r = conn.getresponse()
            if r.status in (301, 302, 303, 307, 308):
                location = r.getheader('Location')
                conn.close()
                if not location:
                    raise SourceError('Source redirected without a destination.')
                new = urljoin(url, location)
                if p.scheme == 'https' and urlsplit(new).scheme != 'https':
                    raise UnsafeURL('The source attempted to downgrade HTTPS.')
                url = new
                if r.status == 303 or (r.status in (301, 302) and method == 'POST'):
                    method, data = 'GET', None
                continue
            if r.status == 429:
                raise SourceError('Provider rate limit reached. Retry after ' + str(r.getheader('Retry-After', '60'))[:20] + ' seconds.')
            if r.status not in (200, 206):
                raise SourceError(f'Source returned HTTP {r.status}. Check its status or credentials.')
            return conn, r, url
        except BaseException:
            conn.close()
            raise
    raise SourceError('Too many redirects from this source.')


def fetch(url, method='GET', data=None, headers=None, limit=16*1024*1024):
    conn, response, final = open_url(url, method, data, headers)
    try:
        body = response.read(limit + 1)
        if len(body) > limit:
            raise SourceError('This metadata response is too large. Import a local export instead.')
        return body, response.getheader('Content-Type', ''), final
    finally:
        conn.close()


def json_request(url, payload=None, headers=None):
    h = {'Accept': 'application/json', **(headers or {})}
    if payload is not None:
        h['Content-Type'] = 'application/json'
    try:
        return json.loads(fetch(url, 'POST' if payload is not None else 'GET', json.dumps(payload).encode() if payload is not None else None, h)[0])
    except (json.JSONDecodeError, UnicodeError) as e:
        raise SourceError('The source did not return valid JSON. Check the API endpoint.') from e


class Proxy(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_CONNECT(self):
        remote = None
        try:
            _, _, port, ip = target('https://' + self.path)
            remote = socket.create_connection((ip, port), timeout=12)
            self.send_response(200)
            self.end_headers()
            self.connection.settimeout(20)
            while True:
                ready, _, _ = select.select([self.connection, remote], [], [], 25)
                if not ready:
                    return
                for src in ready:
                    chunk = src.recv(65536)
                    if not chunk:
                        return
                    (remote if src is self.connection else self.connection).sendall(chunk)
        except Exception:
            if remote is None:
                self.send_error(403, 'Destination blocked or unreachable')
        finally:
            if remote:
                remote.close()
            self.close_connection = True

    def relay(self):
        conn = None
        try:
            headers = {k: v for k, v in self.headers.items() if k.lower() in ('range', 'if-range', 'accept', 'content-type')}
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > 2*1024*1024:
                raise ValueError('Request too large')
            data = self.rfile.read(length) if length else None
            conn, r, _ = open_url(self.path, self.command, data, headers)
            self.send_response(r.status)
            for k in ('Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges', 'ETag', 'Last-Modified'):
                if r.getheader(k):
                    self.send_header(k, r.getheader(k))
            self.end_headers()
            if self.command != 'HEAD':
                while chunk := r.read(65536):
                    self.wfile.write(chunk)
        except Exception:
            if conn is None:
                self.send_error(502, 'Source unavailable')
        finally:
            if conn:
                conn.close()
            self.close_connection = True

    do_GET = relay
    do_HEAD = relay
    do_POST = relay


def start_proxy():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
