#!/usr/bin/env python3
"""The redis client inside anvil: correct answers under concurrent load, commands from
concurrent requests batched on one connection, deadlines that leave the connection in
step, reconnecting after the server drops it, and AUTH. Runs against a small RESP server
written here (REDIS_ADDR=host:port uses a real one instead, for the checks it can do)."""
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time
from suite import ROOT


class Fake:
    """Just enough of Redis: strings, INCR, DEL, PEXPIRE, MULTI/EXEC, AUTH, HELLO, SELECT,
    DEBUG SLEEP. It counts reads, so the test can see commands arriving in batches."""

    def __init__(self, password=''):
        self.password = password
        self.data = {}
        self.lock = threading.Lock()
        self.reads = 0
        self.commands = 0
        self.conns = []
        fake = self

        class H(socketserver.BaseRequestHandler):
            def handle(self):
                fake.conns.append(self.request)
                fake.serve(self.request)

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

    def serve(self, s):
        buf = b''
        authed = not self.password
        multi = None
        while True:
            try:
                d = s.recv(65536)
            except OSError:
                return
            if not d:
                return
            self.reads += 1
            buf += d
            out = b''
            while True:
                cmd, buf2 = parse(buf)
                if cmd is None:
                    break
                buf = buf2
                self.commands += 1
                name = cmd[0].upper()
                if name == b'AUTH':
                    if cmd[-1].decode() == self.password:
                        authed = True
                        out += b'+OK\r\n'
                    else:
                        out += b'-WRONGPASS invalid username-password pair\r\n'
                    continue
                if not authed:
                    out += b'-NOAUTH Authentication required.\r\n'
                    continue
                if name == b'MULTI':
                    multi = []
                    out += b'+OK\r\n'
                    continue
                if name == b'EXEC':
                    rs = [self.run(c) for c in (multi or [])]
                    multi = None
                    out += b'*%d\r\n' % len(rs) + b''.join(rs)
                    continue
                if multi is not None:
                    multi.append(cmd)
                    out += b'+QUEUED\r\n'
                    continue
                if name == b'DEBUG':
                    s.sendall(out)
                    out = b''
                    time.sleep(float(cmd[2]))
                    out += b'+OK\r\n'
                    continue
                out += self.run(cmd)
            if out:
                s.sendall(out)

    def run(self, cmd):
        name = cmd[0].upper()
        with self.lock:
            if name == b'PING':
                return b'+PONG\r\n'
            if name in (b'SELECT', b'HELLO'):
                return b'+OK\r\n'
            if name == b'SET':
                self.data[cmd[1]] = cmd[2]
                return b'+OK\r\n'
            if name == b'GET':
                v = self.data.get(cmd[1])
                return b'$-1\r\n' if v is None else b'$%d\r\n%s\r\n' % (len(v), v)
            if name == b'DEL':
                return b':%d\r\n' % (1 if self.data.pop(cmd[1], None) is not None else 0)
            if name == b'INCR':
                v = int(self.data.get(cmd[1], b'0')) + 1
                self.data[cmd[1]] = b'%d' % v
                return b':%d\r\n' % v
            if name == b'PEXPIRE':
                return b':%d\r\n' % (1 if cmd[1] in self.data else 0)
        return b'-ERR unknown command\r\n'


def parse(buf):
    if not buf.startswith(b'*'):
        return None, buf
    e = buf.find(b'\r\n')
    if e < 0:
        return None, buf
    n = int(buf[1:e])
    at = e + 2
    out = []
    for _ in range(n):
        e = buf.find(b'\r\n', at)
        if e < 0:
            return None, buf
        ln = int(buf[at + 1:e])
        at = e + 2
        if len(buf) < at + ln + 2:
            return None, buf
        out.append(buf[at:at + ln])
        at += ln + 2
    return out, buf[at:]


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def get(port, path, timeout=10):
    s = socket.create_connection(('127.0.0.1', port), timeout=timeout)
    t0 = time.time()
    s.sendall(('GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n' % path).encode())
    d = b''
    while True:
        c = s.recv(65536)
        if not c:
            break
        d += c
    s.close()
    head, _, body = d.partition(b'\r\n\r\n')
    return int(head.split(b' ')[1]), body, time.time() - t0


class Server:
    def __init__(self, exe, addr, cores, extra=None):
        self.port = free_port()
        env = dict(os.environ, PORT=str(self.port), TIN_CORES=str(cores), REDIS_ADDR=addr, TIN_DEADLINE_MS='500')
        env.update(extra or {})
        self.p = subprocess.Popen([str(exe)], env=env)
        for _ in range(100):
            try:
                socket.create_connection(('127.0.0.1', self.port), timeout=0.1).close()
                return
            except OSError:
                time.sleep(0.05)

    def stop(self):
        self.p.terminate()
        self.p.wait(timeout=10)


