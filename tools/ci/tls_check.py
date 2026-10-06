#!/usr/bin/env python3
"""The TLS 1.3 client (lib/tls, #124): the RFC 8448 trace, interop with openssl s_server and
Python's ssl module, KeyUpdate, timeouts, truncation, https:// in wire and wss:// in websocket.

Certificates are generated here with the runner's openssl, so no key is checked in. The interop
runs use InsecureSkipVerify; the verified runs trust the generated certificate through RootCAs
(chain, host name and CertificateVerify checked for RSA-PSS, ECDSA and Ed25519 keys), and the
default configuration refuses it as signed by an unknown authority."""
import argparse
import base64
import hashlib
import http.server
import os
import re
import shutil
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from suite import ROOT

SUITES = ['TLS_AES_128_GCM_SHA256', 'TLS_AES_256_GCM_SHA384', 'TLS_CHACHA20_POLY1305_SHA256']
GROUPS = {'X25519': 'X25519', 'P-256': 'P-256'}

RFC8448 = '''handshake ok true X25519
client hello sent as given true
client Finished true
server data after a ticket pong
client data true
server data after KeyUpdate after update
client KeyUpdate true
client data after KeyUpdate true
close_notify true
tampered record tls: record authentication failed
bad_record_mac alert under the client handshake key true
'''


def openssl3():
    """An OpenSSL 3 command line (s_server -tls1_3 with -ciphersuites and -groups), or None."""
    for cand in (shutil.which('openssl'), '/opt/homebrew/opt/openssl@3/bin/openssl', '/usr/local/opt/openssl@3/bin/openssl'):
        if cand and os.path.exists(cand):
            out = subprocess.run([cand, 'version'], capture_output=True, text=True).stdout
            if out.startswith('OpenSSL 3'):
                return cand
    return None


def make_certs(openssl, work):
    """Self-signed certificates for localhost and 127.0.0.1; returns {kind: (cert, key)}."""
    kinds = {'rsa': ['-newkey', 'rsa:2048'], 'ecdsa': ['-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256'],
             'ed25519': ['-newkey', 'ed25519']}
    certs = {}
    for kind, args in kinds.items():
        cert, key = work / f'{kind}.pem', work / f'{kind}.key'
        r = subprocess.run([openssl, 'req', '-x509', *args, '-keyout', str(key), '-out', str(cert), '-days', '30', '-nodes',
                            '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'],
                           capture_output=True)
        if r.returncode == 0:
            certs[kind] = (cert, key)
    assert 'rsa' in certs and 'ecdsa' in certs, 'openssl could not make test certificates'
    # other-root.pem, next to them, is a root that signed none of them, under its own name: the
    # trusted roots of the unknown-authority case. It is not one of the kinds the servers use.
    cert, key = work / 'other-root.pem', work / 'other-root.key'
    r = subprocess.run([openssl, 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256', '-keyout', str(key),
                        '-out', str(cert), '-days', '30', '-nodes', '-subj', '/CN=tin unrelated root'], capture_output=True)
    assert r.returncode == 0, r.stderr
    return certs


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_port(port, proc=None, limit=10):
    end = time.time() + limit
    while time.time() < end:
        if proc is not None and proc.poll() is not None:
            raise AssertionError(f'server exited: {proc.stdout.read() if proc.stdout else ""}')
        try:
            socket.create_connection(('127.0.0.1', port), timeout=0.2).close()
            return
        except OSError:
            time.sleep(0.05)
    raise AssertionError(f'port {port} never opened')


def run(exe, *args, timeout=30, env=None):
    r = subprocess.run([str(exe), *map(str, args)], capture_output=True, text=True, timeout=timeout,
                       env=None if env is None else dict(os.environ, **env))
    assert r.returncode == 0, (args, r.returncode, r.stdout, r.stderr[-3000:])
    return r.stdout


def server_ctx(cert):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(str(cert[0]), str(cert[1]))
    return ctx


def serve_in_thread(target):
    t = threading.Thread(target=target, daemon=True)
    t.start()
    return t


