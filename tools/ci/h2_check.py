#!/usr/bin/env python3
"""HTTP/2 in anvil (#360): h2c by prior knowledge and by Upgrade: h2c, on the port that serves
HTTP/1.1, and h2 over TLS by ALPN. The fixture (tools/ci/fixtures/h2.tin) is checked by:

- h2spec (H2SPEC, or h2spec on PATH; required when CI is set): every generic, http2 and hpack
  case but http2/3.5/2, which sends "INVALID CONNECTION PREFACE" to a port that also speaks
  HTTP/1.1, where it is a malformed HTTP/1.1 request line and gets 400 (RFC 9113 3.4 applies once a
  connection is known to be HTTP/2: with prior knowledge after "PRI * HTTP/2.0", or over TLS);
- Go's own HTTP/2 client (fixtures/h2client.go, net/http with h2c): Huffman-coded and indexed
  headers, request and response trailers, large bodies both ways, a streamed body, HEAD and 600
  requests on one connection;
- a gRPC client (grpc-go, tools/ci/grpc) against examples/grpc.tin;
- over TLS (ServeTLS, #124): h2 by ALPN with raw frames, h2spec (every case) and Go's client,
  HTTP/1.1 for clients that do not offer h2, and no h2c over TLS;
- raw frames (h2wire.py): the server's settings, exact flow control, the HPACK dynamic table under
  insertions, evictions and size updates, multiplexed waits, cancels by RST_STREAM and by a closed
  connection, the write timeout, limits (413, 431), CONTINUATION, 100-continue, the Upgrade,
  streamed responses and their failures, rapid resets, flat memory, and the graceful drain.
"""
import os
from pathlib import Path
import shutil
import signal
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time

from suite import ROOT
import h2wire as w

