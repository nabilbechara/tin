#!/usr/bin/env python3
"""The TLS 1.3 server (anvil.ServeTLS, #124 phase 5) against real clients.

- openssl s_client -tls1_3 against ECDSA P-256, ECDSA P-384 and RSA-2048 certificates generated
  per run: every cipher suite with X25519, P-256, and P-256 by HelloRetryRequest (the client's
  first share is P-384); OpenSSL verifies the chain and the CertificateVerify (ECDSA, RSA-PSS
  with SHA-256, -384 and -512); ALPN; a client KeyUpdate with and without update_requested; the
  refusals (an ECDSA-only client against an RSA key, no common ALPN protocol, TLS 1.2 only).
- Python's ssl: https requests on one keep-alive connection (plain, chunked, streamed and
  SendFile bodies, a 1 MiB and a chunked upload), pipelining with close_notify at the end, ALPN,
  a TLS 1.2-only client refused, a ClientHello split over many records.
- The Tin client: tls.Dial with and without ALPN, verification through RootCAs (and the
  default's refusal), wire https:// GET and POST, websocket wss:// through websocket.Accept.
- Malformed handshakes get their alerts (unexpected_message, record_overflow, decode_error),
  and a client that never sends or stops halfway is closed at the handshake timeout.
- One core: hundreds of stalled handshakes, a burst of full ones and a waiting request do
  not hold up a fast request.
- Memory: 256 MiB streamed over TLS leaves RSS flat; the cost of idle TLS connections.
- Graceful shutdown: SIGTERM lets a waiting request answer, closes with close_notify, and the
  server exits 0.
- examples/https_server.tin, and a key that does not match its certificate.

The Python parts need an ssl module with TLS 1.3 (OpenSSL 1.1.1 or later): they are skipped
on a Mac whose Python links LibreSSL, and required on Linux. openssl s_client must be OpenSSL 3."""
import argparse
import base64
import hashlib
import os
import re
import signal
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from suite import ROOT
from tls_check import free_port, openssl3, wait_port

SUITES = {'TLS_AES_128_GCM_SHA256': '1301', 'TLS_AES_256_GCM_SHA384': '1302', 'TLS_CHACHA20_POLY1305_SHA256': '1303'}
# groups offered by the client -> the group the server must use (P-384 first forces a HelloRetryRequest)
GROUPS = {'X25519': 'X25519', 'P-256': 'P-256', 'P-384:P-256': 'P-256'}
SIGTYPE = {'ecdsa': ('ecdsa_secp256r1_sha256', 'ECDSA'), 'ecdsa384': ('ecdsa_secp384r1_sha384', 'ECDSA'),
           'rsa': ('rsa_pss_rsae_sha256', 'RSA-PSS')}

PY_TLS13 = getattr(ssl, 'HAS_TLSv1_3', False) and not ssl.OPENSSL_VERSION.startswith('LibreSSL')


def pattern(n, start=0):
    return bytes((start + i) % 251 for i in range(n))


def build(compiler, src, exe):
    subprocess.run([str(compiler), '-o', str(exe), src], check=True, cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), timeout=180)


