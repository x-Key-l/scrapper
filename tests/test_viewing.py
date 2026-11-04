import shutil
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import pytest

from scenetrace import network, open_catalog
from scenetrace.viewing import official_episode, open_license, youtube_id


@pytest.mark.parametrize('query', ['Pokémon', 'Pokemon', 'Pocket Monsters', 'ポケットモンスター'])
def test_publisher_catalog_finds_alternate_anime_titles(query):
    rows, _ = open_catalog.search({'id': 'pokemon-tv', 'kind': 'pokemon-tv', 'name': 'Pokémon TV'}, query, 1)
    assert rows[0]['title'] == 'Pokémon: Indigo League'
    assert rows[0]['episode_count'] == 3
    assert open_catalog.episodes('pokemon-tv')[1]['url'].endswith('h6LFdBPjbf4')


def test_episode_handoff_requires_an_exact_official_page():
    assert official_episode('https://www.crunchyroll.com/watch/EXAMPLE/episode-one')
    assert not official_episode('https://www.crunchyroll.com/')
    assert not official_episode('https://www.crunchyroll.com.evil.example/watch/EXAMPLE')
    assert not youtube_id('https://www.youtube.com/results?search_query=z3hMX65Khtg')


def test_licensed_files_require_the_actual_license_host():
    assert open_license('http://creativecommons.org/licenses/by/3.0/us/')
    assert not open_license('https://creativecommons.org.example/licenses/by/3.0/')


def test_platform_tls_keeps_peer_validation_enabled():
    context = network.tls_context()
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_untrusted_certificate_is_rejected_over_real_tls(tmp_path):
    openssl = shutil.which('openssl')
    if not openssl:
        pytest.skip('OpenSSL CLI unavailable for generating the local TLS fixture')
    key, cert = tmp_path / 'key.pem', tmp_path / 'cert.pem'
    subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-subj', '/CN=fixture.example', '-keyout', str(key), '-out', str(cert)],
                   check=True, capture_output=True)
    server = HTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = network.PinnedHTTPS('fixture.example', server.server_port, '127.0.0.1', 5)
        with pytest.raises(network.TrustError):
            conn.connect()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