H2SPEC_SKIP = 'http2/3.5/2'
PY_TLS13 = getattr(ssl, 'HAS_TLSv1_3', False) and not ssl.OPENSSL_VERSION.startswith('LibreSSL')
H2SPEC_SECTIONS = ['generic', 'hpack', 'http2/3.5/1', 'http2/4', 'http2/5', 'http2/6', 'http2/7', 'http2/8']


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def eventually(check, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(.02)
    return check()


class Server:
    def __init__(self, exe, log, cores=2, **env):
        self.port = free_port()
        self.path = log
        self.log = open(log, 'wb')
        self.p = subprocess.Popen([str(exe)], stdout=self.log, stderr=subprocess.STDOUT,
                                  env=dict(os.environ, PORT=str(self.port), TIN_CORES=str(cores), **env))

        def ready():
            assert self.p.poll() is None, 'the server exited during startup'
            try:
                socket.create_connection(('127.0.0.1', self.port), timeout=.1).close()
                return True
            except OSError:
                return False
        assert eventually(ready, 10), 'the server did not start'

    def logged(self):
        return self.path.read_text(errors='replace')

    def rss_kb(self):
        r = subprocess.run(['ps', '-o', 'rss=', '-p', str(self.p.pid)], capture_output=True, text=True)
        return int(r.stdout.strip() or 0)

    def stop(self):
        if self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait()
        self.log.close()


def pattern(n, start=0):
    return bytes((start + i) % 251 for i in range(n))


def one(port, path, method='GET', headers=(), body=None, settings=()):
    c = w.Conn(port, client_settings=settings)
    try:
        c.request(1, method, path, headers, body)
        return c.responses([1])[1]
    finally:
        c.close()


def fields(r):
    return dict(r['headers'])


# ---- h2spec, Go and gRPC clients ----

def check_h2spec(port, out, tls=False):
    h2spec = os.environ.get('H2SPEC') or shutil.which('h2spec')
    if not h2spec:
        if os.environ.get('CI'):
            raise AssertionError('h2spec is required in CI (set H2SPEC)')
        print('SKIP h2spec: not installed (go install github.com/summerwind/h2spec/cmd/h2spec@'
              'v1.5.1-0.20220625142712-af83a65f0b62, then H2SPEC=path)')
        return
    name = 'h2spec-tls' if tls else 'h2spec'
    # Over TLS a connection is HTTP/2 from its handshake (ALPN), so every case applies, 3.5/2 too.
    args = ['-t', '-k', 'generic', 'hpack', 'http2'] if tls else H2SPEC_SECTIONS
    r = subprocess.run([h2spec, '-h', '127.0.0.1', '-p', str(port), '-o', '3', '-j', str(out / (name + '.xml'))] + args,
                       capture_output=True, text=True, timeout=600)
    (out / (name + '.log')).write_text(r.stdout + r.stderr)
    tail = [l for l in r.stdout.splitlines() if 'tests,' in l]
    assert r.returncode == 0 and tail and ' 0 failed' in tail[-1], 'h2spec failed:\n' + r.stdout[-6000:]
    if tls:
        print('PASS h2spec over TLS (h2 by ALPN):', tail[-1].strip())
    else:
        print('PASS h2spec:', tail[-1].strip(), '(skipped by design: %s)' % H2SPEC_SKIP)


def check_go_client(port, out, ca=None):
    exe = out / 'h2client'
    subprocess.run(['go', 'build', '-o', str(exe), './tools/ci/fixtures/h2client.go'], cwd=ROOT, check=True)
    r = subprocess.run([str(exe), '-addr', '127.0.0.1:%d' % port] + (['-ca', str(ca)] if ca else []),
                       capture_output=True, text=True, timeout=120)
    sys.stdout.write(r.stdout)
    assert r.returncode == 0, "Go's HTTP/2 client failed:\n" + r.stdout + r.stderr


def check_grpc(out):
    exe = out / 'grpc'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'examples/grpc.tin'], cwd=ROOT,
                   env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    client = out / 'grpcclient'
    subprocess.run(['go', 'build', '-o', str(client), '.'], cwd=ROOT / 'tools/ci/grpc', check=True)
    # The Tin client (#480, examples/grpc_client.tin) over wire's h2c, and a grpc-go server.
    tin_client = out / 'grpc_client'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(tin_client), 'examples/grpc_client.tin'], cwd=ROOT,
                   env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    go_server = out / 'grpcserver'
    subprocess.run(['go', 'build', '-o', str(go_server), './server'], cwd=ROOT / 'tools/ci/grpc', check=True)

    def tin_calls(addr, who):
        for name, want in (('tin', 'Hello tin\n'), ('', 'grpc: InvalidArgument: name is required\n')):
            r = subprocess.run([str(tin_client), name], capture_output=True, text=True, timeout=60, env=dict(os.environ, ADDR=addr))
            assert r.stdout == want, (who, name, r.stdout, r.stderr[-1000:])
        print(f'grpc: PASS the Tin client (wire, h2c) calls {who}: a reply, and InvalidArgument from the status')

    srv = Server(exe, out / 'grpc.log')
    try:
        r = subprocess.run([str(client), '-addr', '127.0.0.1:%d' % srv.port], capture_output=True, text=True, timeout=120)
        sys.stdout.write(''.join('grpc: ' + l + '\n' for l in r.stdout.splitlines()))
        assert r.returncode == 0, 'the gRPC client failed:\n' + r.stdout + r.stderr
        tin_calls('127.0.0.1:%d' % srv.port, 'examples/grpc.tin')
    finally:
        srv.stop()
    port = free_port()
    gs = subprocess.Popen([str(go_server), '-addr', '127.0.0.1:%d' % port], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        assert gs.stdout.readline().strip() == 'listening'
        tin_calls('127.0.0.1:%d' % port, 'a grpc-go server')
    finally:
        gs.kill()
        gs.wait()


# ---- raw frames ----

def check_settings(port):
    c = w.Conn(port)
    f = c.read_frame()
    assert f[0] == w.SETTINGS and f[1] == 0 and f[2] == 0, f
    got = {struct.unpack('>H', f[3][i:i + 2])[0]: struct.unpack('>I', f[3][i + 2:i + 6])[0] for i in range(0, len(f[3]), 6)}
    assert got == {3: 100, 4: 1048576, 6: 65536}, got
    f = c.read_frame()
    assert f[0] == w.WINDOW_UPDATE and struct.unpack('>I', f[3])[0] == 4194304 - 65535, f
    c.request(1, 'GET', '/')
    r = c.responses([1])[1]
    h = fields(r)
    assert h[':status'] == '200' and h['server'] == 'anvil' and 'date' in h and h['content-length'] == str(len(r['body']))
    assert r['body'] == b'hello from anvil over HTTP/2.0\n', r['body']
    c.close()
    print('PASS preface: SETTINGS (100 streams, 1 MiB stream window, 64 KiB header list) and a 4 MiB connection window')


def check_hpack_table(port):
    import random
    rnd = random.Random(360)
    c = w.Conn(port)
    enc = w.Encoder()
    values = ['v%d-' % i + 'x' * rnd.randrange(0, 300) for i in range(60)]
    sid = 1
    for i in range(800):
        if i % 97 == 0:
            enc.resize(rnd.choice([0, 100, 1000, 4096]))
        xt = rnd.choice(values)
        ck = rnd.choice(values)
        block = enc.encode([(':method', 'POST'), (':scheme', 'http'), (':path', '/echo?i=%d' % (i % 7)),
                            (':authority', 'h2.test'), ('x-test', xt), ('cookie', ck), ('x-pad', rnd.choice(values))])
        c.send(w.frame(w.HEADERS, w.END_HEADERS | w.END_STREAM, sid, block))
        r = c.responses([sid])[sid]
        m = dict(l.split('=', 1) for l in r['body'].decode().splitlines() if '=' in l)
        assert m['x-test'] == xt and m['cookie'] == ck and m['query'] == 'i=%d' % (i % 7) and m['host'] == 'h2.test', (i, m)
        sid += 2
    c.close()
    print('PASS HPACK dynamic table: 800 requests with indexed fields, insertions, evictions and size updates')


def check_huffman(port):
    import random
    rnd = random.Random(7541)
    alphabet = [b for b in range(1, 256) if b not in (10, 13)]
    c = w.Conn(port)
    sid = 1
    for i in range(400):
        n = rnd.randrange(0, 200)
        v = bytes(rnd.choice(alphabet) for _ in range(n)).strip(b' \t')
        block = (w.encode([(':method', 'GET'), (':scheme', 'http'), (':path', '/echo'), (':authority', 'x')]) +
                 b'\x00' + w.enc_huff('x-test') + w.enc_huff(v))
        c.send(w.frame(w.HEADERS, w.END_HEADERS | w.END_STREAM, sid, block))
        r = c.responses([sid])[sid]
        got = [l for l in r['body'].split(b'\n') if l.startswith(b'x-test=')][0][7:]
        assert got == v, (i, v, got)
        sid += 2
    c.close()
    print('PASS Huffman: 400 values of every byte but CR and LF decode exactly')


def check_multiplexing(port):
    c = w.Conn(port)
    t = time.monotonic()
    for i in range(8):
        c.request(1 + 2 * i, 'GET', '/wait?ms=400')
    c.request(17, 'GET', '/')
    c.responses([17])
    fast = time.monotonic() - t
    r = c.responses([1 + 2 * i for i in range(8)])
    took = time.monotonic() - t
    assert all(x['body'] == b'waited 400' for x in r.values())
    assert fast < 0.2 and took < 1.5, (fast, took)
    c.close()
    print('PASS multiplexing: a request behind eight waiting ones answered after %.3f s, all after %.3f s' % (fast, took))


def check_flow_control(port):
    c = w.Conn(port, client_settings=[(4, 10)])
    c.request(1, 'GET', '/big?n=1000')
    got, conn_win, win, sizes = b'', 65535, 10, []
    while True:
        typ, flags, sid, payload = c.read_frame()
        if typ != w.DATA:
            continue
        conn_win -= len(payload)
        win -= len(payload)
        assert conn_win >= 0 and win >= 0, (conn_win, win)
        sizes.append(len(payload))
        got += payload
        if flags & w.END_STREAM:
            break
        if win == 0:
            c.send(w.frame(w.WINDOW_UPDATE, 0, 1, struct.pack('>I', 99)))
            win += 99
    assert got == pattern(1000) and sizes[0] == 10 and max(sizes) == 99, sizes
    # A larger SETTINGS_MAX_FRAME_SIZE: DATA frames grow past 16 KiB (anvil caps them at 64 KiB).
    c2 = w.Conn(port, client_settings=[(5, 1 << 20), (4, 1 << 30)])
    c2.send(w.frame(w.WINDOW_UPDATE, 0, 0, struct.pack('>I', 1 << 30)))
    c2.request(1, 'GET', '/big?n=500000')
    r = c2.responses([1])[1]
    sizes2 = [f[1] for f in r['frames'] if f[0] == 'DATA']
    assert r['body'] == pattern(500000) and max(sizes2) == 65536, max(sizes2)
    c.close()
    c2.close()
    print('PASS flow control: never past either window (first frame 10 bytes, then 99 per update); 64 KiB frames when allowed')


def check_read_while_writing(exe, out):
    """#506: a client that cannot read until the server takes what it writes (Go's: its reader needs
    the lock its writer holds) must not wait for a server that stopped reading because its own
    output waits. The client's buffers are small and it reads none of 8 MB of responses while it
    sends 4 MB of requests: the server must keep reading, or both wait for the write timeout."""
    srv = Server(exe, out / 'h2rw.log', TIN_WRITE_TIMEOUT_MS='20000', TIN_MAX_BODY='2000000')
    try:
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 16384)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16384)
        s.settimeout(20)
        s.connect(('127.0.0.1', srv.port))
        c = w.Conn.__new__(w.Conn)
        c.sock, c.buf, c.dec, c.port = s, b'', w.Decoder(), srv.port
        c.send(w.PREFACE + w.settings((4, 1 << 24)) + w.frame(w.WINDOW_UPDATE, 0, 0, struct.pack('>I', 1 << 28)))
        gets = list(range(1, 16, 2))
        for sid in gets:
            c.request(sid, 'GET', '/big?n=1000000')
        time.sleep(1)  # the server's output has filled the sockets
        body = pattern(100000)
        posts = list(range(17, 17 + 2 * 40, 2))
        failed = []

        def write():
            try:
                for sid in posts:
                    c.request(sid, 'POST', '/echo', end=False)
                    for i in range(0, len(body), 16384):
                        last = i + 16384 >= len(body)
                        c.send(w.frame(w.DATA, w.END_STREAM if last else 0, sid, body[i:i + 16384]))
            except OSError as e:
                failed.append(e)

        t = threading.Thread(target=write, daemon=True)
        t0 = time.monotonic()
        t.start()
        t.join(15)
        assert not t.is_alive() and not failed, ('the server stopped reading while its output waited', failed)
        sent = time.monotonic() - t0
        r = c.responses(gets + posts, window_updates=False)
        for sid in gets:
            assert r[sid]['body'] == pattern(1000000), sid
        for sid in posts:
            assert w.status(r[sid]) == '200' and b'len=100000\n' in r[sid]['body'], (sid, r[sid]['body'][:80])
        c.close()
        assert srv.p.poll() is None, 'the server died'
    finally:
        srv.stop()
    print('PASS reading goes on while output waits: 4 MB written to a server whose 8 MB of responses the client had not read (%.1fs)' % sent)


