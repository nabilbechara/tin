#!/usr/bin/env python3
"""PostgreSQL protocol 3.0: authentication, typed binary bindings, transaction and
pool recovery, request/operation deadlines, cache eviction and 1000 concurrent inserts.
With POSTGRES_ADDR/USER/PASSWORD/DATABASE, run the shared checks against a real server.
The fake peer deliberately fragments, coalesces and sends malformed protocol frames.
Only Python's standard library is required.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
import random
from pathlib import Path
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


def i16(n):
    return struct.pack('>H', n)


def i32(n):
    return struct.pack('>I', n)


def cstr(s):
    return s.encode() + b'\0' if isinstance(s, str) else s+b'\0'


def frame(kind, payload=b''):
    return kind.encode()+i32(len(payload)+4)+payload


def mac(key, msg):
    return hmac.new(key, msg, 'sha256').digest()


def xor(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


class Reader:
    def __init__(self, data):
        self.data, self.at = data, 0

    def take(self, n):
        assert 0 <= n <= len(self.data)-self.at, 'truncated client frame'
        out = self.data[self.at:self.at+n]
        self.at += n
        return out

    def number(self, n):
        return int.from_bytes(self.take(n), 'big')

    def string(self):
        end = self.data.index(b'\0', self.at)
        return self.take(end-self.at+1)[:-1]

    def done(self):
        assert self.at == len(self.data), 'trailing client frame bytes'


class Fake:
    def __init__(self):
        self.users, self.next_id = {}, 1
        self.lock = threading.Lock()
        self.conns, self.errors = [], []
        self.parses = self.closes = self.auths = 0
        self.max_statements = 0
        fake = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                with fake.lock:
                    fake.conns.append(self.request)
                try:
                    Session(fake, self.request).run()
                except (OSError, ConnectionError):
                    pass # Deadlines, shutdown, bad passwords and hostile-server probes.
                except Exception as exc:
                    with fake.lock:
                        fake.errors.append(repr(exc))

        class TCP(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True
            # The default listen backlog is 5: a burst of 20 clients opening connections overflows
            # it, and macOS answers the overflow with a reset instead of making the client retry.
            request_queue_size = 256

        self.srv = TCP(('127.0.0.1', 0), Handler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def drop_all(self):
        with self.lock:
            conns = list(self.conns)
        for c in conns:
            try:
                c.shutdown(socket.SHUT_RDWR)
                c.close()
            except OSError:
                pass

    def close(self):
        self.drop_all()
        self.srv.shutdown()
        self.srv.server_close()


class Session:
    def __init__(self, fake, sock):
        self.f, self.s = fake, sock
        self.statements = {}
        self.status = b'I'
        self.staged = {}
        self.discard = False
        self.sql, self.vals, self.oids = b'', [], []
        self.user = b''
        self.s.settimeout(10)
        # PostgreSQL disables Nagle: separate small protocol replies must not wait
        # for Linux delayed ACKs (otherwise each Parse/Sync costs ~40ms).
        self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def receive(self, n):
        out = b''
        while len(out) < n:
            b = self.s.recv(n-len(out))
            if not b:
                raise ConnectionError('closed')
            out += b
        return out

    def message(self):
        kind = self.receive(1)
        n = int.from_bytes(self.receive(4), 'big')
        assert 4 <= n <= 16777216
        return kind, Reader(self.receive(n-4))

    def send(self, kind, payload=b''):
        self.s.sendall(frame(kind, payload))

    def error(self, state, message, detail=None):
        fields = b'SERROR\0VERROR\0C'+cstr(state)+b'M'+cstr(message)
        if detail:
            fields += b'D'+cstr(detail)
        self.send('E', fields+b'\0')
        if self.status == b'T':
            self.status = b'E'

    def ready(self):
        self.send('Z', self.status)

    def auth(self):
        n = int.from_bytes(self.receive(4), 'big')
        r = Reader(self.receive(n-4))
        assert r.number(4) == 196608, 'protocol must be 3.0, no SSL negotiation'
        opts = {}
        while True:
            key = r.string()
            if not key:
                break
            opts[key] = r.string()
        r.done()
        self.user = opts[b'user']
        assert opts[b'database'] == b'tin' and opts[b'client_encoding'] == b'UTF8'
        if self.user == b'tls':
            self.error('28000', 'no pg_hba.conf entry for host, no encryption')
            return False
        if self.user == b'premature':
            self.ready(); return False
        if self.user == b'unknown':
            self.send('R', i32(7))
            return False
        password = b'tinpass'
        if self.user == b'unicode':
            password = 'IX é 각'.encode() # input has soft hyphen, decomposed accents/Hangul
        elif self.user == b'prohibited':
            password = '\x07ª'.encode() # PostgreSQL falls back to the original bytes
        if self.user in (b'md5', b'clear'):
            salt = b'\x00\xff\x80x'
            self.send('R', i32(5 if self.user == b'md5' else 3)+(salt if self.user == b'md5' else b''))
            kind, r = self.message()
            assert kind == b'p'
            got = r.string(); r.done()
            want = password
            if self.user == b'md5':
                inner = hashlib.md5(password+self.user).hexdigest().encode()
                want = b'md5'+hashlib.md5(inner+salt).hexdigest().encode()
            if got != want:
                self.error('28P01', 'password authentication failed'); return False
        else:
            # Split the tag/length across TCP reads, testing the client's framing.
            msg = frame('R', i32(10)+b'SCRAM-SHA-256\0\0')
            self.s.sendall(msg[:2]); time.sleep(.002); self.s.sendall(msg[2:])
            kind, r = self.message()
            assert kind == b'p' and r.string() == b'SCRAM-SHA-256'
            first = r.take(r.number(4)); r.done()
            assert first.startswith(b'n,,n=,r=')
            bare = first[3:]
            nonce = bare.split(b'r=', 1)[1]
            server_nonce = nonce+b'SERVERnonce'
            if self.user == b'badnonce':
                server_nonce = b'WRONGnonce'
            salt = b'tin-test-salt\x00\xff'
            server_first = b'r='+server_nonce+b',s='+base64.b64encode(salt)+b',i=4096'
            if self.user == b'duplicate':
                server_first += b',r=duplicate'
            if self.user == b'slowauth':
                server_first = server_first.replace(b'i=4096', b'i=1000000')
            if self.user == b'badcount':
                server_first = server_first.replace(b'i=4096', b'i=1000001')
            self.send('R', i32(11)+server_first)
            kind, r = self.message()
            assert kind == b'p'
            final = r.take(len(r.data)); r.done()
            without_proof, proof = final.rsplit(b',p=', 1)
            assert without_proof == b'c=biws,r='+server_nonce
            auth_message = bare+b','+server_first+b','+without_proof
            salted = hashlib.pbkdf2_hmac('sha256', password, salt, 4096)
            client_key = mac(salted, b'Client Key')
            want = xor(client_key, mac(hashlib.sha256(client_key).digest(), auth_message))
            if not hmac.compare_digest(want, base64.b64decode(proof)):
                self.error('28P01', 'password authentication failed'); return False
            verifier = mac(mac(salted, b'Server Key'), auth_message)
            if self.user == b'badverifier':
                verifier = bytes(32)
            self.send('R', i32(12)+b'v='+base64.b64encode(verifier))
        with self.f.lock:
            self.f.auths += 1
        # Coalesce authentication and metadata; unknown Error/Notice fields are legal.
        self.s.sendall(frame('R', i32(0))+frame('S', b'server_version\x0015.0\0')+
                       frame('K', i32(1234)+i32(5678))+
                       frame('N', b'SNOTICE\0C00000\0Mhello\0Ddetail\0Xunknown\0\0')+frame('Z', b'I'))
        return True

    def columns(self):
        if self.sql.startswith(b'SELECT 1 /'):
            return [('value', 20)]
        if self.sql.startswith(b'INSERT'):
            return [('id', 20)]
        if self.sql.startswith(b'SELECT id, name'):
            return [('id', 20), ('name', 25)]
        if self.sql == b'SELECT COUNT(*) FROM users':
            return [('count', 20)]
        if self.sql.startswith(b'SELECT pg_sleep'):
            return [('pg_sleep', 25)]
        if self.sql.startswith(b'SELECT $1 AS i,'):
            return list(zip(['i', 'f', 's', 'b', 'bytes'], self.oids))
        if self.sql.startswith(b'SELECT -123::'):
            return list(zip(['small','medium','large','real','double','yes','no','empty','num','s','day','ts','tz','uid','j','jb'], [21,23,20,700,701,16,16,25,1700,1043,1082,1114,1184,2950,114,3802]))
        if self.sql.startswith(b'SELECT $1 AS value') or self.sql.startswith(b'SELECT $1 AS f'):
            return [('value', self.oids[0])]
        return []

    def describe(self, cols):
        data = i16(len(cols))
        for name, oid in cols:
            data += cstr(name)+i32(0)+i16(0)+i32(oid)+i16(0xffff)+i32(0xffffffff)+i16(0)
        return frame('T', data)

    def rows(self, cols, rows, tag, described=False):
        data = b'' if described else self.describe(cols)
        for row in rows:
            payload = i16(len(row))
            for v in row:
                if v is None:
                    payload += i32(0xffffffff)
                else:
                    v = str(v).encode() if not isinstance(v, bytes) else v
                    payload += i32(len(v))+v
            data += frame('D', payload)
        self.s.sendall(data+frame('C', cstr(tag)))

    def execute(self, described=False):
        sql, vals = self.sql, self.vals
        if self.status == b'E' and sql not in (b'ROLLBACK', b'COMMIT'):
            self.error('25P02', 'current transaction is aborted'); return
        if sql == b'BEGIN':
            assert self.status == b'I'
            self.status = b'T'; self.send('C', b'BEGIN\0'); return
        if sql in (b'COMMIT', b'ROLLBACK'):
            if sql == b'COMMIT' and self.status == b'T':
                with self.f.lock:
                    self.f.users.update(self.staged)
            self.staged.clear(); self.status = b'I'; self.send('C', cstr(sql)); return
        if sql.startswith(b'CREATE TABLE'):
            self.send('C', b'CREATE TABLE\0'); return
        if b'FROM nope' in sql:
            self.error('42P01', 'relation "nope" does not exist', 'test detail'); return
        if sql.startswith(b'SELECT 1 /'):
            if vals[0] == 0:
                self.error('22012', 'division by zero')
            else:
                self.rows(self.columns(), [[1 // vals[0]]], 'SELECT 1', described)
            return
        if sql.startswith(b'UPDATE users'):
            self.send('C', b'UPDATE 0\0'); return
        if sql.startswith(b'INSERT'):
            with self.f.lock:
                uid = self.f.next_id; self.f.next_id += 1
                if self.status == b'T':
                    self.staged[uid] = vals[0]
                else:
                    self.f.users[uid] = vals[0]
            self.rows(self.columns(), [[uid]], 'INSERT 0 1', described); return
        if sql.startswith(b'SELECT id, name'):
            with self.f.lock:
                name = self.staged.get(vals[0], self.f.users.get(vals[0]))
            self.rows(self.columns(), [] if name is None else [[vals[0], name]], 'SELECT 0' if name is None else 'SELECT 1', described); return
        if sql == b'SELECT COUNT(*) FROM users':
            with self.f.lock:
                count = len(self.f.users)+len(self.staged)
            self.rows(self.columns(), [[count]], 'SELECT 1', described); return
        if sql.startswith(b'SELECT pg_sleep'):
            time.sleep(vals[0]); self.rows(self.columns(), [[b'']], 'SELECT 1', described); return
        if sql.startswith(b'SELECT $1 AS i,'):
            values = [vals[0], vals[1], vals[2], 't' if vals[3] else 'f', b'\\x'+vals[4].hex().encode()]
            self.rows(self.columns(), [values], 'SELECT 1', described); return
        if sql.startswith(b'SELECT -123::'):
            values = [-123,-123456,9223372036854775807,1.5,-2.25,'t','f',None,'12.345','x','2000-01-02','2000-01-02 03:04:05','2000-01-02 03:04:05+00','00000000-0000-0000-0000-000000000001','{"x":1}','{"x": 1}']
            self.rows(self.columns(), [values], 'SELECT 1', described); return
        if sql.startswith(b'SELECT $1 AS value') or sql.startswith(b'SELECT $1 AS f'):
            value = vals[0]
            if value == float('inf'):
                value = 'Infinity'
            self.rows(self.columns(), [[value]], 'SELECT 1', described); return
        if sql == b'SELECT 1 AS first; SELECT 2 AS second':
            self.rows([('first', 23)], [[1]], 'SELECT 1')
            self.rows([('second', 23)], [[2]], 'SELECT 1'); return
        if sql == b'SELECT 1':
            self.rows([('?column?', 23)], [[1]], 'SELECT 1', described); return
        raise AssertionError('unhandled SQL: %r' % sql)

    def run(self):
        if not self.auth():
            return
        while True:
            kind, r = self.message()
            if self.discard and kind != b'S':
                continue
            if kind == b'Q':
                self.sql, self.vals, self.oids = r.string(), [], []
                r.done()
                if self.user == b'malformed':
                    self.s.sendall(b'T'+i32(3)); return
                if self.user == b'truncated':
                    self.send('T', i16(1)+b'unterminated-name-with-no-zero'); self.ready(); continue
                if self.user == b'oversized':
                    self.s.sendall(b'D'+i32(0x80000000)); return
                if self.user == b'badrow':
                    self.s.sendall(self.describe([('id',20)])); self.send('D', i16(1)+i32(0xfffffffe)); self.ready(); continue
                if self.user == b'badstatus':
                    self.execute(); self.send('Z', b'x'); continue
                if self.user == b'trickle':
                    for _ in range(12):
                        self.send('N', b'SNOTICE\0C00000\0Mstill waiting\0\0'); time.sleep(.06)
                    self.execute(); self.ready(); continue
                self.execute(); self.ready()
            elif kind == b'P':
                name, sql = r.string(), r.string()
                oids = [r.number(4) for _ in range(r.number(2))]; r.done()
                assert name and name not in self.statements
                if b'FROM nope' in sql or self.status == b'E':
                    self.error('42P01' if self.status != b'E' else '25P02', 'prepare failed')
                    self.discard = True; continue
                self.statements[name] = (sql, oids)
                with self.f.lock:
                    self.f.parses += 1
                    self.f.max_statements = max(self.f.max_statements, len(self.statements))
                assert len(self.statements) <= 256
                self.send('1')
            elif kind == b'B':
                assert r.string() == b''
                self.sql, self.oids = self.statements[r.string()]
                fmts = [r.number(2) for _ in range(r.number(2))]
                assert fmts == [1], 'parameters must use binary format'
                count = r.number(2); assert count == len(self.oids)
                self.vals = []
                for oid in self.oids:
                    data = r.take(r.number(4))
                    if oid == 20:
                        assert len(data) == 8; value = struct.unpack('>q', data)[0]
                    elif oid == 701:
                        assert len(data) == 8; value = struct.unpack('>d', data)[0]
                    elif oid == 16:
                        assert data in (b'\0', b'\1'); value = data == b'\1'
                    else:
                        assert oid in (25, 17); value = data
                    self.vals.append(value)
                assert r.number(2) == 0 # request text results
                r.done()
                if any(oid == 25 and b'\0' in v for oid, v in zip(self.oids, self.vals)):
                    self.error('22021', 'invalid byte sequence for encoding UTF8'); self.discard = True
                else:
                    self.send('2')
            elif kind == b'D':
                assert r.take(1) == b'P' and r.string() == b''; r.done()
                cols = self.columns()
                if cols:
                    self.s.sendall(self.describe(cols))
                else:
                    self.send('n')
            elif kind == b'E':
                assert r.string() == b'' and r.number(4) == 0; r.done()
                self.execute(described=True)
            elif kind == b'C':
                assert r.take(1) == b'S'
                del self.statements[r.string()]; r.done()
                with self.f.lock:
                    self.f.closes += 1
                self.send('3')
            elif kind == b'S':
                r.done(); self.discard = False; self.ready()
            elif kind == b'X':
                return
            else:
                raise AssertionError('unexpected client message: %r' % kind)


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
    def __init__(self, exe, env, cores=1):
        self.port = free_port()
        full = dict(os.environ, PORT=str(self.port), TIN_CORES=str(cores), POSTGRES_POOL='4', TIN_DEADLINE_MS='1500')
        full.update(env)
        self.log = open(exe.parent/'server.log', 'ab')
        self.p = subprocess.Popen([str(exe)], env=full, stdout=self.log, stderr=self.log)
        for _ in range(100):
            if self.p.poll() is not None:
                raise RuntimeError('PostgreSQL test service exited; see server.log')
            try:
                socket.create_connection(('127.0.0.1', self.port), timeout=.1).close()
                return
            except OSError:
                time.sleep(.05)
        self.stop()
        raise RuntimeError('PostgreSQL test service did not start')

    def get(self, path):
        start = time.monotonic()
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d%s' % (self.port, path), timeout=10) as r:
                code, body = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, body = e.code, e.read()
        return code, body, time.monotonic()-start

    def stop(self):
        self.p.terminate()
        try:
            self.p.wait(timeout=10)
        finally:
            self.log.close()


def expect(srv, path, code=200, body=None, contains=None):
    got, data, dt = srv.get(path)
    assert got == code, (path, got, data)
    if body is not None:
        assert data == body, (path, data, body)
    if contains is not None:
        assert contains in data, (path, data, contains)
    return data, dt


def shared(exe, env, fake):
    srv = Server(exe, env)
    try:
        expect(srv, '/setup', body=b'ok')
        hostile = 'o\'brien "x"; DROP TABLE users'
        uid, _ = expect(srv, '/add?name='+urllib.request.quote(hostile))
        data, _ = expect(srv, '/user?id='+uid.decode())
        assert json.loads(data) == {'id': int(uid), 'name': hostile}
        expect(srv, '/user?id=999999999', 404)
        data, _ = expect(srv, '/echo?name='+urllib.request.quote(hostile))
        assert json.loads(data) == ['-9223372036854775808','1.25',hostile,'1','\\x00ff80'], data
        data, _ = expect(srv, '/echo?bool=false&bytes=empty')
        assert json.loads(data) == ['-9223372036854775808','1.25','','0','\\x'], data
        data, _ = expect(srv, '/values')
        assert json.loads(data) == ['-123','-123456','9223372036854775807','1.5','-2.25','1','0','','12.345','x','2000-01-02','2000-01-02 03:04:05','2000-01-02 03:04:05+00','00000000-0000-0000-0000-000000000001','{"x":1}','{"x": 1}','true','13','-1'], data
        expect(srv, '/multi', body=b'first 1 1')
        expect(srv, '/special', body=b'+Inf')
        expect(srv, '/affected', body=b'0')
        expect(srv, '/signature', body=b'123 hello')
        auths = fake.auths if fake else None
        expect(srv, '/error', 502, contains=b'postgres: ERROR 42P01: relation "nope" does not exist')
        expect(srv, '/count')
        expect(srv, '/prepare-error', 502, contains=b'42P01')
        expect(srv, '/execute-error?n=0', 502, contains=b'22012')
        expect(srv, '/execute-error?n=1', body=b'1')
        expect(srv, '/add?name=bad%00name', 502, contains=b'22021')
        expect(srv, '/add?name=after-bind-error')
        if fake:
            assert fake.auths == auths, 'SQL errors must reuse the synchronized connection'
        before, _ = expect(srv, '/count')
        expect(srv, '/copy', body=b'true')
        for _ in range(8):
            expect(srv, '/abandon', body=b'ok')
        after, _ = expect(srv, '/count'); assert after == before
        expect(srv, '/tx?mode=rollback&name=rolled-back', body=b'ok')
        after, _ = expect(srv, '/count'); assert after == before
        expect(srv, '/tx?mode=abort&name=aborted', body=b'true true true true')
        after, _ = expect(srv, '/count'); assert after == before
        expect(srv, '/tx?mode=commit&name=committed', body=b'ok')
        after, _ = expect(srv, '/count'); assert int(after) == int(before)+1
        expect(srv, '/cache', body=b'ok')
        if fake:
            assert fake.closes >= 256 and fake.max_statements == 256
        print('bindings, OIDs, RETURNING, SQL error recovery, transactions and cache: passed', flush=True)
        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: srv.get('/sleep?ms=350'), range(8)))
        elapsed = time.monotonic()-start
        assert all(r[0] == 200 for r in results), results
        assert .60 < elapsed < 1.35, ('pool of four on one core', elapsed)
        print('8 x 350ms with four pooled connections, one core: %.2fs' % elapsed, flush=True)
        _, dt = expect(srv, '/sleep?ms=3000', 502, body=b'deadline exceeded')
        assert 1.2 < dt < 2.1, dt
        expect(srv, '/count')
        if fake:
            fake.drop_all(); time.sleep(.1)
            for _ in range(3):
                expect(srv, '/count')
        print('request deadline, dropped connection, idle reconnect: passed', flush=True)
    finally:
        srv.stop()
    srv = Server(exe, dict(env, POSTGRES_TIMEOUT_MS='120', TIN_DEADLINE_MS='2000'))
    try:
        _, dt = expect(srv, '/sleep?ms=1000', 502, body=b'postgres: timed out')
        assert dt < .6, dt
        expect(srv, '/count')
        # A queued request must also honor Options.Timeout.
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: srv.get('/sleep?ms=1000'), range(8)))
        assert all(r[0] == 502 and r[2] < .6 for r in results), results
    finally:
        srv.stop()
    srv = Server(exe, env, cores=2)
    try:
        before, _ = expect(srv, '/count')
        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(lambda i: srv.get('/add?name=u%d' % i), range(1000)))
        after, _ = expect(srv, '/count')
        assert all(r[0] == 200 for r in results), [r for r in results if r[0] != 200][:3]
        assert int(after)-int(before) == 1000, (before, after)
        print('1000 inserts from 20 clients, two cores: passed', flush=True)
    finally:
        srv.stop()


def main():
    out = ROOT/'bin/ci/postgres'; out.mkdir(parents=True, exist_ok=True)
    source = (ROOT/'examples/postgres.tin').read_text()
    source = source.replace('\tw.Status(404)\n\tw.Text("no route', '\tif extra(q, mut w) { return }\n\tw.Status(404)\n\tw.Text("no route')
    (out/'service.tin').write_text(source)
    exe = out/'service'
    subprocess.run([str(ROOT/'bin/tinc'), '-o', str(exe), str(out/'service.tin'), 'tests/fixtures/postgres_routes.tin'], cwd=ROOT, check=True, env=dict(os.environ, TIN_ROOT=str(ROOT)))
    real = os.environ.get('POSTGRES_ADDR')
    fake = None if real else Fake()
    env = {} if real else {'POSTGRES_ADDR': '127.0.0.1:%d' % fake.port, 'POSTGRES_USER': 'tin', 'POSTGRES_PASSWORD': 'tinpass', 'POSTGRES_DATABASE': 'tin'}
    try:
        shared(exe, env, fake)
        if fake:
            cases = [('md5','tinpass',200,None),('clear','tinpass',200,None),('tin','wrong',502,b'28P01'),('unicode','I\u00adX e\u0301 \u1100\u1161\u11a8',200,None),('prohibited','\x07ª',200,None),('unknown','tinpass',502,b'authentication method 7'),('tls','tinpass',502,b'TLS is not supported'),('badnonce','tinpass',502,b'server nonce'),('badverifier','tinpass',502,b'server verifier'),('duplicate','tinpass',502,b'duplicate SCRAM'),('badcount','tinpass',502,b'iteration count'),('malformed','tinpass',502,b'message length'),('truncated','tinpass',502,b'unterminated string'),('oversized','tinpass',502,b'message length'),('badrow','tinpass',502,b'truncated message'),('badstatus','tinpass',502,b'transaction status'),('premature','tinpass',502,b'before authentication')]
            for user, password, code, contains in cases:
                srv = Server(exe, dict(env, POSTGRES_USER=user, POSTGRES_PASSWORD=password))
                try:
                    expect(srv, '/count', code, contains=contains)
                finally:
                    srv.stop()
            srv = Server(exe, dict(env, POSTGRES_PASSWORD='wrong', POSTGRES_POOL='1'))
            try:
                with ThreadPoolExecutor(max_workers=8) as pool:
                    results = list(pool.map(lambda _: srv.get('/count'), range(8)))
                assert all(r[0] == 502 and b'28P01' in r[1] for r in results), results
            finally:
                srv.stop()
            for timeout, deadline, body in [('30','2000',b'postgres: timed out'),('2000','30',b'deadline exceeded')]:
                srv = Server(exe, dict(env, POSTGRES_USER='slowauth', POSTGRES_TIMEOUT_MS=timeout, TIN_DEADLINE_MS=deadline))
                try:
                    _, dt = expect(srv, '/count', 502, body=body)
                    assert dt < .6, dt
                finally:
                    srv.stop()
            srv = Server(exe, dict(env, POSTGRES_USER='trickle', POSTGRES_TIMEOUT_MS='220', TIN_DEADLINE_MS='2000'))
            try:
                _, dt = expect(srv, '/count', 502, body=b'postgres: timed out')
                assert .15 < dt < .6, dt # notices must not restart the operation timeout
            finally:
                srv.stop()
            assert not fake.errors, fake.errors
            print('SCRAM, MD5, cleartext, Unicode, hostile auth/frames, absolute timeout: passed', flush=True)
    finally:
        if fake:
            fake.close()


if __name__ == '__main__':
    main()
