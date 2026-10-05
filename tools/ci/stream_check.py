#!/usr/bin/env python3
"""Streaming responses (#350): w.Stream(), Write, Flush, Length, Closed, SendFile.

The fixture (tools/ci/fixtures/stream.tin) streams server-sent events, chunks of a known byte
pattern, Content-Length bodies and files. The client is raw sockets, so the framing is checked:
chunked bodies decode to the pattern; HTTP/1.0 gets a body up to the end of the connection and
no chunks; HEAD gets the head only; the connection is reused after a stream and a pipelined
request waits for it; a short Content-Length body, a panic and a client that stops reading end
the connection without a second response in the middle of the first; a client that goes away is
seen; and the memory of a large streamed response stays flat.
"""
import os
from pathlib import Path
import subprocess
import time

from suite import ROOT
from lifetime_check import eventually, server_ready
import socket
import websocket_check as ws


class Conn:
    def __init__(self, port, timeout=10):
        self.s = socket.create_connection(('127.0.0.1', port), timeout=timeout)
        self.buf = b''

    def send(self, data):
        self.s.sendall(data)

    def fill(self):
        part = self.s.recv(1 << 20)
        if not part:
            raise EOFError
        self.buf += part

    def line(self):
        while b'\r\n' not in self.buf:
            self.fill()
        line, self.buf = self.buf.split(b'\r\n', 1)
        return line

    def head(self):
        """The status and headers of the next response: (status, {lowercase name: value})."""
        status = int(self.line().split()[1])
        headers = {}
        while True:
            h = self.line()
            if not h:
                return status, headers
            k, _, v = h.decode().partition(':')
            headers[k.strip().lower()] = v.strip()

    def exactly(self, n):
        while len(self.buf) < n:
            self.fill()
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def chunked(self, first=None):
        """The chunks of the body up to the last one: a list of bytes."""
        out = []
        while True:
            size = int(self.line(), 16)
            if size == 0:
                assert self.line() == b'', 'trailer'
                return out
            out.append(self.exactly(size))
            assert self.exactly(2) == b'\r\n'

    def rest(self):
        """Everything up to the end of the connection."""
        try:
            while True:
                self.fill()
        except EOFError:
            out, self.buf = self.buf, b''
            return out

    def closed(self, seconds=3):
        """True when the server closes the connection within seconds (nothing more to read)."""
        self.s.settimeout(seconds)
        try:
            return self.s.recv(1) == b''
        except socket.timeout:
            return False
        except ConnectionResetError:
            return True


def get(path, extra=b'', version=b'1.1', method=b'GET'):
    return method + b' ' + path.encode() + b' HTTP/' + version + b'\r\nHost: x\r\n' + extra + b'\r\n'


def pattern(n, start=0):
    return bytes((start + i) % 251 for i in range(n))


class Server:
    def __init__(self, exe, out, cores=2, **env):
        self.port = ws.free_port()
        self.log = open(out / 'stream.log', 'wb')
        self.p = subprocess.Popen([str(exe)], stdout=self.log, stderr=subprocess.STDOUT,
                                  env=dict(os.environ, PORT=str(self.port), TIN_CORES=str(cores), TIN_GRACE='1', **env))
        eventually(lambda: server_ready(self.port, self.p))
        self.path = out / 'stream.log'

    def logged(self):
        return self.path.read_text(errors='replace')

    def rss_kb(self):
        r = subprocess.run(['ps', '-o', 'rss=', '-p', str(self.p.pid)], capture_output=True, text=True)
        return int(r.stdout.strip() or 0)

    def stop(self):
        self.p.terminate()
        try:
            self.p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.p.kill()
            raise
        finally:
            self.log.close()