def check_cancels(srv):
    port = srv.port
    c = w.Conn(port)
    c.request(1, 'GET', '/wait?ms=5000')
    time.sleep(.1)
    c.send(w.frame(w.RST_STREAM, 0, 1, struct.pack('>I', 8)))
    assert eventually(lambda: 'the client reset the stream' in srv.logged(), 2), srv.logged()[-2000:]
    c.request(3, 'GET', '/')
    assert c.responses([3])[3]['body'].startswith(b'hello')
    c.close()
    before = srv.logged().count('the connection closed')
    c = w.Conn(port)
    for i in range(5):
        c.request(1 + 2 * i, 'GET', '/wait?ms=5000')
    time.sleep(.1)
    c.close()
    assert eventually(lambda: srv.logged().count('the connection closed') - before == 5, 2), srv.logged()[-2000:]
    print('PASS cancels: RST_STREAM cancels its handler, a closed connection cancels all five')


def check_write_timeout(srv):
    # The client never opens the stream's window again (the connection's is wide open): the
    # stream's write fails after TIN_WRITE_TIMEOUT_MS, and the other streams go on.
    c = w.Conn(srv.port)
    c.send(w.frame(w.WINDOW_UPDATE, 0, 0, struct.pack('>I', 1 << 30)))
    t = time.monotonic()
    c.request(1, 'GET', '/endless')
    reset = None
    while reset is None:
        f = c.read_frame()
        if f[0] == w.RST_STREAM and f[2] == 1:
            reset = struct.unpack('>I', f[3])[0]
    took = time.monotonic() - t
    assert reset == 8 and 1.0 < took < 4, (reset, took)
    assert eventually(lambda: 'endless stopped' in srv.logged() and 'the client stopped reading' in srv.logged(), 2)
    c.request(3, 'GET', '/')
    assert c.responses([3])[3]['body'].startswith(b'hello')
    c.close()
    print('PASS write timeout: a client that keeps its window shut gets RST_STREAM(CANCEL) after %.1f s; the handler sees it' % took)