def load(port, key, conns, per):
    errs = []

    def worker():
        s = socket.create_connection(('127.0.0.1', port), timeout=10)
        f = s.makefile('rb')
        for _ in range(per):
            s.sendall(('GET /incr?key=%s HTTP/1.1\r\nHost: x\r\n\r\n' % key).encode())
            line = f.readline()
            n = 0
            while True:
                h = f.readline()
                if h.lower().startswith(b'content-length'):
                    n = int(h.split(b':')[1])
                if h in (b'\r\n', b''):
                    break
            body = f.read(n)
            if not line.startswith(b'HTTP/1.1 200'):
                errs.append(line + body)
        s.close()

    ts = [threading.Thread(target=worker) for _ in range(conns)]
    t0 = time.time()
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return time.time() - t0, errs


def main():
    out = ROOT / 'bin/ci/redis'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'redis'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'examples/redis.tin'], cwd=ROOT, check=True,
                   env=dict(os.environ, TIN_ROOT=str(ROOT)))
    real = os.environ.get('REDIS_ADDR')
    fake = None if real else Fake()
    addr = real or '127.0.0.1:%d' % fake.port
    failures = []
    key = 'tin-check-%d' % os.getpid()

    srv = Server(exe, addr, 2)
    try:
        dt, errs = load(srv.port, key, 40, 100)
        code, body, _ = get(srv.port, '/get?key=' + key)
        print('4000 INCR from 40 connections on 2 cores: %.2f s, %d errors, final %s' % (dt, len(errs), body))
        if errs or body != b'4000':
            failures.append('load: %d errors %r, final %r' % (len(errs), errs[:2], body))
        if fake:
            print('fake server: %d commands in %d reads' % (fake.commands, fake.reads))
            if fake.commands < 2 * fake.reads:
                failures.append('commands were not batched: %d commands, %d reads' % (fake.commands, fake.reads))
        val = 'hello world; DEL x {braces} "quotes"'
        code, body, _ = get(srv.port, '/set?key=%s-v&value=%s' % (key, val.replace(' ', '%20').replace('"', '%22').replace(';', '%3B').replace('{', '%7B').replace('}', '%7D')))
        code, body, _ = get(srv.port, '/get?key=%s-v' % key)
        print('value with spaces round trip: %r' % body)
        if body.decode() != val:
            failures.append('value round trip: %r' % body)
        code, body, _ = get(srv.port, '/get?key=%s-none' % key)
        if code != 404:
            failures.append('missing key: %d %r' % (code, body))
        get(srv.port, '/set?key=%s-t&value=5' % key)
        code, body, _ = get(srv.port, '/twice?key=%s-t' % key)
        print('MULTI/EXEC: %r' % body)
        if code != 200 or b'Int(7)' not in body:
            failures.append('MULTI/EXEC: %d %r' % (code, body))
    finally:
        srv.stop()

    # One core: the queued request shares the paused connection.
    srv = Server(exe, addr, 1)
    try:
        if fake:
            # A 1 s pause with a 500 ms deadline: the request gives up, and the replies that
            # come later still go to the right callers.
            get(srv.port, '/set?key=%s-d&value=0' % key)
            res = {}

            def sleeper():
                res['sleep'] = get(srv.port, '/sleep?ms=1000')

            th = threading.Thread(target=sleeper)
            th.start()
            time.sleep(0.05)
            res['queued'] = get(srv.port, '/incr?key=%s-d' % key)
            th.join()
            print('deadline: sleep -> %d %r in %.2f s; queued incr -> %d %r' %
                  (res['sleep'][0], res['sleep'][1], res['sleep'][2], res['queued'][0], res['queued'][1]))
            for r in (res['sleep'], res['queued']):
                if r[0] != 502 or b'deadline exceeded' not in r[1] or r[2] > 0.9:
                    failures.append('deadline: %r' % (r,))
            time.sleep(0.7)
            seq = [get(srv.port, '/incr?key=%s-d' % key)[1] for _ in range(3)]
            print('after the pause:', seq)
            want_first = 2
            if seq != [b'%d' % want_first, b'%d' % (want_first + 1), b'%d' % (want_first + 2)]:
                failures.append('replies out of step after a deadline: %r' % seq)
            fake.drop_all()
            time.sleep(0.1)
            codes = [get(srv.port, '/incr?key=%s-r' % key)[0] for _ in range(4)]
            print('after the server dropped the connections:', codes)
            if codes != [200, 200, 200, 200]:
                failures.append('no reconnect: %r' % codes)
    finally:
        srv.stop()

    if fake:
        locked = Fake(password='s3cret')
        for pw, want in (('s3cret', 200), ('wrong', 502)):
            srv = Server(exe, '127.0.0.1:%d' % locked.port, 1, {'REDIS_PASSWORD': pw})
            try:
                code, body, _ = get(srv.port, '/incr?key=a')
                print('AUTH %s: %d %r' % (pw, code, body))
                if code != want or (want == 502 and b'WRONGPASS' not in body):
                    failures.append('AUTH %s: %d %r' % (pw, code, body))
            finally:
                srv.stop()
    if failures:
        sys.exit('\n'.join(failures))


if __name__ == '__main__':
    main()
