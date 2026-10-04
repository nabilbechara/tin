#!/usr/bin/env python3
"""The mysql client inside anvil: queries with bound values, a per-core pool whose waiters
overlap on one core, deadlines that drop the connection, concurrent inserts, both auth
plugins (caching_sha2_password with the RSA exchange, and an auth switch to
mysql_native_password), wrong passwords, and reconnecting after the server drops idle
connections. Runs against a small MySQL server written here (MYSQL_ADDR=host:port with
MYSQL_USER/MYSQL_PASSWORD/MYSQL_DATABASE uses a real one, for the checks it can do)."""
import hashlib
import os
import random
import re
import socket
import socketserver
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from suite import ROOT

# A throwaway 2048-bit test key: the fake server decrypts the client's RSA-OAEP password.
N = 0xd2bd9337a676f717731fd543518e7cc0fc5bba8aec2f2e138af4d80e8ca7d80c11539e5e65ae4099c13f813c6095f731abf20bd665e5257a3689903ac959cb5fbde59e8303b03524d5cad8a7835d0daf692cf0b2cab70cf8911b17bbc1ac5bef8cc5fe22e288675d03e5e94d1938a3606111397bef3dc809e530adcfca7c9defbf77c7ad2bf87ab4056b0e35b211797faf7127209281158a4c6f1bfe0917376de8264356d1f108a62a07f1c55ce87af26911d724711d8405f0d54e9df8b17af81a260abc5e1da36c12a36beb53efd5223517810670961fd36aca069907f38e8aa4c8051d401e9b4702b8de6f0c8c06432d68fe943d22e2802a01f4632110e901
D = 0x428b8f4daed8790ce41304be35a62739af566dd0c964da895c4315687ebccf697c1d29f087ee1ec30e7535a371a25944cb956a6c808f7ba69c4b130aa5232027b2e8ab8596681157f8d48d56541251ac76ab34b45873b5fa55a3b6fa585d4b4898ecba639ca1d2f5d9b1c35a4fa10561fd34b9b0ab6a985c9b8d240d6dd4acf000f12fd4a5bdbe8798bc7db7b089604f81ec8d4a7f47334ab5c119b9198e5d9522dcac71d961f6447e70d9b19f0b40c6a35dbadbc6a110caac3f4bbe76a56aa1a8a684727a24d1607379a9ff9eb24aaf4b6c634b5e499018b3232e1e99beae08a387641b19345a04691f72e7aa6e87ffcc525c8e0e552092e729c5ea4798805b
PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0r2TN6Z29xdzH9VDUY58
wPxbuorsLy4TivTYDoyn2AwRU55eZa5AmcE/gTxglfcxq/IL1mXlJXo2iZA6yVnL
X73lnoMDsDUk1crYp4NdDa9pLPCyyrcM+JEbF7vBrFvvjMX+IuKIZ10D5elNGTij
YGEROXvvPcgJ5TCtz8p8ne+/d8etK/h6tAVrDjWyEXl/r3EnIJKBFYpMbxv+CRc3
begmQ1bR8QimKgfxxVzoevJpEdckcR2EBfDVTp34sXr4GiYKvF4do2wSo2vrU+/V
IjUXgQZwlh/TasoGmQfzjoqkyAUdQB6bRwK43m8MjAZDLWj+lD0i4oAqAfRjIRDp
AQIDAQAB
-----END PUBLIC KEY-----
"""

PROTO41, SECURE, PLUGIN, LENENC, WITHDB, NOEOF = 0x200, 0x8000, 0x80000, 0x200000, 0x8, 0x1000000
CAPS = 0x1 | 0x4 | WITHDB | PROTO41 | 0x2000 | SECURE | 0x20000 | PLUGIN | LENENC | NOEOF


def lenenc(n):
    if n < 251:
        return bytes([n])
    if n < 65536:
        return b'\xfc' + struct.pack('<H', n)
    return b'\xfe' + struct.pack('<Q', n)


def lstr(b):
    return lenenc(len(b)) + b


def xor(a, b):
    return bytes(x ^ b[i % len(b)] for i, x in enumerate(a))


def sha1(b):
    return hashlib.sha1(b).digest()


def sha256(b):
    return hashlib.sha256(b).digest()


def mgf1(seed, n):
    out = b''
    c = 0
    while len(out) < n:
        out += sha1(seed + struct.pack('>I', c))
        c += 1
    return out[:n]


def oaep_decrypt(c):
    k = (N.bit_length() + 7) // 8
    em = pow(int.from_bytes(c, 'big'), D, N).to_bytes(k, 'big')
    mseed, mdb = em[1:21], em[21:]
    seed = xor(mseed, mgf1(mdb, 20))
    db = xor(mdb, mgf1(seed, k - 21))
    assert em[0] == 0 and db[:20] == sha1(b''), 'bad OAEP'
    i = 20
    while db[i] == 0:
        i += 1
    assert db[i] == 1, 'bad OAEP'
    return db[i + 1:]


def coldef(name, typ, flags=0):
    return (lstr(b'def') + lstr(b'tin') + lstr(b'users') + lstr(b'users') + lstr(name) + lstr(name) +
            b'\x0c' + struct.pack('<HIBHB', 33, 255, typ, flags, 0) + b'\x00\x00')


class Fake:
    """Just enough of MySQL for examples/mysql.tin: a users table in a dict."""

    USERS = {b'tin': (b'tinpass', 'caching_sha2_password'), b'native': (b'nativepass', 'mysql_native_password')}
    PREPARED = {
        b'SELECT id, name FROM users WHERE id = ?': [(b'id', 0x08), (b'name', 0xfd)],
        b'INSERT INTO users (name) VALUES (?)': [],
        b'SELECT SLEEP(?)': [(b'SLEEP(?)', 0x08)],
    }

    def __init__(self):
        self.users = {}
        self.next_id = 1
        self.lock = threading.Lock()
        self.cached = set()
        self.full_auths = 0
        self.fast_auths = 0
        self.switches = 0
        self.key_requests = 0
        self.conns = []
        fake = self

        class H(socketserver.BaseRequestHandler):
            def handle(self):
                fake.conns.append(self.request)
                try:
                    Session(fake, self.request).run()
                except (OSError, ConnectionError, AssertionError, struct.error):
                    pass

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        socketserver.ThreadingTCPServer.request_queue_size = 256  # the default backlog of 5 resets bursts on macOS
        self.srv = socketserver.ThreadingTCPServer(('127.0.0.1', 0), H)
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def drop_all(self):
        for c in self.conns:
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.conns = []


class Session:
    def __init__(self, fake, s):
        self.fake, self.s = fake, s
        self.buf = b''
        self.seq = 0
        self.stmts = {}

    def recv(self):
        while len(self.buf) < 4 or len(self.buf) < 4 + int.from_bytes(self.buf[:3], 'little'):
            d = self.s.recv(65536)
            if not d:
                raise ConnectionError
            self.buf += d
        n = int.from_bytes(self.buf[:3], 'little')
        self.seq = self.buf[3] + 1
        p, self.buf = self.buf[4:4 + n], self.buf[4 + n:]
        return p

    def send(self, payload):
        self.s.sendall(len(payload).to_bytes(3, 'little') + bytes([self.seq & 255]) + payload)
        self.seq += 1

    def ok(self, affected=0, last=0):
        self.send(b'\x00' + lenenc(affected) + lenenc(last) + b'\x02\x00\x00\x00')

    def err(self, code, state, msg):
        self.send(b'\xff' + struct.pack('<H', code) + b'#' + state + msg)

    def end(self):
        self.send(b'\xfe\x00\x00\x02\x00\x00\x00')

    def run(self):
        scramble = os.urandom(20).replace(b'\x00', b'\x01')
        self.send(b'\x0a8.0.0-fake\x00' + struct.pack('<I', 7) + scramble[:8] + b'\x00' +
                  struct.pack('<HBHHB', CAPS & 0xffff, 255, 2, CAPS >> 16, 21) + b'\x00' * 10 +
                  scramble[8:] + b'\x00' + b'caching_sha2_password\x00')
        p = self.recv()
        caps = struct.unpack('<I', p[:4])[0]
        assert caps & NOEOF, 'the client should ask for DEPRECATE_EOF'
        at = 32
        e = p.index(b'\x00', at)
        user = p[at:e]
        at = e + 1
        n = p[at]
        auth = p[at + 1:at + 1 + n]
        if user not in Fake.USERS:
            return self.err(1045, b'28000', b"Access denied for user '" + user + b"'")
        pw, plugin = Fake.USERS[user]
        f = self.fake
        if plugin == 'mysql_native_password':
            f.switches += 1
            scramble = os.urandom(20).replace(b'\x00', b'\x01')
            self.send(b'\xfemysql_native_password\x00' + scramble + b'\x00')
            auth = self.recv()
            h1 = sha1(pw)
            good = auth == xor(h1, sha1(scramble + sha1(h1)))
        elif user in f.cached:
            h1 = sha256(pw)
            good = auth == xor(h1, sha256(sha256(h1) + scramble))
            if good:
                f.fast_auths += 1
                self.send(b'\x01\x03')
        else:
            self.send(b'\x01\x04')
            q = self.recv()
            if q == b'\x02':
                f.key_requests += 1
                self.send(b'\x01' + PEM.encode())
                q = self.recv()
            got = xor(oaep_decrypt(q), scramble)
            good = got == pw + b'\x00'
            if good:
                f.full_auths += 1
                f.cached.add(user)
        if not good:
            return self.err(1045, b'28000', b"Access denied for user '" + user + b"'@'localhost' (using password: YES)")
        self.ok()
        while True:
            p = self.recv()
            self.seq = 1
            cmd = p[0]
            if cmd == 0x01:
                return
            if cmd == 0x03:
                self.query(p[1:])
            elif cmd == 0x16:
                self.prepare(p[1:])
            elif cmd == 0x17:
                self.execute(p[1:])
            elif cmd == 0x19:
                self.stmts.pop(struct.unpack('<I', p[1:5])[0], None)
            else:
                self.err(1047, b'08S01', b'Unknown command')

    def query(self, q):
        if q in (b'DO 1', b'BEGIN', b'COMMIT', b'ROLLBACK') or q.startswith(b'CREATE TABLE'):
            return self.ok()
        if q == b'SELECT COUNT(*) FROM users':
            self.send(lenenc(1))
            self.send(coldef(b'COUNT(*)', 0x08))
            with self.fake.lock:
                self.send(lstr(b'%d' % len(self.fake.users)))
            return self.end()
        self.err(1064, b'42000', b'You have an error in your SQL syntax')

    def prepare(self, q):
        if q not in Fake.PREPARED:
            return self.err(1146, b'42S02', b"Table 'tin.nope' doesn't exist")
        sid = len(self.stmts) + 1
        cols = Fake.PREPARED[q]
        self.stmts[sid] = q
        params = q.count(b'?')
        self.send(b'\x00' + struct.pack('<IHHBH', sid, len(cols), params, 0, 0))
        for _ in range(params):
            self.send(coldef(b'?', 0xfd))
        for name, typ in cols:
            self.send(coldef(name, typ))

    def execute(self, p):
        sid = struct.unpack('<I', p[:4])[0]
        q = self.stmts[sid]
        n = q.count(b'?')
        at = 9 + (n + 7) // 8
        assert p[at] == 1
        at += 1
        types = [p[at + 2 * i] for i in range(n)]
        at += 2 * n
        vals = []
        for t in types:
            if t == 0x08:
                vals.append(struct.unpack('<q', p[at:at + 8])[0])
                at += 8
            elif t == 0x05:
                vals.append(struct.unpack('<d', p[at:at + 8])[0])
                at += 8
            elif t == 0x01:
                vals.append(p[at])
                at += 1
            else:
                ln = p[at]
                at += 1
                if ln == 0xfc:
                    ln = struct.unpack('<H', p[at:at + 2])[0]
                    at += 2
                vals.append(p[at:at + ln])
                at += ln
        f = self.fake
        if q.startswith(b'INSERT'):
            with f.lock:
                uid = f.next_id
                f.next_id += 1
                f.users[uid] = vals[0]
            return self.ok(1, uid)
        if q.startswith(b'SELECT SLEEP'):
            time.sleep(vals[0])
            self.send(lenenc(1))
            self.send(coldef(b'SLEEP(?)', 0x08))
            self.send(b'\x00\x00' + struct.pack('<q', 0))
            return self.end()
        self.send(lenenc(2))
        self.send(coldef(b'id', 0x08))
        self.send(coldef(b'name', 0xfd))
        with f.lock:
            name = f.users.get(vals[0])
        if name is not None:
            self.send(b'\x00\x00' + struct.pack('<q', vals[0]) + lstr(name))
        self.end()


def free_port():
    """A free port below the ephemeral ranges (Linux 32768+, macOS 49152+). A port the kernel
    picks for bind(0) is an ephemeral one, which a client connection can take as its source
    port before the server binds it ("cannot bind the address" under load)."""
    for _ in range(500):
        port = random.randint(20000, 30000)
        with socket.socket() as s:
            try:
                s.bind(('127.0.0.1', port))
            except OSError:
                continue
            return port
    raise RuntimeError('no free port below the ephemeral range')


class Server:
    def __init__(self, exe, env, cores):
        self.port = free_port()
        full = dict(os.environ, PORT=str(self.port), TIN_CORES=str(cores), MYSQL_POOL='4', TIN_DEADLINE_MS='1000')
        full.update(env)
        self.p = subprocess.Popen([str(exe)], env=full)
        for _ in range(100):
            try:
                socket.create_connection(('127.0.0.1', self.port), timeout=0.1).close()
                return
            except OSError:
                time.sleep(0.05)

    def get(self, path):
        t0 = time.time()
        try:
            r = urllib.request.urlopen('http://127.0.0.1:%d%s' % (self.port, path), timeout=10)
            code, body = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, body = e.code, e.read()
        return code, body, time.time() - t0

    def stop(self):
        self.p.terminate()
        self.p.wait(timeout=10)


def main():
    out = ROOT / 'bin/ci/mysql'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'mysql'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'examples/mysql.tin'], cwd=ROOT, check=True,
                   env=dict(os.environ, TIN_ROOT=str(ROOT)))
    real = os.environ.get('MYSQL_ADDR')
    fake = None if real else Fake()
    env = {} if real else {'MYSQL_ADDR': '127.0.0.1:%d' % fake.port, 'MYSQL_USER': 'tin',
                           'MYSQL_PASSWORD': 'tinpass', 'MYSQL_DATABASE': 'tin'}
    failures = []

    srv = Server(exe, env, 1)
    try:
        srv.get('/setup')
        name = 'o\'brien "x"; DROP TABLE users'
        code, body, _ = srv.get('/add?name=' + urllib.request.quote(name))
        uid = int(body)
        code, body, _ = srv.get('/user?id=%d' % uid)
        want = ('{"id":%d,"name":"o\'brien \\"x\\"; DROP TABLE users"}' % uid).encode()
        print('bound values: %r' % body)
        if body != want:
            failures.append('user: %r, want %r' % (body, want))
        code, _, _ = srv.get('/user?id=999999999')
        if code != 404:
            failures.append('missing user: %d' % code)
        res = {}

        def sleeper(i):
            res[i] = srv.get('/sleep?ms=300')

        ts = [threading.Thread(target=sleeper, args=(i,)) for i in range(8)]
        t0 = time.time()
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        total = time.time() - t0
        print('8 x 300 ms statements on a pool of 4, one core: %.2f s' % total)
        if any(r[0] != 200 for r in res.values()) or not 0.55 < total < 0.95:
            failures.append('pool: %.2f s %r' % (total, sorted(r[0] for r in res.values())))
        code, body, dt = srv.get('/sleep?ms=3000')
        print('deadline: %d %r in %.2f s' % (code, body, dt))
        if code != 502 or body != b'deadline exceeded' or dt > 1.5:
            failures.append('deadline: %d %r %.2f' % (code, body, dt))
        code, before, _ = srv.get('/count')
        if code != 200:
            failures.append('after the deadline: %d %r' % (code, before))
        if fake:
            fake.drop_all()
            time.sleep(0.1)
            codes = [srv.get('/count')[0] for _ in range(3)]
            print('after the server dropped the connections:', codes)
            if codes != [200, 200, 200]:
                failures.append('no reconnect: %r' % codes)
    finally:
        srv.stop()

    # The load checks that every insert lands, not how fast a shared runner's MySQL is: against a
    # real server a disk flush can hold a few inserts past the 1 s deadline (#133), so it gets
    # 10 s there, and the slowest requests are logged.
    srv = Server(exe, dict(env, TIN_DEADLINE_MS='10000') if real else env, 2)
    try:
        _, before, _ = srv.get('/count')
        errs = []
        slow = []

        def adder(n):
            for i in range(n):
                code, body, dt = srv.get('/add?name=u%d' % i)
                slow.append(dt)
                if code != 200:
                    errs.append(body)

        ts = [threading.Thread(target=adder, args=(50,)) for _ in range(20)]
        t0 = time.time()
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        _, after, _ = srv.get('/count')
        print('1000 inserts from 20 clients on 2 cores: %.2f s, %d errors, count %s -> %s; slowest %s s' %
              (time.time() - t0, len(errs), before, after, ', '.join('%.2f' % x for x in sorted(slow)[-3:])))
        if errs or int(after) - int(before) != 1000:
            failures.append('inserts: %d errors %r, %s -> %s' % (len(errs), errs[:2], before, after))
    finally:
        srv.stop()

    if fake:
        for user, pw, want in (('native', 'nativepass', 200), ('tin', 'wrong', 502)):
            e2 = dict(env, MYSQL_USER=user, MYSQL_PASSWORD=pw)
            srv = Server(exe, e2, 1)
            try:
                code, body, _ = srv.get('/count')
                print('%s/%s: %d %r' % (user, pw, code, body))
                if code != want or (want == 502 and b'Error 1045 (28000)' not in body):
                    failures.append('%s/%s: %d %r' % (user, pw, code, body))
            finally:
                srv.stop()
        print('auth: %d full (RSA, %d key requests), %d fast, %d switches to mysql_native_password' %
              (fake.full_auths, fake.key_requests, fake.fast_auths, fake.switches))
        if fake.full_auths < 1 or fake.key_requests < 1 or fake.fast_auths < 1 or fake.switches < 1:
            failures.append('auth paths not all taken')
    if failures:
        sys.exit('\n'.join(failures))


if __name__ == '__main__':
    main()