def check_limits(port):
    c = w.Conn(port)
    c.request(1, 'POST', '/echo', body=None, end=False)
    for i in range(140):
        c.send(w.frame(w.DATA, 0, 1, b'x' * 16384))
    c.send(w.frame(w.DATA, w.END_STREAM, 1, b'end'))
    r = c.responses([1])[1]
    assert w.status(r) == '413', r
    c.request(3, 'GET', '/', [('x-big', 'y' * 70000)])
    r = c.responses([3])[3]
    assert w.status(r) == '431', r
    c.request(5, 'GET', '/', [('x-big', 'y' * 40000)])
    assert w.status(c.responses([5])[5]) == '200'
    c.close()
    print('PASS limits: 413 past TIN_MAX_BODY, 431 past 64 KiB of headers (sent in CONTINUATION frames); the connection goes on')


def check_responses(port, files):
    r = one(port, '/trailers?n=100')
    assert r['body'] == pattern(100) and r['trailers'] == [('x-sum', str(sum(pattern(100)))), ('grpc-status', '0')]
    assert [f[0] for f in r['frames']] == ['HEADERS', 'DATA', 'HEADERS'] and r['frames'][-1][1] & w.END_STREAM
    r = one(port, '/streamtrailers')
    assert r['body'] == b'part one;part two' and r['trailers'] == [('x-done', 'yes')]
    r = one(port, '/stream?n=5&size=3000&ms=20')
    assert r['body'] == pattern(15000)
    r = one(port, '/length?n=50000')
    assert fields(r)['content-length'] == '50000' and r['body'] == pattern(50000)
    r = one(port, '/short')
    assert r['body'] == b'12345' and r['reset'] == 2, r
    r = one(port, '/file?name=big')
    assert r['body'] == (files / 'big').read_bytes() and fields(r)['content-length'] == str(len(r['body']))
    r = one(port, '/file?name=big&off=1000&n=5000')
    assert r['body'] == (files / 'big').read_bytes()[1000:6000]
    r = one(port, '/headers?n=30&size=1000')
    assert len(r['headers']) == 35 and r['body'] == b'headers 30'
    r = one(port, '/status?code=204')
    assert w.status(r) == '204' and r['body'] == b'' and 'content-length' not in fields(r)
    r = one(port, '/', 'HEAD')
    assert r['body'] == b'' and fields(r)['content-length'] == '31' and r['frames'] == [('HEADERS', 5)]
    r = one(port, '/abort')
    assert r['body'] == b'partial' and r['reset'] == 2
    r = one(port, '/hijack')
    assert w.status(r) == '400' and b'cannot be hijacked' in r['body']
    c = w.Conn(port)
    c.request(1, 'GET', '/panic')
    r = c.responses([1])[1]
    assert w.status(r) == '500' and r['body'] == b'Internal Server Error'
    c.request(3, 'GET', '/streampanic')
    r = c.responses([3])[3]
    assert r['body'] == b'partial' and r['reset'] == 2
    c.request(5, 'GET', '/')
    assert c.responses([5])[5]['body'].startswith(b'hello')
    c.close()
    print('PASS responses: trailers, streamed and Length bodies, SendFile, CONTINUATION, 204, HEAD; '
          'a short Length, Abort and a panic after the head reset the stream, a panic before it is 500')