def check_sse(srv):
    c = Conn(srv.port)
    start = time.monotonic()
    c.send(get('/sse?n=3&ms=250'))
    status, h = c.head()
    assert status == 200 and h['transfer-encoding'] == 'chunked' and 'content-length' not in h, (status, h)
    assert h['content-type'] == 'text/event-stream' and h['cache-control'] == 'no-cache', h
    first = c.chunked_one()
    assert first == b'data: tick 0\n\n', first
    early = time.monotonic() - start
    assert early < 0.2, ('the first event arrives before the stream ends', early)
    rest = c.chunked()
    assert rest == [b'data: tick 1\n\n', b'data: tick 2\n\n'], rest
    assert time.monotonic() - start > 0.45
    # the connection is reused after a stream
    c.send(get('/plain'))
    status, h = c.head()
    assert status == 200 and c.exactly(int(h['content-length'])) == b'plain'
    # a request pipelined behind a stream waits for it, and is answered after it
    c.send(get('/sse?n=2&ms=50') + get('/plain'))
    status, h = c.head()
    assert status == 200 and h['transfer-encoding'] == 'chunked'
    assert c.chunked() == [b'data: tick 0\n\n', b'data: tick 1\n\n']
    status, h = c.head()
    assert c.exactly(int(h['content-length'])) == b'plain'
    # a plain response before it in the same batch is not lost or reordered
    c.send(get('/plain') + get('/sse?n=1&ms=10'))
    status, h = c.head()
    assert c.exactly(int(h['content-length'])) == b'plain'
    status, h = c.head()
    assert h['transfer-encoding'] == 'chunked' and c.chunked() == [b'data: tick 0\n\n']
    c.s.close()
    print('server-sent events: the first event is out at once, then the stream; keep-alive and pipelining work')


def check_chunks(srv):
    c = Conn(srv.port, timeout=30)
    c.send(get('/chunks?n=8&size=100000'))
    status, h = c.head()
    assert status == 200 and h['transfer-encoding'] == 'chunked'
    body = b''.join(c.chunked())
    assert body == pattern(100000) * 8, 'the bytes of eight 100000-byte writes'
    # HEAD: the head, no body, and the connection goes on
    c.send(get('/chunks?n=2', method=b'HEAD'))
    status, h = c.head()
    assert status == 200 and h.get('transfer-encoding') == 'chunked'
    c.send(get('/plain'))
    status, h = c.head()
    assert c.exactly(int(h['content-length'])) == b'plain', 'a response after a HEAD stream'
    # HTTP/1.0: no chunks, the body ends with the connection
    d = Conn(srv.port, timeout=30)
    d.send(get('/chunks?n=3&size=5000', version=b'1.0'))
    status, h = d.head()
    assert status == 200 and 'transfer-encoding' not in h and h.get('connection') == 'close', h
    assert d.rest() == pattern(5000) * 3
    # Text and Flush: the buffered body goes out as chunks, and the last Text with the end
    e = Conn(srv.port)
    e.send(get('/text'))
    status, h = e.head()
    assert e.chunked() == [b'one,', b'two,', b'three']
    # Stream without a write is an ordinary response
    e.send(get('/unsent'))
    status, h = e.head()
    assert status == 201 and e.exactly(int(h['content-length'])) == b'not streamed'
    print('chunks: eight 100000-byte writes in order, HEAD, HTTP/1.0 up to the close, Text and Flush, an unsent stream')


def check_length(srv):
    c = Conn(srv.port, timeout=30)
    c.send(get('/length?n=123457'))
    status, h = c.head()
    assert status == 200 and h['content-length'] == '123457' and 'transfer-encoding' not in h, h
    assert c.exactly(123457) == pattern(123457)
    c.send(get('/plain'))
    status, h = c.head()
    assert c.exactly(int(h['content-length'])) == b'plain', 'keep-alive after a Content-Length stream'
    # a body shorter than its Content-Length cannot be followed by another response
    d = Conn(srv.port)
    d.send(get('/short') + get('/plain'))
    status, h = d.head()
    assert status == 200 and h['content-length'] == '10'
    assert d.rest() == b'12345', 'only the five bytes, then the connection closes'
    # a panic mid-stream: what was sent stays, no error page follows, the connection closes
    p = Conn(srv.port)
    p.send(get('/panic') + get('/plain'))
    status, h = p.head()
    assert status == 200 and h['transfer-encoding'] == 'chunked'
    tail = p.rest()
    assert tail.startswith(b'7\r\npartial\r\n') and b'500' not in tail and b'plain' not in tail, tail
    q = Conn(srv.port)
    q.send(get('/plain'))
    status, h = q.head()
    assert q.exactly(int(h['content-length'])) == b'plain', 'the server goes on'
    print('Content-Length: exact body and keep-alive; a short body and a panic close the connection')