def make_certs(openssl, work):
    """Self-signed certificates for localhost and 127.0.0.1: {kind: (cert, key)}."""
    kinds = {'ecdsa': ['-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256'],
             'ecdsa384': ['-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-384'],
             'rsa': ['-newkey', 'rsa:2048'],
             'ed25519': ['-newkey', 'ed25519']}
    certs = {}
    for kind, args in kinds.items():
        cert, key = work / f'{kind}.pem', work / f'{kind}.key'
        r = subprocess.run([openssl, 'req', '-x509', *args, '-keyout', str(key), '-out', str(cert), '-days', '30', '-nodes',
                            '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], capture_output=True)
        assert r.returncode == 0, (kind, r.stderr)
        certs[kind] = (cert, key)
    # A root that has nothing to do with the server, for the default verification's refusal.
    cert, key = work / 'unrelated.pem', work / 'unrelated.key'
    r = subprocess.run([openssl, 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256', '-keyout', str(key),
                        '-out', str(cert), '-days', '30', '-nodes', '-subj', '/CN=Unrelated Test Root'], capture_output=True)
    assert r.returncode == 0, r.stderr
    certs['unrelated'] = (cert, key)
    return certs


class Server:
    """The https_server fixture (or another ServeTLS program) on a free port."""

    def __init__(self, exe, cert, work, env=None, cores=1, wait=True):
        self.port = free_port()
        e = dict(os.environ, PORT=str(self.port), TIN_CORES=str(cores), TLS_CERT=str(cert[0]), TLS_KEY=str(cert[1]),
                 FILE=str(work / 'file.bin'))
        e.update(env or {})
        self.logpath = work / f'server-{self.port}.log'
        self.log = open(self.logpath, 'w')
        self.p = subprocess.Popen([str(exe)], env=e, stdout=self.log, stderr=subprocess.STDOUT)
        if wait:
            wait_port(self.port, self.p)

    def addr(self):
        return f'127.0.0.1:{self.port}'

    def rss_kb(self):
        r = subprocess.run(['ps', '-o', 'rss=', '-p', str(self.p.pid)], capture_output=True, text=True)
        return int(r.stdout.strip() or 0)

    def output(self):
        self.log.flush()
        return self.logpath.read_text(errors='replace')

    def stop(self):
        if self.p.poll() is None:
            self.p.kill()
        self.p.wait()
        self.log.close()


def s_client(openssl, port, args, request, cafile=None, timeout=30):
    """One s_client run that sends request and reads until the server closes: (exit code, output)."""
    cmd = [openssl, 's_client', '-tls1_3', '-connect', f'127.0.0.1:{port}', '-servername', 'localhost', '-ign_eof', *args]
    if cafile:
        cmd += ['-CAfile', str(cafile), '-verify_hostname', 'localhost', '-verify_return_error']
    r = subprocess.run(cmd, input=request, capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode('latin1') + r.stderr.decode('latin1')


def get(path, close=True):
    conn = 'Connection: close\r\n' if close else ''
    return f'GET {path} HTTP/1.1\r\nHost: localhost\r\n{conn}\r\n'.encode()


def openssl_interop(openssl, exe, certs, work):
    """Every suite and group against each certificate, verified by OpenSSL; signature schemes; refusals."""
    runs = 0
    for kind in ('ecdsa', 'ecdsa384', 'rsa'):
        cert = certs[kind]
        srv = Server(exe, cert, work)
        try:
            for suite, code in SUITES.items():
                for offer, group in GROUPS.items():
                    rc, out = s_client(openssl, srv.port, ['-ciphersuites', suite, '-groups', offer, '-alpn', 'http/1.1'],
                                       get('/info'), cafile=cert[0])
                    want = f'alpn=http/1.1 suite={code} group={group}'
                    assert want in out, (kind, suite, offer, out[-2000:])
                    assert 'Verify return code: 0 (ok)' in out, (kind, suite, offer, out[-2000:])
                    assert any(t in out for t in SIGTYPE[kind]), (kind, out[-2000:])
                    runs += 1
            if kind == 'rsa':
                for sa in ('rsa_pss_rsae_sha256', 'rsa_pss_rsae_sha384', 'rsa_pss_rsae_sha512'):
                    rc, out = s_client(openssl, srv.port, ['-sigalgs', sa], get('/fast'), cafile=cert[0])
                    assert '\r\n\r\nfast' in out and 'Verify return code: 0 (ok)' in out, (sa, out[-2000:])
                rc, out = s_client(openssl, srv.port, ['-sigalgs', 'ecdsa_secp256r1_sha256'], get('/fast'))
                assert rc != 0 and 'alert number 40' in out, ('ECDSA-only client against an RSA key', out[-1500:])
            if kind == 'ecdsa':
                rc, out = s_client(openssl, srv.port, ['-sigalgs', 'rsa_pss_rsae_sha256'], get('/fast'))
                assert rc != 0 and 'alert number 40' in out, ('RSA-only client against an ECDSA key', out[-1500:])
                rc, out = s_client(openssl, srv.port, ['-alpn', 'spdy/3'], get('/fast'))
                assert rc != 0 and 'alert number 120' in out, ('no common ALPN protocol', out[-1500:])
                rc, out = s_client(openssl, srv.port, [], get('/info'))
                assert 'alpn= suite=' in out, ('no ALPN offered', out[-1500:])
                r = subprocess.run([openssl, 's_client', '-tls1_2', '-connect', srv.addr()], input=b'', capture_output=True, timeout=30)
                out = (r.stdout + r.stderr).decode('latin1')
                assert r.returncode != 0 and 'alert number 70' in out, ('TLS 1.2 only', out[-1500:])
                keyupdate(openssl, srv)
                watch_closed(openssl, srv)
        finally:
            srv.stop()
    print(f'PASS openssl s_client: {runs} handshakes (ECDSA P-256, ECDSA P-384 and RSA certificates verified by OpenSSL; '
          'every suite; X25519, P-256 and P-256 by HelloRetryRequest), RSA-PSS SHA-256/384/512, '
          'handshake_failure, no_application_protocol and protocol_version refusals, client KeyUpdate, '
          'a stream sees the client\'s close_notify (Out.Closed)')


def keyupdate(openssl, srv):
    """The client's KeyUpdate: with update_requested (K) the server answers with its own."""
    p = subprocess.Popen([openssl, 's_client', '-tls1_3', '-connect', srv.addr()], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for chunk in (b'K\n', get('/fast', close=False), b'k\n', get('/info')):
            p.stdin.write(chunk)
            p.stdin.flush()
            time.sleep(0.4)
        out, _ = p.communicate(timeout=20)
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
    out = out.decode('latin1')
    assert out.count('KEYUPDATE') == 2 and '\r\n\r\nfast' in out and 'alpn= suite=' in out, out[-2000:]


def watch_closed(openssl, srv):
    """A stream's handler polling w.Closed() sees the client's close_notify (a socket peek would
    see only a record), then its FIN."""
    # Not -quiet: it implies -ign_eof, and here the end of input is what makes s_client close.
    p = subprocess.Popen([openssl, 's_client', '-tls1_3', '-connect', srv.addr()], stdin=subprocess.PIPE,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    p.stdin.write(get('/watch', close=False))
    p.stdin.flush()
    time.sleep(0.5)
    p.stdin.close()  # s_client sends close_notify and exits
    p.wait(timeout=10)
    deadline = time.time() + 5
    while 'watch saw closed' not in srv.output() and time.time() < deadline:
        time.sleep(0.05)
    assert 'watch saw closed' in srv.output(), srv.output()[-1000:]


# ---- Python's ssl ----

def py_ctx(cert, alpn=None, max12=False):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(str(cert[0]))
    if max12:
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    else:
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    if alpn:
        ctx.set_alpn_protocols(alpn)
    return ctx


def py_connect(srv, ctx, timeout=20):
    raw = socket.create_connection(('127.0.0.1', srv.port), timeout=timeout)
    return ctx.wrap_socket(raw, server_hostname='127.0.0.1', suppress_ragged_eofs=False)


def read_to_close(s):
    """Everything until the server's close_notify (a TCP close without it raises SSLEOFError)."""
    data = b''
    while True:
        chunk = s.recv(1 << 16)
        if not chunk:
            return data
        data += chunk


def python_clients(exe, certs, work):
    import http.client
    cert = certs['ecdsa']
    srv = Server(exe, cert, work)
    try:
        # http.client speaks HTTP/1.1: of what it offers, the server has only http/1.1 (h2 is
        # checked by tools/ci/h2_check.py).
        ctx = py_ctx(cert, alpn=['spdy/3', 'http/1.1'])
        c = http.client.HTTPSConnection('127.0.0.1', srv.port, context=ctx, timeout=30)
        upload = os.urandom(1 << 20)
        fbytes = (work / 'file.bin').read_bytes()
        checks = [
            ('GET', '/', None, b'hello over tls'),
            ('GET', '/info', None, b'alpn=http/1.1 suite='),
            ('POST', '/echo', upload, upload),
            ('POST', '/echo', iter([b'chunked ', b'upload ', b'body']), b'chunked upload body'),
            ('GET', '/big?n=3000000', None, pattern(3000000)),
            ('GET', '/stream?n=40&size=70000', None, pattern(40 * 70000)),
            ('GET', '/file', None, fbytes),
            ('GET', '/file?n=1000', None, fbytes[:1000]),
        ]
        for method, path, body, want in checks:
            headers = {'Transfer-Encoding': 'chunked'} if isinstance(body, type(iter([]))) else {}
            c.request(method, path, body=body, headers=headers, encode_chunked=bool(headers))
            r = c.getresponse()
            got = r.read()
            assert r.status == 200, (path, r.status, got[:200])
            if path == '/info':
                assert got.startswith(want), got
            else:
                assert got == want, (method, path, len(got), len(want))
        for _ in range(20):
            c.request('GET', '/fast')
            assert c.getresponse().read() == b'fast'
        assert c.sock.selected_alpn_protocol() == 'http/1.1'
        assert c.sock.version() == 'TLSv1.3'
        c.close()
        # Pipelined requests in one write, answered in order; the close is a close_notify.
        s = py_connect(srv, py_ctx(cert))
        s.sendall(get('/fast', False) + get('/', False) + get('/info'))
        data = read_to_close(s)
        s.close()
        bodies = [part.split(b'\r\n\r\n', 1)[1][:14] for part in data.split(b'HTTP/1.1 200 OK')[1:]]
        assert bodies == [b'fast', b'hello over tls', b'alpn= suite=13'], data[-500:]
        # ALPN with nothing in common, and a client without TLS 1.3: the fatal alert the client
        # read, no_application_protocol (120) and protocol_version (70). It is taken from the
        # records, because Python's name for an alert depends on the OpenSSL it was built with
        # (Ubuntu 24.04's has none for 120).
        for ctx2, want in ((py_ctx(cert, alpn=['spdy/3']), 120), (py_ctx(cert, max12=True), 70)):
            alerts = []

            def seen(conn, direction, version, ctype, mtype, data, alerts=alerts):
                if direction == 'read' and ctype == ssl._TLSContentType.ALERT:
                    alerts.append(bytes(data[:2]))

            ctx2._msg_callback = seen
            try:
                py_connect(srv, ctx2).close()
                raise AssertionError(f'handshake succeeded, wanted alert {want}')
            except ssl.SSLError as e:
                assert alerts == [bytes([2, want])], (want, alerts, e)
        fragmented_hello(srv, cert)
    finally:
        srv.stop()
    print('PASS Python ssl: GET, POST (1 MiB and chunked), 3 MB body, streamed and SendFile bodies on one keep-alive connection; '
          'pipelining ended by close_notify; ALPN; no common protocol and a TLS 1.2 client refused; a ClientHello in 40-byte records')


def fragmented_hello(srv, cert):
    """The ClientHello split over many records (the server reassembles handshake messages)."""
    inc, out = ssl.MemoryBIO(), ssl.MemoryBIO()
    obj = py_ctx(cert).wrap_bio(inc, out, server_hostname='127.0.0.1')
    try:
        obj.do_handshake()
    except ssl.SSLWantReadError:
        pass
    hello = out.read()
    assert hello[0] == 22, hello[:5]
    body = hello[5:]
    sock = socket.create_connection(('127.0.0.1', srv.port), timeout=10)
    sock.sendall(b''.join(b'\x16\x03\x01' + struct.pack('>H', len(body[i:i + 40])) + body[i:i + 40] for i in range(0, len(body), 40)))
    done = False
    while not done:
        data = sock.recv(65536)
        assert data, 'the server closed during the handshake'
        inc.write(data)
        try:
            obj.do_handshake()
            done = True
        except ssl.SSLWantReadError:
            pass
        sock.sendall(out.read())
    obj.write(get('/fast'))
    sock.sendall(out.read())
    got = b''
    while b'fast' not in got:
        data = sock.recv(65536)
        assert data, got
        inc.write(data)
        try:
            got += obj.read(65536)
        except ssl.SSLWantReadError:
            pass
    sock.close()


# ---- the Tin client ----

def tin_clients(exe, client, certs, work):
    cert = certs['ecdsa']
    srv = Server(exe, cert, work)
    try:
        def run(*args, env=None):
            r = subprocess.run([str(client), *map(str, args)], capture_output=True, text=True, timeout=60,
                               env=dict(os.environ, **(env or {})))
            assert r.returncode == 0, (args, r.stdout, r.stderr[-2000:])
            return r.stdout
        out = run('get', srv.addr())
        assert re.fullmatch(r'ok TLS_\w+ X25519 alpn= 1 true\n', out), out
        out = run('get', srv.addr(), 'http/1.1')
        assert re.fullmatch(r'ok TLS_\w+ X25519 alpn=http/1.1 1 true\n', out), out
        out = run('resume', srv.addr(), 2, cert[0])
        assert re.fullmatch(r'resumed false TLS_\w+ X25519 1 true\nresumed true TLS_\w+ X25519 [01] true\n', out), out
        # The system's roots (here an unrelated root, so the result does not depend on the runner's
        # bundle) do not include the server's certificate: refused.
        out = run('verify', srv.addr(), 'localhost', env={'SSL_CERT_FILE': str(certs['unrelated'][0])})
        assert out.startswith('fault tls: x509: certificate signed by unknown authority'), out
        want = hashlib.sha256(b'hello over tls').hexdigest()
        out = run('https', f'https://127.0.0.1:{srv.port}/')
        assert out == f'get 200 14 {want}\npost 200 posted over tls\n', out
        out = run('wss', f'wss://127.0.0.1:{srv.port}/ws')
        assert out == 'wss true echo: hello wss\n', out
    finally:
        srv.stop()
    srv = Server(exe, certs['rsa'], work)
    try:
        r = subprocess.run([str(client), 'resume', srv.addr(), '1', str(certs['rsa'][0])], capture_output=True, text=True, timeout=60)
        assert re.fullmatch(r'resumed false TLS_\w+ X25519 1 true\n', r.stdout), r.stdout
    finally:
        srv.stop()
    print('PASS Tin client: tls.Dial with and without ALPN, verified through RootCAs (ECDSA and RSA keys) and refused by default; '
          'wire https:// GET and POST; websocket wss:// through websocket.Accept')


# ---- session resumption (#472) ----

def resumed_get(openssl, port, cafile=None, sess_in=None, sess_out=None, extra=()):
    """One s_client GET /fast: True when it resumed a session, False for a full handshake."""
    args = list(extra)
    if sess_in:
        args += ['-sess_in', str(sess_in)]
    if sess_out:
        args += ['-sess_out', str(sess_out)]
    rc, out = s_client(openssl, port, args, get('/fast'), cafile=cafile)
    assert rc == 0 and '\r\n\r\nfast' in out, out[-1500:]
    assert ('Reused, TLSv1.3' in out) != ('New, TLSv1.3' in out), out[-1500:]
    return 'Reused, TLSv1.3' in out


def tamper_ticket(openssl, sess, out):
    """Write to out the session sess with the last byte of its ticket flipped."""
    text = subprocess.run([openssl, 'sess_id', '-in', str(sess), '-noout', '-text'], capture_output=True, text=True,
                          check=True).stdout
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == 'TLS session ticket:')
    hexes = []
    for l in lines[start + 1:]:
        m = re.match(r'\s*[0-9a-f]{4} - ((?:[0-9a-f]{2}[ -]?)+)', l)
        if not m:
            break
        hexes += re.findall(r'[0-9a-f]{2}', m.group(1))
    ticket = bytes(int(h, 16) for h in hexes)
    pem = sess.read_text()
    body = ''.join(l for l in pem.splitlines() if not l.startswith('-----'))
    der = base64.b64decode(body)
    at = der.find(ticket)
    assert len(ticket) > 32 and at >= 0, (len(ticket), at)
    der = der[:at + len(ticket) - 1] + bytes([der[at + len(ticket) - 1] ^ 1]) + der[at + len(ticket):]
    b64 = base64.b64encode(der).decode()
    out.write_text('-----BEGIN SSL SESSION PARAMETERS-----\n' +
                   '\n'.join(b64[i:i + 64] for i in range(0, len(b64), 64)) +
                   '\n-----END SSL SESSION PARAMETERS-----\n')


def resumption(openssl, exe, client, certs, work):
    cert = certs['ecdsa']
    sess, bad = work / 'sess.pem', work / 'sess-tampered.pem'
    # Four cores: the accepting core deals connections round-robin, so the resumptions below
    # land on cores that never saw the ticket.
    srv = Server(exe, cert, work, cores=4)
    try:
        assert not resumed_get(openssl, srv.port, cert[0], sess_out=sess)
        reused = [resumed_get(openssl, srv.port, cert[0], sess_in=sess) for _ in range(8)]
        assert all(reused), reused
        # A key share the server does not take: HelloRetryRequest, then the PSK binder over it.
        rc, out = s_client(openssl, srv.port, ['-sess_in', str(sess), '-groups', 'P-384:X25519', '-msg'], get('/fast'),
                           cafile=cert[0])
        assert rc == 0 and 'Reused, TLSv1.3' in out and out.count('ClientHello') == 2, out[-1500:]
        tamper_ticket(openssl, sess, bad)
        assert not resumed_get(openssl, srv.port, cert[0], sess_in=bad)
        r = subprocess.run([str(client), 'resume', srv.addr(), '3', str(cert[0])], capture_output=True, text=True, timeout=60)
        assert re.fullmatch(r'resumed false TLS_\w+ X25519 1 true\n(resumed true TLS_\w+ X25519 [01] true\n){2}', r.stdout), r.stdout
        if PY_TLS13:
            ctx = py_ctx(cert)
            s = py_connect(srv, ctx)
            s.sendall(get('/fast'))
            read_to_close(s)
            session = s.session
            s.close()
            raw = socket.create_connection(('127.0.0.1', srv.port), timeout=20)
            s = ctx.wrap_socket(raw, server_hostname='127.0.0.1', session=session)
            s.sendall(get('/fast'))
            assert read_to_close(s).endswith(b'fast') and s.session_reused, 'Python did not resume'
            s.close()
    finally:
        srv.stop()
    # Processes that share TIN_TLS_TICKET_SECRET resume each other's sessions; another secret,
    # a lifetime past, or tickets turned off give a full handshake.
    key = os.urandom(32).hex()
    srv = Server(exe, cert, work, env={'TIN_TLS_TICKET_SECRET': key})
    try:
        assert not resumed_get(openssl, srv.port, cert[0], sess_out=sess)
        issued = time.monotonic()
    finally:
        srv.stop()
    for env, want in (({'TIN_TLS_TICKET_SECRET': key}, True), ({'TIN_TLS_TICKET_SECRET': os.urandom(32).hex()}, False),
                      ({'TIN_TLS_TICKET_SECRET': key, 'TIN_TLS_TICKETS': '0'}, False),
                      ({'TIN_TLS_TICKET_SECRET': key, 'TIN_TLS_TICKET_LIFETIME_S': '1'}, False)):
        if 'TIN_TLS_TICKET_LIFETIME_S' in env:
            time.sleep(max(0.0, issued + 2.2 - time.monotonic()))
        srv = Server(exe, cert, work, env=env)
        try:
            assert resumed_get(openssl, srv.port, cert[0], sess_in=sess) == want, env
        finally:
            srv.stop()
    print('PASS resumption: OpenSSL resumes on four cores (8 of 8) and after a HelloRetryRequest, a tampered ticket gets '
          'a full handshake, the Tin and Python clients resume; a shared TIN_TLS_TICKET_SECRET resumes across processes, another secret, '
          'TIN_TLS_TICKETS=0 and a ticket past TIN_TLS_TICKET_LIFETIME_S do not')


# ---- client certificates (mutual TLS, #475) ----

def make_pki(work):
    """The client-certificate test PKI (tools/ci/fixtures/mtlspki.go): CA, alice, rsa, bob (server
    only), carol (expired), mallory (another CA)."""
    pki = work / 'pki'
    pki.mkdir(exist_ok=True)
    subprocess.run(['go', 'run', str(ROOT / 'tools/ci/fixtures/mtlspki.go'), str(pki)], cwd=ROOT, check=True, timeout=300)
    return pki


def mtls(openssl, exe, client, certs, work):
    pki = make_pki(work)
    cert = certs['ecdsa']

    def who(name):
        return ['-cert', str(pki / f'{name}.pem'), '-key', str(pki / f'{name}.key')]

    sess = work / 'mtls-sess.pem'
    srv = Server(exe, cert, work, env={'TLS_CLIENT_AUTH': '2', 'TLS_CLIENT_CAS': str(pki / 'ca.pem')}, cores=2)
    try:
        for name, cn in (('alice', 'alice'), ('rsa', 'rsa-client')):
            rc, out = s_client(openssl, srv.port, who(name) + ['-sess_out', str(sess)], get('/whoami'), cafile=cert[0])
            assert rc == 0 and f'cn={cn} chain=1 resumed=false' in out, (name, out[-1500:])
        # A resumed session keeps the client's identity (the ticket carries the chain).
        rc, out = s_client(openssl, srv.port, ['-sess_in', str(sess)], get('/whoami'), cafile=cert[0])
        assert rc == 0 and 'Reused, TLSv1.3' in out and 'cn=rsa-client chain=1 resumed=true' in out, out[-1500:]
        for name, alert in ((None, 116), ('bob', 42), ('carol', 45), ('mallory', 48)):
            args = who(name) if name else []
            rc, out = s_client(openssl, srv.port, args, get('/whoami'), cafile=cert[0])
            assert f'alert number {alert}' in out and 'cn=' not in out, (name, alert, out[-1500:])
        r = subprocess.run([str(client), 'mtls', srv.addr(), '2', str(cert[0]), str(pki / 'alice.pem'), str(pki / 'alice.key')],
                           capture_output=True, text=True, timeout=60)
        assert r.stdout == 'mtls false cn=alice chain=1 resumed=false\nmtls true cn=alice chain=1 resumed=true\n', r.stdout
        r = subprocess.run([str(client), 'mtls', srv.addr(), '1', str(cert[0])], capture_output=True, text=True, timeout=60)
        assert r.stdout == 'fault tls: remote error: certificate required\n', r.stdout
        # wire with client certificates: alice, then dave, then alice again; a kept connection is
        # never lent to the other identity.
        r = subprocess.run([str(client), 'wiremtls', f'https://localhost:{srv.port}/whoami', str(cert[0]),
                            str(pki / 'alice.pem'), str(pki / 'alice.key'), str(pki / 'rsa.pem'), str(pki / 'rsa.key')],
                           capture_output=True, text=True, timeout=60)
        lines = r.stdout.splitlines()
        assert len(lines) == 3 and lines[0].startswith('wire 200 cn=alice ') and lines[1].startswith('wire 200 cn=rsa-client ') \
            and lines[2].startswith('wire 200 cn=alice '), r.stdout
        if PY_TLS13:
            ctx = py_ctx(cert)
            ctx.load_cert_chain(str(pki / 'alice.pem'), str(pki / 'alice.key'))
            s = py_connect(srv, ctx)
            s.sendall(get('/whoami'))
            assert read_to_close(s).endswith(b'cn=alice chain=1 resumed=false'), 'Python client certificate'
            s.close()
    finally:
        srv.stop()
    # RequestClientCert: a client without a certificate is served; one that sends a bad one is not.
    srv = Server(exe, cert, work, env={'TLS_CLIENT_AUTH': '1', 'TLS_CLIENT_CAS': str(pki / 'ca.pem')})
    try:
        rc, out = s_client(openssl, srv.port, [], get('/whoami'), cafile=cert[0])
        assert rc == 0 and '\r\n\r\nnone' in out, out[-1500:]
        rc, out = s_client(openssl, srv.port, who('alice'), get('/whoami'), cafile=cert[0])
        assert rc == 0 and 'cn=alice' in out, out[-1500:]
        rc, out = s_client(openssl, srv.port, who('mallory'), get('/whoami'), cafile=cert[0])
        assert 'alert number 48' in out and 'cn=' not in out, out[-1500:]
    finally:
        srv.stop()
    # A server without ClientCAs does not start.
    p = subprocess.run([str(exe)], env=dict(os.environ, PORT=str(free_port()), TLS_CERT=str(cert[0]), TLS_KEY=str(cert[1]),
                                            TLS_CLIENT_AUTH='2', TLS_CLIENT_CAS=str(cert[1])),
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0 and 'server:' in p.stdout and 'ClientCAs' in p.stdout, p.stdout + p.stderr
    print('PASS client certificates: openssl (ECDSA and RSA keys), Python and the Tin client verified; a resumed session keeps '
          'the identity; certificate_required, bad_certificate (server-only usage), certificate_expired and unknown_ca '
          'refusals; RequestClientCert serves a client without one; ClientCAs without a certificate fail at start')


# ---- malformed handshakes and timeouts ----

def exchange(port, data, wait=5.0):
    """Send data, then read until the server closes: (bytes, seconds)."""
    s = socket.create_connection(('127.0.0.1', port), timeout=wait)
    t0 = time.time()
    if data:
        s.sendall(data)
    got = b''
    try:
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            got += chunk
    except socket.timeout:
        got += b'<timeout>'
    except ConnectionResetError:
        got += b'<reset>'
    s.close()
    return got, time.time() - t0


def alert(desc):
    return b'\x15\x03\x03\x00\x02\x02' + bytes([desc])


def malformed(exe, client, certs, work):
    srv = Server(exe, certs['ecdsa'], work, env={'TIN_HANDSHAKE_TIMEOUT_MS': '1000', 'TIN_HEADER_TIMEOUT_MS': '1500'})
    try:
        cases = [
            ('plain HTTP to the TLS port', get('/'), alert(10)),
            ('a record longer than TLS allows', b'\x16\x03\x01\x4e\x20' + b'\x00' * 16, alert(22)),
            ('a truncated ClientHello body', b'\x16\x03\x01\x00\x08\x01\x00\x00\x04\x03\x03\xff\xff', alert(50)),
            ('Finished before ClientHello', b'\x16\x03\x01\x00\x08\x14\x00\x00\x04abcd', alert(10)),
            ('an unknown record type', b'\x63\x03\x03\x00\x01\x00', alert(10)),
        ]
        for name, data, want in cases:
            got, took = exchange(srv.port, data)
            assert got == want and took < 3, (name, got, took)
        # A client that never sends, and one that stops in the middle of its ClientHello: closed
        # at the handshake timeout (1 s here), after an alert.
        for name, data in (('silent', b''), ('half a ClientHello', b'\x16\x03\x01\x01\x00' + b'\x01\x00\x00\xfc' + b'\x03' * 60)):
            got, took = exchange(srv.port, data)
            assert got in (b'', alert(80)) and 0.9 < took < 3.5, (name, got, took)
        # A completed handshake with no request: the header timeout (1.5 s here) closes it, with close_notify.
        r = subprocess.run([str(client), 'truncated', srv.addr()], capture_output=True, text=True, timeout=30)
        assert r.stdout.startswith('fault EOF 0'), r.stdout
        out = subprocess.run([str(client), 'get', srv.addr()], capture_output=True, text=True, timeout=30).stdout
        assert out.startswith('ok '), out
    finally:
        srv.stop()
    print('PASS malformed handshakes: plain HTTP, an oversized record, a truncated ClientHello, Finished first and an unknown record '
          'type get their alerts; silent and stalled clients close at the handshake timeout, an idle one at the header timeout '
          'with close_notify; the server serves on')


# ---- one core: handshakes never hold up a fast request ----

def https_fast(port, client, srv):
    t0 = time.time()
    out = subprocess.run([str(client), 'https', f'https://127.0.0.1:{port}/'], capture_output=True, text=True, timeout=30).stdout
    assert out.startswith('get 200 14'), out
    return time.time() - t0


def one_core(exe, client, certs, work):
    srv = Server(exe, certs['ecdsa'], work, env={'TIN_HANDSHAKE_TIMEOUT_MS': '20000'})
    held = []
    try:
        base = min(https_fast(srv.port, client, srv) for _ in range(3))
        # 300 connections that never send and 100 that stop in their ClientHello: each is a
        # handshake task waiting on its socket.
        for i in range(400):
            s = socket.create_connection(('127.0.0.1', srv.port), timeout=10)
            if i % 4 == 0:
                s.sendall(b'\x16\x03\x01\x01\x00\x01\x00\x00\xfc\x03\x03')
            held.append(s)
        time.sleep(0.3)
        stalled = max(https_fast(srv.port, client, srv) for _ in range(5))
        assert stalled < base + 1.0, f'a fast request took {stalled:.2f} s behind 400 stalled handshakes (alone: {base:.2f} s)'
        # A burst of 64 full handshakes at once, with a waiting request, and a fast one beside them.
        results = []

        def full():
            results.append(subprocess.run([str(client), 'get', srv.addr()], capture_output=True, text=True, timeout=60).stdout)

        slow = []

        def waiting():
            out = subprocess.run([str(client), 'https', f'https://127.0.0.1:{srv.port}/slow?ms=1500'], capture_output=True,
                                 text=True, timeout=60).stdout
            slow.append(out.split('\n')[0])

        ts = threading.Thread(target=waiting)
        ts.start()
        burst = [threading.Thread(target=full) for _ in range(64)]
        for t in burst:
            t.start()
        samples = [https_fast(srv.port, client, srv)]
        while any(t.is_alive() for t in burst):
            samples.append(https_fast(srv.port, client, srv))
        during = max(samples)
        for t in burst:
            t.join()
        ts.join()
        assert len(results) == 64 and all(r.startswith('ok ') for r in results), [r for r in results if not r.startswith('ok ')][:3]
        assert slow == [f'get 200 9 {hashlib.sha256(b"slow done").hexdigest()}'], slow
        assert during < 3.0, f'a fast request took {during:.2f} s during 64 handshakes'
    finally:
        for s in held:
            s.close()
        srv.stop()
    print(f'PASS one core: a fast https request takes {stalled:.3f} s with 400 stalled handshakes (alone {base:.3f} s) and '
          f'{during:.3f} s during a burst of 64 handshakes and a waiting request')


# ---- memory ----

def memory(openssl, exe, certs, work):
    srv = Server(exe, certs['ecdsa'], work)
    try:
        # Warm up, then stream 256 MiB in 64 KiB writes over one TLS connection.
        s_client(openssl, srv.port, ['-quiet'], get('/stream?n=64&size=65536'))
        base = srv.rss_kb()
        peak = [base]
        stop = threading.Event()

        def watch():
            while not stop.is_set():
                peak[0] = max(peak[0], srv.rss_kb())
                time.sleep(0.05)

        w = threading.Thread(target=watch)
        w.start()
        cmd = [openssl, 's_client', '-tls1_3', '-quiet', '-connect', srv.addr()]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        p.stdin.write(get('/stream?n=4096&size=65536'))
        p.stdin.flush()
        total = 0
        while True:
            chunk = p.stdout.read(1 << 20)
            if not chunk:
                break
            total += len(chunk)
        p.wait()
        stop.set()
        w.join()
        grew = (max(peak[0], srv.rss_kb()) - base) / 1024
        assert total > 256 << 20, total
        assert grew < 24, f'RSS grew by {grew:.0f} MiB while 256 MiB streamed over TLS'
        idle = ''
        if PY_TLS13:
            ctx = py_ctx(certs['ecdsa'])
            before = srv.rss_kb()
            conns = [py_connect(srv, ctx) for _ in range(200)]
            for s in conns:
                s.sendall(get('/fast', False))
                s.recv(4096)
            per = (srv.rss_kb() - before) / 200
            for s in conns:
                s.close()
            assert per < 160, f'an idle TLS connection costs {per:.0f} KiB'
            idle = f'; an idle TLS connection after a request holds {per:.0f} KiB'
    finally:
        srv.stop()
    print(f'PASS memory: 256 MiB streamed over TLS, RSS grew by {grew:.0f} MiB{idle}')


# ---- graceful shutdown ----

def shutdown(exe, certs, work):
    cert = certs['ecdsa']
    srv = Server(exe, cert, work, env={'TIN_GRACE': '5'})
    try:
        s = py_connect(srv, py_ctx(cert))
        s.sendall(get('/slow?ms=1500', False))
        time.sleep(0.3)
        srv.p.send_signal(signal.SIGTERM)
        time.sleep(0.3)
        try:
            socket.create_connection(('127.0.0.1', srv.port), timeout=2).close()
            refused = False
        except OSError:
            refused = True
        data = read_to_close(s)
        s.close()
        code = srv.p.wait(timeout=10)
        assert data.startswith(b'HTTP/1.1 200 OK') and b'Connection: close' in data and data.endswith(b'slow done'), data
        assert refused, 'a new connection was accepted after SIGTERM'
        assert code == 0, code
    finally:
        srv.stop()
    print('PASS graceful shutdown: SIGTERM lets a waiting request answer (Connection: close), the close is a close_notify, '
          'new connections are refused, exit 0')


# ---- the example and configuration errors ----

def example(openssl, compiler, client, certs, work):
    exe = work / 'https_example'
    build(compiler, 'examples/https_server.tin', exe)
    srv = Server(exe, certs['rsa'], work)
    try:
        rc, out = s_client(openssl, srv.port, ['-alpn', 'http/1.1'], get('/'), cafile=certs['rsa'][0])
        assert 'hello over TLS 1.3 (http/1.1, group X25519)' in out and 'Verify return code: 0 (ok)' in out, out[-1500:]
        r = subprocess.run([str(client), 'wss', f'wss://127.0.0.1:{srv.port}/echo'], capture_output=True, text=True, timeout=30)
        assert r.stdout == 'wss true echo: hello wss\n', r.stdout
    finally:
        srv.stop()
    print('PASS examples/https_server.tin: HTTPS verified by OpenSSL, wss:// echo')


def server_keylog(openssl, exe, certs, work):
    """SSLKEYLOGFILE on the server (#478): anvil logs the four secrets openssl s_client logs."""
    from tls_check import keylog_lines
    cert = certs['ecdsa']
    mine, theirs = work / 'keylog-anvil.txt', work / 'keylog-s_client.txt'
    srv = Server(exe, cert, work, env={'SSLKEYLOGFILE': str(mine)})
    try:
        rc, out = s_client(openssl, srv.port, ['-keylogfile', str(theirs)], get('/fast'))
        assert rc == 0 and '\r\n\r\nfast' in out, out[-1500:]
    finally:
        srv.stop()
    a, b = keylog_lines(mine), keylog_lines(theirs)
    assert len(a) == 4 and a == b, (a, b)
    print('PASS SSLKEYLOGFILE: anvil logs the four TLS 1.3 traffic secrets openssl s_client logs for the connection')


def bad_config(exe, certs, work):
    for name, pair, want in (('a key of another certificate', (certs['ecdsa'][0], certs['rsa'][1]), 'does not belong'),
                             ('an Ed25519 key', certs['ed25519'], 'server: ')):
        srv = Server(exe, pair, work, wait=False)
        try:
            code = srv.p.wait(timeout=20)
            out = srv.output()
            assert code == 0 and out.startswith('server: ') and want in out, (name, code, out)
        finally:
            srv.stop()
    print('PASS configuration: a key that does not match the certificate, and an Ed25519 key, fail ServeTLS before it listens')


def main():
    # 400 held connections: lift a low descriptor limit (macOS starts at 256); servers inherit it.
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    want = 4096 if hard == resource.RLIM_INFINITY else min(4096, hard)
    if soft < want:
        resource.setrlimit(resource.RLIMIT_NOFILE, (want, hard))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default='bin/tinc')
    args = parser.parse_args()
    compiler = (ROOT / args.compiler).resolve()
    openssl = openssl3()
    assert openssl, 'tls_server_check needs an OpenSSL 3 command line (s_client -tls1_3)'
    if sys.platform.startswith('linux'):
        assert PY_TLS13, f'Python ssl without TLS 1.3 on Linux: {ssl.OPENSSL_VERSION}'
    out = ROOT / 'bin/ci/tls_server'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tls-server-', dir=out) as tmp:
        work = Path(tmp)
        exe, client = work / 'https_server', work / 'tls_client'
        build(compiler, 'tools/ci/fixtures/https_server.tin', exe)
        build(compiler, 'tools/ci/fixtures/tls_client.tin', client)
        (work / 'file.bin').write_bytes(os.urandom(5 << 20))
        certs = make_certs(openssl, work)
        openssl_interop(openssl, exe, certs, work)
        tin_clients(exe, client, certs, work)
        resumption(openssl, exe, client, certs, work)
        mtls(openssl, exe, client, certs, work)
        malformed(exe, client, certs, work)
        one_core(exe, client, certs, work)
        memory(openssl, exe, certs, work)
        example(openssl, compiler, client, certs, work)
        bad_config(exe, certs, work)
        server_keylog(openssl, exe, certs, work)
        if PY_TLS13:
            python_clients(exe, certs, work)
            shutdown(exe, certs, work)
        else:
            print(f'SKIP Python ssl clients and the shutdown check: {ssl.OPENSSL_VERSION} has no TLS 1.3')
    print('tls_server: all checks passed')


if __name__ == '__main__':
    main()