def rfc8448(compiler, work):
    """Build the client with the probe in a private copy of lib/tls and run the trace."""
    root = work / 'probe-root'
    shutil.copytree(ROOT / 'lib', root / 'lib')
    shutil.copy(ROOT / 'tools/ci/fixtures/tls_rfc8448_probe.tin', root / 'lib/tls/probe_rfc8448.tin')
    exe = work / 'rfc8448'
    subprocess.run([str(compiler), '-o', str(exe), 'tools/ci/fixtures/tls_rfc8448.tin'], check=True, cwd=ROOT,
                   env=dict(os.environ, TIN_ROOT=str(root)), timeout=120)
    out = run(exe)
    assert out == RFC8448, out
    print('PASS RFC 8448 trace: Finished both ways, application data, ticket, KeyUpdate, close_notify, bad_record_mac')


def openssl_matrix(exe, openssl, certs):
    """Every cipher suite and group against every certificate type, then ALPN and TLS 1.2."""
    count = 0
    for kind, cert in certs.items():
        for suite in SUITES:
            for group in GROUPS:
                port = free_port()
                proc = subprocess.Popen([openssl, 's_server', '-tls1_3', '-accept', str(port), '-cert', str(cert[0]), '-key', str(cert[1]),
                                         '-www', '-quiet', '-ciphersuites', suite, '-groups', group],
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                try:
                    wait_port(port, proc)
                    out = run(exe, 'get', f'127.0.0.1:{port}')
                finally:
                    proc.kill()
                    proc.wait()
                want = f'ok {suite} {group} alpn= 1 true\n'
                assert out == want, (kind, suite, group, out)
                count += 1
    print(f'PASS openssl s_server: {count} runs (certificates {", ".join(certs)}; every suite; X25519 and P-256 by HelloRetryRequest)')
    port = free_port()
    proc = subprocess.Popen([openssl, 's_server', '-tls1_3', '-accept', str(port), '-cert', str(certs['ecdsa'][0]), '-key', str(certs['ecdsa'][1]),
                             '-www', '-quiet', '-alpn', 'http/1.1'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        wait_port(port, proc)
        out = run(exe, 'get', f'127.0.0.1:{port}', 'http/1.1')
        assert out.startswith('ok ') and ' alpn=http/1.1 ' in out, out
        out = run(exe, 'get', f'127.0.0.1:{port}')
        assert out.startswith('ok ') and ' alpn= ' in out, out
    finally:
        proc.kill()
        proc.wait()
    port = free_port()
    proc = subprocess.Popen([openssl, 's_server', '-tls1_2', '-accept', str(port), '-cert', str(certs['ecdsa'][0]), '-key', str(certs['ecdsa'][1]),
                             '-www', '-quiet'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        wait_port(port, proc)
        out = run(exe, 'get', f'127.0.0.1:{port}')
        assert out.startswith('fault tls: ') and 'protocol version' in out, out
    finally:
        proc.kill()
        proc.wait()
    print('PASS ALPN chosen and absent; a TLS 1.2-only server is refused')


def verified(exe, openssl, certs):
    """Verification on (the default) with the server's certificate in RootCAs: each key type."""
    for kind, cert in certs.items():
        port = free_port()
        proc = subprocess.Popen([openssl, 's_server', '-tls1_3', '-accept', str(port), '-cert', str(cert[0]), '-key', str(cert[1]),
                                 '-www', '-quiet', '-ciphersuites', 'TLS_AES_128_GCM_SHA256'],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            wait_port(port, proc)
            out = run(exe, 'resume', f'127.0.0.1:{port}', 1, cert[0])
        finally:
            proc.kill()
            proc.wait()
        assert out == 'resumed false TLS_AES_128_GCM_SHA256 X25519 1 true\n', (kind, out)
    print(f'PASS verification against RootCAs: certificates {", ".join(certs)} (chain, name, CertificateVerify)')


def resumption(exe, openssl, certs, work):
    """Session tickets (#348): the second and later connections of one client process resume."""
    # openssl s_server: every suite, X25519 and P-256 (a HelloRetryRequest with the PSK offered again).
    count = 0
    for suite in SUITES:
        for group in GROUPS:
            port = free_port()
            cert = certs['ecdsa']
            proc = subprocess.Popen([openssl, 's_server', '-tls1_3', '-accept', str(port), '-cert', str(cert[0]), '-key', str(cert[1]),
                                     '-www', '-quiet', '-ciphersuites', suite, '-groups', group],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                wait_port(port, proc)
                out = run(exe, 'resume', f'127.0.0.1:{port}', 4).splitlines()
            finally:
                proc.kill()
                proc.wait()
            want = [f'resumed {flag} {suite} {group} {certs_seen} true' for flag, certs_seen in
                    (('false', 1), ('true', 0), ('true', 0), ('true', 0))]
            assert out == want, (suite, group, out)
            count += 1
    print(f'PASS resumption: {count} openssl s_server runs (every suite; X25519 and P-256 by HelloRetryRequest): the first connection is full, the next three resume')
    # A server that forgets its ticket keys after three connections (a restart): the client's old
    # ticket is not understood, and it falls back to a full handshake and carries on.
    contexts = [server_ctx(certs['ecdsa']), server_ctx(certs['ecdsa'])]
    reused = []
    stop = threading.Event()
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', 0))
    srv.listen(8)
    srv.settimeout(.2)
    port = srv.getsockname()[1]

    def serve():
        while not stop.is_set():
            try:
                raw, _ = srv.accept()
            except socket.timeout:
                continue
            try:
                conn = contexts[0 if len(reused) < 3 else 1].wrap_socket(raw, server_side=True)
                reused.append(conn.session_reused)
                conn.recv(100)
                conn.sendall(b'HTTP/1.0 200 OK\r\n\r\nok')
                conn.unwrap().close()  # close_notify, then TCP
            except (OSError, ssl.SSLError):
                pass
    thread = serve_in_thread(serve)
    try:
        out = run(exe, 'resume', f'127.0.0.1:{port}', 6).splitlines()
        assert [l.split()[1] for l in out] == ['false', 'true', 'true', 'false', 'true', 'true'], out
        assert reused == [False, True, True, False, True, True], reused
    finally:
        stop.set()
        thread.join(timeout=2)
        srv.close()
    print('PASS resumption: a server that lost its ticket keys gets a full handshake, then resumption again')


def client_certificate(exe, openssl, certs, work):
    """Mutual TLS from the client (#475): openssl s_server requiring a certificate from the test
    PKI's CA accepts the Tin client's (ECDSA and RSA keys) and refuses a client without one."""
    pki = work / 'pki'
    pki.mkdir(exist_ok=True)
    subprocess.run(['go', 'run', str(ROOT / 'tools/ci/fixtures/mtlspki.go'), str(pki)], cwd=ROOT, check=True, timeout=300)
    cert = certs['ecdsa']
    port = free_port()
    proc = subprocess.Popen([openssl, 's_server', '-tls1_3', '-accept', str(port), '-cert', str(cert[0]), '-key', str(cert[1]),
                             '-www', '-quiet', '-Verify', '1', '-CAfile', str(pki / 'ca.pem'), '-verify_return_error'],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        wait_port(port, proc)
        for name in ('alice', 'rsa'):
            out = run(exe, 'mtls', f'127.0.0.1:{port}', 1, cert[0], pki / f'{name}.pem', pki / f'{name}.key')
            assert out.startswith('mtls false <HTML>') and 'TLSv1.3' in out, (name, out[:500])
        out = run(exe, 'mtls', f'127.0.0.1:{port}', 1, cert[0])
        assert out.startswith('fault tls: remote error: certificate required'), out
    finally:
        proc.kill()
        proc.wait()
    print('PASS client certificates: openssl s_server -Verify accepts the Tin client\'s ECDSA and RSA certificates and '
          'refuses a client without one')


KEYLOG_LABELS = ('CLIENT_HANDSHAKE_TRAFFIC_SECRET', 'SERVER_HANDSHAKE_TRAFFIC_SECRET', 'CLIENT_TRAFFIC_SECRET_0',
                 'SERVER_TRAFFIC_SECRET_0')


def keylog_lines(path):
    """The TLS 1.3 traffic-secret lines of an NSS key log, sorted (OpenSSL also writes EXPORTER_SECRET)."""
    return sorted(l for l in path.read_text().splitlines() if l.split(' ', 1)[0] in KEYLOG_LABELS)


def keylog(exe, openssl, certs, work):
    """SSLKEYLOGFILE (#478): the client logs the same four secrets openssl s_server logs."""
    cert = certs['ecdsa']
    mine, theirs = work / 'keylog-client.txt', work / 'keylog-s_server.txt'
    port = free_port()
    proc = subprocess.Popen([openssl, 's_server', '-tls1_3', '-accept', str(port), '-cert', str(cert[0]), '-key', str(cert[1]),
                             '-www', '-quiet', '-keylogfile', str(theirs)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        wait_port(port, proc)
        out = run(exe, 'resume', f'127.0.0.1:{port}', 1, cert[0], env={'SSLKEYLOGFILE': str(mine)})
        assert out.startswith('resumed false'), out
    finally:
        proc.kill()
        proc.wait()
    a, b = keylog_lines(mine), keylog_lines(theirs)
    assert len(a) == 4 and a == b, (a, b)
    print('PASS SSLKEYLOGFILE: the client logs the four TLS 1.3 traffic secrets openssl s_server logs for the connection')


def keyupdate(exe, openssl, certs):
    """An interactive s_server sends KeyUpdate with and without request_update; the client
    reads on, answers and keeps writing on its next key."""
    port = free_port()
    proc = subprocess.Popen([openssl, 's_server', '-tls1_3', '-accept', str(port), '-cert', str(certs['ecdsa'][0]), '-key', str(certs['ecdsa'][1]),
                             '-ign_eof'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    seen = []
    lock = threading.Lock()

    def reader():
        for line in proc.stdout:
            with lock:
                seen.append(line.decode(errors='replace'))

    serve_in_thread(reader)
    try:
        wait_port(port, proc)
        client = subprocess.Popen([str(exe), 'keyupdate', f'127.0.0.1:{port}'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        def wait_for(text):
            end = time.time() + 10
            while time.time() < end:
                with lock:
                    if any(text in line for line in seen):
                        return
                time.sleep(0.05)
            raise AssertionError(f'never saw {text!r}: {seen[-10:]}')

        def say(line):
            proc.stdin.write(line.encode())
            proc.stdin.flush()
            time.sleep(0.3)

        wait_for('ping')
        say('K\n')
        say('one\n')
        wait_for('after one')
        say('k\n')
        say('two\n')
        wait_for('after two')
        say('bye\n')
        out, err = client.communicate(timeout=20)
        assert client.returncode == 0, err
        assert out == 'got one\ngot two\ngot bye\n', out
        with lock:
            text = ''.join(seen)
        # s_server reports each KeyUpdate it sends (KEYUPDATE, or SSL_do_handshake -> 1 in 3.0).
        after = text[text.index('ping'):]
        assert after.count('KEYUPDATE') + after.count('SSL_do_handshake -> 1') >= 2, text[-2000:]
    finally:
        proc.kill()
        proc.wait()
    print('PASS KeyUpdate from the server, with and without request_update')


def python_servers(exe, certs):
    """Timeouts, truncation, a non-TLS server, https:// and wss:// against Python's ssl."""
    # A server that accepts and never answers: the handshake times out after Config.Timeout.
    quiet = socket.socket()
    quiet.bind(('127.0.0.1', 0))
    quiet.listen(4)
    port = quiet.getsockname()[1]
    out = run(exe, 'timeout', f'127.0.0.1:{port}', 300)
    m = re.match(r'fault tls: read timed out (\d+)\n', out)
    assert m and 250 <= int(m.group(1)) < 5000, out
    quiet.close()
    # A server that speaks HTTP instead of TLS.
    plain = socket.socket()
    plain.bind(('127.0.0.1', 0))
    plain.listen(4)

    def http_instead():
        c, _ = plain.accept()
        c.recv(4096)
        c.sendall(b'HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n')
        time.sleep(0.5)
        c.close()

    serve_in_thread(http_instead)
    out = run(exe, 'get', f'127.0.0.1:{plain.getsockname()[1]}')
    assert out.startswith('fault tls: unexpected record type 72'), out
    plain.close()
    # A server that closes TCP without close_notify: the read fails instead of a clean EOF.
    ctx = server_ctx(certs['ecdsa'])
    # The servers below speak ALPN, to see what wire and websocket offer (#478).
    ctx.set_alpn_protocols(['http/1.1'])
    alpn_seen = []
    trunc = socket.socket()
    trunc.bind(('127.0.0.1', 0))
    trunc.listen(4)

    def truncating():
        c, _ = trunc.accept()
        s = ctx.wrap_socket(c, server_side=True)
        s.sendall(b'partial data')
        time.sleep(0.2)
        # Drop the socket under the TLS layer, so no close_notify is sent.
        os.close(s.detach())

    serve_in_thread(truncating)
    out = run(exe, 'truncated', f'127.0.0.1:{trunc.getsockname()[1]}')
    assert out == 'fault tls: connection closed by the peer without close_notify 12\n', out
    trunc.close()
    # Verification is the default: a server whose certificate no trusted root signed is refused.
    port = free_port()

    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_GET(self):
            alpn_seen.append(self.connection.selected_alpn_protocol())
            body = b'hello over tls ' * 4096
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            data = self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(200)
            self.send_header('Transfer-Encoding', 'chunked')
            self.end_headers()
            self.wfile.write(b'%x\r\n%s\r\n0\r\n\r\n' % (len(data), data))

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', port), H)
    srv.handle_error = lambda request, address: None  # the refused handshake of the verify run
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True, do_handshake_on_connect=False)
    serve_in_thread(srv.serve_forever)
    try:
        wait_port(port)
        # The trusted roots are an unrelated certificate (SSL_CERT_FILE), so the outcome does not
        # depend on whether this machine has a CA bundle.
        out = run(exe, 'verify', f'127.0.0.1:{port}', 'localhost', env={'SSL_CERT_FILE': str(certs['rsa'][0].with_name('other-root.pem'))})
        assert out.startswith('fault tls: x509: certificate signed by unknown authority'), out
        want = hashlib.sha256(b'hello over tls ' * 4096).hexdigest()
        out = run(exe, 'https', f'https://127.0.0.1:{port}/x')
        assert out == f'get 200 {15 * 4096} {want}\npost 200 posted over tls\n', out
        assert alpn_seen == ['http/1.1'], ('wire offers ALPN http/1.1', alpn_seen)
    finally:
        srv.shutdown()
    # wss:// with a small WebSocket echo server over TLS.
    ws = socket.socket()
    ws.bind(('127.0.0.1', 0))
    ws.listen(4)

    def recv_exact(s, n):
        b = b''
        while len(b) < n:
            chunk = s.recv(n - len(b))
            if not chunk:
                raise EOFError
            b += chunk
        return b

    def wss_echo():
        c, _ = ws.accept()
        s = ctx.wrap_socket(c, server_side=True)
        alpn_seen.append(s.selected_alpn_protocol())
        head = b''
        while b'\r\n\r\n' not in head:
            head += s.recv(1)
        key = [ln.split(b':', 1)[1].strip() for ln in head.split(b'\r\n') if ln.lower().startswith(b'sec-websocket-key')][0]
        accept = base64.b64encode(hashlib.sha1(key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
        s.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + b'\r\n\r\n')
        while True:
            b0, b1 = recv_exact(s, 2)
            n = b1 & 127
            if n == 126:
                n = struct.unpack('>H', recv_exact(s, 2))[0]
            mask = recv_exact(s, 4)
            data = bytes(x ^ mask[i % 4] for i, x in enumerate(recv_exact(s, n)))
            if b0 & 15 == 8:
                s.sendall(bytes([0x88, len(data)]) + data)
                s.close()
                return
            out = b'echo: ' + data
            s.sendall(bytes([0x80 | (b0 & 15), len(out)]) + out)

    serve_in_thread(wss_echo)
    out = run(exe, 'wss', f'wss://127.0.0.1:{ws.getsockname()[1]}/chat')
    assert out == 'wss true echo: hello wss\n', out
    assert alpn_seen == ['http/1.1', 'http/1.1'], ('websocket offers ALPN http/1.1', alpn_seen)
    ws.close()
    print('PASS handshake timeout, a non-TLS server, truncation without close_notify, verification by default, https:// and wss:// '
          '(both offering ALPN http/1.1)')


def http_get(port, path, timeout=10):
    s = socket.create_connection(('127.0.0.1', port), timeout=timeout)
    t0 = time.time()
    s.sendall(('GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n' % path).encode())
    data = b''
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        data += chunk
    s.close()
    return time.time() - t0, data


def request_tasks(compiler, work, certs):
    """On one core, eight requests that each make a TLS handshake taking 0.5 s overlap, a
    fast request answers meanwhile, and a request deadline ends a handshake that never
    finishes."""
    exe = work / 'tls_server'
    subprocess.run([str(compiler), '-o', str(exe), 'tools/ci/fixtures/tls_server.tin'], check=True, cwd=ROOT,
                   env=dict(os.environ, TIN_ROOT=str(ROOT)), timeout=120)
    ctx = server_ctx(certs['ecdsa'])
    slow = socket.socket()
    slow.bind(('127.0.0.1', 0))
    slow.listen(64)

    def slow_handshake(c):
        time.sleep(0.5)
        try:
            s = ctx.wrap_socket(c, server_side=True)
            s.recv(4096)
            s.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\nslow')
            s.close()
        except (OSError, ssl.SSLError):
            c.close()

    def slow_server():
        while True:
            try:
                c, _ = slow.accept()
            except OSError:
                return
            serve_in_thread(lambda c=c: slow_handshake(c))

    serve_in_thread(slow_server)
    hole = socket.socket()
    hole.bind(('127.0.0.1', 0))
    hole.listen(64)
    port = free_port()
    server = subprocess.Popen([str(exe)], env=dict(os.environ, PORT=str(port), TIN_CORES='1', TIN_DEADLINE_MS='1500'))
    try:
        wait_port(port, server)
        results = {}

        def one(i):
            results[i] = http_get(port, f'/fetch?port={slow.getsockname()[1]}')

        threads = [threading.Thread(target=one, args=(i,)) for i in range(8)]
        t0 = time.time()
        for t in threads:
            t.start()
        time.sleep(0.1)
        fast = [http_get(port, '/fast')[0] for _ in range(5)]
        for t in threads:
            t.join()
        total = time.time() - t0
        bodies = [d.split(b'\r\n\r\n', 1)[-1] for _, d in results.values()]
        assert bodies == [b'via tls: slow'] * 8, bodies
        assert total < 2.5, f'8 handshakes of 0.5 s took {total:.2f} s on one core: they did not overlap'
        assert max(fast) < 0.4, f'a fast request waited {max(fast):.2f} s behind TLS handshakes'
        took, data = http_get(port, f'/fetch?port={hole.getsockname()[1]}')
        assert b'upstream: deadline exceeded' in data and 1.0 < took < 4.0, (took, data[-200:])
    finally:
        server.kill()
        server.wait()
        slow.close()
        hole.close()
    print(f'PASS request tasks: 8 slow handshakes overlap on one core ({total:.2f} s), /fast stays fast, the deadline ends a stuck handshake')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default='bin/tinc')
    args = parser.parse_args()
    compiler = (ROOT / args.compiler).resolve()
    out = ROOT / 'bin/ci/tls'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tls-', dir=out) as tmp:
        work = Path(tmp)
        exe = work / 'tls_client'
        subprocess.run([str(compiler), '-o', str(exe), 'tools/ci/fixtures/tls_client.tin'], check=True, cwd=ROOT,
                       env=dict(os.environ, TIN_ROOT=str(ROOT)), timeout=120)
        subprocess.run([str(compiler), '-o', str(work / 'https_client'), 'examples/https_client.tin'], check=True, cwd=ROOT,
                       env=dict(os.environ, TIN_ROOT=str(ROOT)), timeout=120)
        rfc8448(compiler, work)
        openssl = openssl3()
        any_openssl = openssl or shutil.which('openssl')
        assert any_openssl, 'tls_check needs an openssl command to make test certificates'
        certs = make_certs(any_openssl, work)
        python_servers(exe, certs)
        request_tasks(compiler, work, certs)
        if openssl:
            openssl_matrix(exe, openssl, certs)
            verified(exe, openssl, certs)
            resumption(exe, openssl, certs, work)
            keylog(exe, openssl, certs, work)
            client_certificate(exe, openssl, certs, work)
            keyupdate(exe, openssl, certs)
        else:
            print('SKIP openssl s_server interop: no OpenSSL 3 command line on this runner')
    print('tls: all checks passed')


if __name__ == '__main__':
    main()