def check_files(srv, files):
    big = 24 << 20
    c = Conn(srv.port, timeout=30)
    c.send(get('/file?name=small'))
    status, h = c.head()
    assert status == 200 and h['content-length'] == '1000' and 'transfer-encoding' not in h, h
    assert c.exactly(1000) == pattern(1000)
    # a range, and keep-alive after a file
    c.send(get('/file?name=small&off=100&n=250'))
    status, h = c.head()
    assert status == 200 and h['content-length'] == '250'
    assert c.exactly(250) == pattern(250, 100)
    c.send(get('/file?name=small&off=1000'))
    status, h = c.head()
    assert status == 200 and h['content-length'] == '0'
    # a file bigger than any buffer: every byte, in order
    c.send(get('/file?name=big'))
    status, h = c.head()
    assert status == 200 and h['content-length'] == str(big)
    got = 0
    while got < big:
        part = c.exactly(min(1 << 20, big - got))
        assert part == pattern(len(part), got), 'the bytes at %d' % got
        got += len(part)
    # HEAD and a missing file
    c.send(get('/file?name=big', method=b'HEAD'))
    status, h = c.head()
    assert status == 200 and h['content-length'] == str(big)
    c.send(get('/file?name=nothing'))
    status, h = c.head()
    assert status == 404
    c.exactly(int(h['content-length']))
    c.send(get('/file?name=small&off=900&n=500'))
    status, h = c.head()
    assert status == 404
    c.exactly(int(h['content-length']))
    # inside a chunked stream
    c.send(get('/filechunk?name=small'))
    status, h = c.head()
    assert h['transfer-encoding'] == 'chunked'
    assert b''.join(c.chunked()) == b'head;' + pattern(1000) + b';tail'
    # HTTP/1.0 gets the file up to the end of the connection
    d = Conn(srv.port, timeout=30)
    d.send(get('/file?name=small', version=b'1.0'))
    status, h = d.head()
    assert status == 200 and h['content-length'] == '1000' and h.get('connection') == 'close'
    assert d.rest() == pattern(1000)
    # a client that does not read a big file: the write times out and the server goes on
    e = Conn(srv.port)
    e.send(get('/file?name=big'))
    e.head()
    eventually(lambda: 'file stopped: anvil: the client stopped reading' in srv.logged(), 8)
    q = Conn(srv.port)
    q.send(get('/plain'))
    status, h = q.head()
    assert q.exactly(int(h['content-length'])) == b'plain'
    print('SendFile: a whole file, a range, %d MiB in order, HEAD, a missing file, inside chunks, HTTP/1.0, a client that stops reading' % (big >> 20))


def check_gone(srv):
    # A client that does not read: the write times out, the stream ends, the server goes on.
    c = Conn(srv.port)
    c.send(get('/endless'))
    c.head()
    eventually(lambda: 'endless stopped:' in srv.logged(), 8)
    assert 'client stopped reading' in srv.logged(), srv.logged()[-300:]
    c.s.close()
    # A client that goes away is seen by Closed.
    w = Conn(srv.port)
    w.send(get('/watch'))
    w.head()
    assert w.chunked_one() == b'watching\n'
    w.s.close()
    eventually(lambda: 'watch saw closed' in srv.logged(), 5)
    q = Conn(srv.port)
    q.send(get('/plain'))
    status, h = q.head()
    assert q.exactly(int(h['content-length'])) == b'plain'
    print('a client that stops reading ends the stream at the write timeout; one that leaves is seen by Closed')