def check_header_table_size(port):
    c = w.Conn(port, client_settings=[(1, 0)])
    c.request(1, 'GET', '/')
    while True:
        f = c.read_frame()
        if f[0] == w.HEADERS:
            break
    assert f[3][0] == 0x20, f[3][:4].hex()
    c.close()
    print('PASS SETTINGS_HEADER_TABLE_SIZE 0: the next header block starts with a table size update')


def check_upgrade(port):
    s = socket.create_connection(('127.0.0.1', port), timeout=5)
    body = b'upgrade body'
    s.sendall(b'POST /echo?u=1 HTTP/1.1\r\nHost: up.test\r\nConnection: Upgrade, HTTP2-Settings\r\nUpgrade: h2c\r\n'
              b'HTTP2-Settings: AAMAAABkAARAAAAA\r\nX-Test: up\r\nContent-Length: %d\r\n\r\n' % len(body) + body)
    buf = b''
    while b'\r\n\r\n' not in buf:
        buf += s.recv(4096)
    head, rest = buf.split(b'\r\n\r\n', 1)
    assert head.startswith(b'HTTP/1.1 101 Switching Protocols\r\n') and b'Upgrade: h2c' in head, head
    c = w.Conn.__new__(w.Conn)
    c.sock, c.buf, c.dec, c.port = s, rest, w.Decoder(), port
    c.send(w.PREFACE + w.settings())
    r = c.responses([1])[1]
    m = dict(l.split('=', 1) for l in r['body'].decode().splitlines() if '=' in l)
    assert m['proto'] == 'HTTP/2.0' and m['len'] == '12' and m['x-test'] == 'up' and m['host'] == 'up.test', m
    c.request(3, 'GET', '/')
    assert c.responses([3])[3]['body'].startswith(b'hello')
    c.close()
    # Without a usable HTTP2-Settings the request is HTTP/1.1, as if Upgrade were not there.
    s = socket.create_connection(('127.0.0.1', port), timeout=5)
    s.sendall(b'GET / HTTP/1.1\r\nHost: x\r\nConnection: Upgrade, HTTP2-Settings, close\r\nUpgrade: h2c\r\n'
              b'HTTP2-Settings: !!\r\n\r\n')
    reply = b''
    while True:
        part = s.recv(4096)
        if not part:
            break
        reply += part
    assert reply.startswith(b'HTTP/1.1 200 OK\r\n') and reply.endswith(b'hello from anvil over HTTP/1.1\n'), reply
    print('PASS Upgrade: h2c: 101, the request with its body is stream 1, stream 3 follows; a bad HTTP2-Settings stays HTTP/1.1')


