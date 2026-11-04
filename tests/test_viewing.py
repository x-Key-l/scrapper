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


def test_public_html_search_episodes_and_playback_metadata_over_http():
    """Use an actual HTTP origin and route only its test hostname to loopback."""
    from urllib.parse import parse_qs, urlsplit
    from scenetrace import websites

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path)
            pages = {
                '/': '<title>Anime fixture</title><form action="/search"><input name="q"></form>',
                '/series/pocket': '<div class="episodes"><a href="/episode/1">Episode 1</a><a href="/episode/2">Episode 2</a></div>',
                '/episode/1': '<title>Episode 1</title><video src="/media/one.mp4"><track src="/subs.vtt" srclang="en"></video><a download href="/media/one.mp4">Download</a>',
            }
            if path.path == '/search':
                query = parse_qs(path.query)
                assert query['q'] == ['Pocket Monsters'] and query['page'] == ['2']
                body = '<article class="show"><a href="/series/pocket"><span>Pocket Monsters</span></a><img src="/cover.jpg"></article>'
            else:
                body = pages[path.path]
            data = body.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original = network.target

    def target(value):
        if urlsplit(value).hostname == 'fixture.example':
            return urlsplit(value), 'fixture.example', server.server_port, '127.0.0.1'
        return original(value)

    try:
        with patch('scenetrace.network.target', side_effect=target):
            detected = websites.inspect('http://fixture.example/')
            assert detected['query_param'] == 'q'
            cfg = websites.validate(dict(detected, page_param='page', result_selector='.show',
                                         link_selector='a', title_selector='span', episode_selector='.episodes a'))
            source = {'id': 'fixture', 'name': 'Anime fixture', 'endpoint': 'http://fixture.example/', 'web_config': cfg,
                      'categories': ['anime']}
            rows, more = websites.search(source, 'Pocket Monsters', 2)
            assert more and rows[0]['title'] == 'Pocket Monsters'
            assert rows[0]['thumbnail'] == 'http://fixture.example/cover.jpg'
            listing = websites.episodes(source, rows[0]['url'])
            assert [row['number'] for row in listing] == ['1', '2']
            player = websites.resolve(source, listing[0]['url'])
            assert player['formats'][0]['url'] == 'http://fixture.example/media/one.mp4'
            assert player['download_allowed'] and player['subtitles'][0]['language'] == 'en'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_website_url_pattern_cannot_redirect_search_to_other_origin():
    from scenetrace import websites
    cfg = websites.validate({'strategy': 'html', 'search_pattern': 'https://unrelated.example/?q={query}'})
    with pytest.raises(ValueError, match='configured website origin'):
        websites.search_url({'endpoint': 'https://fixture.example', 'web_config': cfg}, 'test', 1)


def test_xml_video_sitemap_and_nonvideo_entries():
    from scenetrace import websites
    xml = b'<urlset xmlns:v="urn:video"><url><loc>https://site.example/about</loc></url><url><loc>https://site.example/episode/1</loc><v:video><v:title>Episode one</v:title></v:video></url></urlset>'
    assert list(websites.sitemap_rows(xml, 'https://site.example', ''))[0]['title'] == 'Episode one'
    with pytest.raises(ValueError, match='entities'):
        list(websites.sitemap_rows(b'<!DOCTYPE a [<!ENTITY e "test">]><urlset/>', 'https://site.example', ''))


def test_source_discovery_keeps_metadata_out_of_video_suggestions():
    from scenetrace.discovery import find
    result = find('searchable anime episode catalogs', video_only=True)
    assert result['providers']
    assert all(source['role'] != 'metadata' and source['tested'] is False for source in result['providers'])


def test_video_gallery_upgrade_preserves_existing_profile(tmp_path):
    from scenetrace.store import Store
    from scenetrace.sources import defaults
    store = Store(tmp_path / 'profile')
    store.set_setting('gallery_initialized', True)
    store.set_setting('destination', 'existing-folder')
    store.save({'id': 'saved:previous-release', 'title': 'Existing title'})
    store.history('existing search', 'memory')
    defaults(store)
    assert store.setting('destination') == 'existing-folder'
    assert store.saved()[0]['id'] == 'saved:previous-release'
    assert store.history()[0]['query'] == 'existing search'
    assert {source['id'] for source in store.sources()} == {'open-animation', 'pokemon-tv'}