def check_sse_example(out):
    """examples/sse.tin: numbered events, Last-Event-ID resumes the numbering, and a client that
    leaves is noticed between two events."""
    exe = out / 'sse'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'examples/sse.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    port = ws.free_port()
    log = open(out / 'sse.log', 'wb')
    p = subprocess.Popen([str(exe)], stdout=log, stderr=subprocess.STDOUT,
                         env=dict(os.environ, PORT=str(port), TIN_CORES='2', TIN_GRACE='1', TICK_MS='40'))
    try:
        eventually(lambda: server_ready(port, p))
        c = Conn(port)
        c.send(get('/events'))
        status, h = c.head()
        assert status == 200 and h['content-type'] == 'text/event-stream' and h['transfer-encoding'] == 'chunked'
        events = [c.chunked_one() for _ in range(3)]
        assert events == [b'id: %d\nevent: tick\ndata: %d\n\n' % (i, i) for i in (1, 2, 3)], events
        c.s.close()
        d = Conn(port)
        d.send(get('/events', extra=b'Last-Event-ID: 41\r\n'))
        d.head()
        assert d.chunked_one() == b'id: 42\nevent: tick\ndata: 42\n\n'
        d.s.close()
        text = out / 'sse.log'
        eventually(lambda: text.read_text(errors='replace').count('client left after') >= 2, 5)
        page = Conn(port)
        page.send(get('/'))
        status, h = page.head()
        assert status == 200 and b'EventSource' in page.exactly(int(h['content-length']))
    finally:
        p.terminate()
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
            raise
        finally:
            log.close()
    print('examples/sse.tin: numbered events, Last-Event-ID resumes, a client that leaves is noticed')


def check_abort(srv):
    # Abort and a cancelled stream end the connection without the last chunk.
    c = Conn(srv.port)
    c.send(get('/aborted'))
    status, h = c.head()
    assert status == 200
    assert c.chunked_one() == b'half'
    tail = c.rest()
    assert tail == b'', ('no last chunk after Abort', tail)
    print('Abort: the client sees an incomplete response, not a short one')


def check_memory(srv, total_mb):
    # The response is never held: the server's memory stays flat while megabytes go by.
    base = srv.rss_kb()
    c = Conn(srv.port, timeout=60)
    n = total_mb * 16  # 64 KiB chunks
    c.send(get('/chunks?n=%d&size=65536' % n))
    status, h = c.head()
    assert status == 200
    got = 0
    peak = base
    expect = pattern(65536)
    while True:
        size = int(c.line(), 16)
        if size == 0:
            c.line()
            break
        data = c.exactly(size)
        c.exactly(2)
        assert data == expect[:size] if size < 65536 else data == expect
        got += size
        if got % (64 << 20) < 65536:
            peak = max(peak, srv.rss_kb())
    assert got == total_mb << 20, got
    grew = (max(peak, srv.rss_kb()) - base) / 1024
    assert grew < 24, ('RSS grew by %.0f MiB while %d MiB streamed' % (grew, total_mb))
    print('memory: %d MiB streamed in 64 KiB writes, RSS grew by %.0f MiB' % (total_mb, grew))


def chunked_one(self):
    size = int(self.line(), 16)
    assert size > 0
    out = self.exactly(size)
    assert self.exactly(2) == b'\r\n'
    return out


Conn.chunked_one = chunked_one


def main():
    out = ROOT / 'bin/ci/stream'
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'stream'
    subprocess.run([str(ROOT / 'bin/tinc'), '-o', str(exe), 'tools/ci/fixtures/stream.tin'],
                   cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    # The deadline counts from the last write: the 2.4 s stream outlives a 1 s deadline.
    files = out / 'files'
    files.mkdir(exist_ok=True)
    (files / 'small').write_bytes(pattern(1000))
    (files / 'big').write_bytes(b''.join(pattern(1 << 20, i << 20) for i in range(24)))
    srv = Server(exe, out, TIN_DEADLINE_MS='1000', TIN_WRITE_TIMEOUT_MS='600', FILES_DIR=str(files))
    try:
        check_sse(srv)
        check_chunks(srv)
        check_length(srv)
        check_files(srv, files)
        check_gone(srv)
        c = Conn(srv.port)
        c.send(get('/sse?n=8&ms=300'))
        status, h = c.head()
        assert len(c.chunked()) == 8, 'a stream that outlives the request deadline while it keeps writing'
        c.s.close()
        print('the request deadline counts from the last write')
        check_abort(srv)
        check_memory(srv, 1024 if os.uname().sysname == 'Linux' else 256)
        check_sse_example(out)
    finally:
        srv.stop()


if __name__ == '__main__':
    main()