def check_continue(port):
    c = w.Conn(port)
    c.request(1, 'POST', '/echo', [('expect', '100-continue')], body=None, end=False)
    while True:
        f = c.read_frame()
        if f[0] == w.HEADERS:
            break
    assert c.dec.decode(f[3]) == [(':status', '100')] and not f[1] & w.END_STREAM
    c.send(w.frame(w.DATA, w.END_STREAM, 1, b'abc'))
    r = c.responses([1])[1]
    assert w.status(r) == '200' and b'len=3' in r['body']
    c.close()
    print('PASS expect: 100-continue gets an interim 100 before the body')


def check_http1(port):
    s = socket.create_connection(('127.0.0.1', port), timeout=5)
    s.sendall(b'GET /streamtrailers HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n')
    reply = b''
    while True:
        part = s.recv(4096)
        if not part:
            break
        reply += part
    head, body = reply.split(b'\r\n\r\n', 1)
    assert b'Transfer-Encoding: chunked' in head and body.endswith(b'0\r\nx-done: yes\r\n\r\n'), reply
    r = one(port, '/echo', 'GET')
    assert b'proto=HTTP/2.0' in r['body']
    print('PASS HTTP/1.1 on the same port; a chunked stream carries its trailers after the last chunk')


def check_rapid_reset(srv):
    c = w.Conn(srv.port)
    block = w.encode([(':method', 'GET'), (':scheme', 'http'), (':path', '/wait?ms=2000'), (':authority', 'x')])
    batch = b''.join(w.frame(w.HEADERS, w.END_HEADERS | w.END_STREAM, sid, block) +
                     w.frame(w.RST_STREAM, 0, sid, struct.pack('>I', 8)) for sid in range(1, 20001, 2))
    c.send(batch)
    # Past twice the stream limit of handlers still ending, new streams are refused (REFUSED_STREAM,
    # which a client retries); the cancelled handlers end on the next turns of the loop.
    refused = 0
    c.sock.settimeout(.5)
    try:
        while True:
            f = c.read_frame()
            if f is None:
                break
            if f[0] == w.RST_STREAM and struct.unpack('>I', f[3])[0] == 7:
                refused += 1
    except socket.timeout:
        pass
    c.sock.settimeout(5)
    c.request(20001, 'GET', '/')
    r = c.responses([20001])[20001]
    assert r['body'].startswith(b'hello'), r
    c.close()
    assert one(srv.port, '/')['body'].startswith(b'hello')
    print('PASS rapid reset: 10000 streams opened and reset in one write (%d refused while 200 handlers were ending); '
          'the connection and the server go on' % refused)


def check_memory(srv):
    def burst(n):
        conns = [w.Conn(srv.port) for _ in range(4)]
        sid = 1
        for _ in range(n // (4 * 50)):
            for c in conns:
                for k in range(50):
                    c.request(sid + 2 * k, 'POST' if k % 2 else 'GET', '/echo' if k % 2 else '/big?n=3000',
                              body=b'b' * 2000 if k % 2 else None)
            for c in conns:
                r = c.responses([sid + 2 * k for k in range(50)])
                assert all(w.status(x) == '200' for x in r.values())
            sid += 100
        for c in conns:
            c.close()
    burst(20000)
    before = srv.rss_kb()
    burst(40000)
    after = srv.rss_kb()
    limit = 16 * 1024
    assert after - before < limit, (before, after)
    print('PASS memory: RSS %d KiB after 20000 requests, %d KiB after 40000 more' % (before, after))


def check_drain(exe, out):
    srv = Server(exe, out / 'drain.log', TIN_GRACE='3')
    try:
        idle = w.Conn(srv.port)
        idle.request(1, 'GET', '/')
        idle.responses([1])
        busy = w.Conn(srv.port)
        busy.request(1, 'GET', '/wait?ms=800')
        time.sleep(.1)
        t = time.monotonic()
        srv.p.send_signal(signal.SIGTERM)
        f = idle.read_frame()
        assert f and f[0] == w.GOAWAY and f[3] == struct.pack('>II', 1, 0), f
        assert idle.read_frame() is None
        seen = []
        while True:
            f = busy.read_frame()
            if f is None:
                break
            seen.append(f[0])
            if f[0] == w.DATA and f[2] == 1:
                assert f[3] == b'waited 800'
        assert w.GOAWAY in seen and w.DATA in seen and seen.index(w.GOAWAY) < seen.index(w.DATA), seen
        assert srv.p.wait(timeout=10) == 0
        took = time.monotonic() - t
        assert took < 2.5, took
        print('PASS drain: idle connections get GOAWAY(NO_ERROR) and close, a request in flight finishes, exit 0 after %.2f s' % took)
    finally:
        srv.stop()


# ---- HTTP/2 over TLS (#124) ----

def openssl3():
    """An OpenSSL 3 command line, or None."""
    for cand in (shutil.which('openssl'), '/opt/homebrew/opt/openssl@3/bin/openssl', '/usr/local/opt/openssl@3/bin/openssl'):
        if cand and os.path.exists(cand):
            if subprocess.run([cand, 'version'], capture_output=True, text=True).stdout.startswith('OpenSSL 3'):
                return cand
    return None


def tls_conn(port, cert, alpn):
    """A TLS 1.3 connection to the fixture that offers the ALPN protocols alpn (None: no ALPN)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(str(cert))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    if alpn:
        ctx.set_alpn_protocols(alpn)
    return ctx.wrap_socket(socket.create_connection(('127.0.0.1', port), timeout=5), server_hostname='localhost')


def http1_over(s, request):
    """The whole HTTP/1.1 reply to request on TLS socket s (the request says Connection: close)."""
    s.sendall(request)
    reply = b''
    while True:
        try:
            part = s.recv(65536)
        except (ssl.SSLEOFError, ConnectionResetError):
            break
        if not part:
            break
        reply += part
    s.close()
    return reply


def check_tls(exe, out, files):
    """ServeTLS offers h2 and then http/1.1: a client that offers h2 gets HTTP/2, the others
    HTTP/1.1 on the same port, and the cleartext ways into HTTP/2 do not apply over TLS."""
    openssl = openssl3()
    if not openssl or not PY_TLS13:
        if os.environ.get('CI'):
            raise AssertionError('h2 over TLS needs an OpenSSL 3 command line and Python ssl with TLS 1.3')
        print('SKIP h2 over TLS: no OpenSSL 3 command line, or Python ssl without TLS 1.3 (%s)' % ssl.OPENSSL_VERSION)
        return
    cert, key = out / 'tls.pem', out / 'tls.key'
    subprocess.run([openssl, 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256', '-keyout', str(key),
                    '-out', str(cert), '-days', '30', '-nodes', '-subj', '/CN=localhost',
                    '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], check=True, capture_output=True)
    srv = Server(exe, out / 'h2tls.log', TLS_CERT=str(cert), TLS_KEY=str(key), FILES_DIR=str(files), TIN_MAX_BODY='2000000')
    try:
        # Raw frames over TLS: ALPN chose h2, then multiplexed streams and a body past the
        # initial window, as over TCP.
        s = tls_conn(srv.port, cert, ['h2', 'http/1.1'])
        assert s.selected_alpn_protocol() == 'h2', s.selected_alpn_protocol()
        c = w.Conn.__new__(w.Conn)
        c.sock, c.buf, c.dec, c.port = s, b'', w.Decoder(), srv.port
        c.send(w.PREFACE + w.settings())
        t = time.monotonic()
        for i in range(4):
            c.request(1 + 2 * i, 'GET', '/wait?ms=300')
        c.request(9, 'GET', '/')
        c.request(11, 'GET', '/big?n=200000')
        r = c.responses([9, 11])
        fast = time.monotonic() - t
        assert r[9]['body'] == b'hello from anvil over HTTP/2.0\n', r[9]
        assert r[11]['body'] == pattern(200000), len(r[11]['body'])
        r = c.responses([1, 3, 5, 7])
        assert all(x['body'] == b'waited 300' for x in r.values()), r
        assert fast < 0.25, fast
        c.close()
        # The same port without h2: HTTP/1.1 when ALPN offers only http/1.1 and when there is none.
        for alpn in (['http/1.1'], None):
            s = tls_conn(srv.port, cert, alpn)
            assert s.selected_alpn_protocol() == (alpn[0] if alpn else None), s.selected_alpn_protocol()
            reply = http1_over(s, b'GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n')
            assert reply.startswith(b'HTTP/1.1 200 OK\r\n') and reply.endswith(b'hello from anvil over HTTP/1.1\n'), reply
        # h2c is for cleartext (RFC 9113 3.2, 3.3): over a TLS connection that agreed on HTTP/1.1,
        # Upgrade: h2c is ignored and the client preface is a malformed request line.
        s = tls_conn(srv.port, cert, ['http/1.1'])
        reply = http1_over(s, b'GET / HTTP/1.1\r\nHost: x\r\nConnection: Upgrade, HTTP2-Settings, close\r\n'
                              b'Upgrade: h2c\r\nHTTP2-Settings: AAMAAABkAARAAAAA\r\n\r\n')
        assert reply.startswith(b'HTTP/1.1 200 OK\r\n') and reply.endswith(b'over HTTP/1.1\n'), reply
        s = tls_conn(srv.port, cert, ['http/1.1'])
        reply = http1_over(s, w.PREFACE + w.settings())
        assert reply.startswith(b'HTTP/1.1 400 '), reply
        print('PASS h2 over TLS: ALPN chose h2 for a client offering it (multiplexed waits, a 200 KB body), '
              'HTTP/1.1 for http/1.1 and for no ALPN on the same port; Upgrade: h2c and the preface are cleartext only')
        check_h2spec(srv.port, out, tls=True)
        check_go_client(srv.port, out, ca=cert)
        assert srv.p.poll() is None, 'the server died'
    finally:
        srv.stop()


def main():
    out = ROOT / 'bin/ci/h2'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'h2'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/h2.tin'], cwd=ROOT,
                   env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    files = out / 'files'
    files.mkdir(exist_ok=True)
    (files / 'big').write_bytes(b''.join(pattern(1 << 20, i << 20) for i in range(3)) + b'tail')
    srv = Server(exe, out / 'h2.log', FILES_DIR=str(files), TIN_WRITE_TIMEOUT_MS='1500', TIN_MAX_BODY='2000000')
    try:
        check_settings(srv.port)
        check_h2spec(srv.port, out)
        check_go_client(srv.port, out)
        check_hpack_table(srv.port)
        check_huffman(srv.port)
        check_multiplexing(srv.port)
        check_flow_control(srv.port)
        check_cancels(srv)
        check_write_timeout(srv)
        check_limits(srv.port)
        check_responses(srv.port, files)
        check_header_table_size(srv.port)
        check_upgrade(srv.port)
        check_continue(srv.port)
        check_http1(srv.port)
        check_rapid_reset(srv)
        check_memory(srv)
        assert srv.p.poll() is None, 'the server died'
    finally:
        srv.stop()
    check_drain(exe, out)
    check_read_while_writing(exe, out)
    check_tls(exe, out, files)
    check_grpc(out)


if __name__ == '__main__':
    main()
