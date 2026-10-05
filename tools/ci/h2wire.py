"""A small HTTP/2 client for anvil's checks (#360): frames, an HPACK decoder (with Huffman) and a
plain HPACK encoder, standard library only. It speaks h2c by prior knowledge or by Upgrade."""
import socket
import struct

PREFACE = b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'

DATA, HEADERS, PRIORITY, RST_STREAM, SETTINGS, PUSH_PROMISE, PING, GOAWAY, WINDOW_UPDATE, CONTINUATION = range(10)
END_STREAM, ACK, END_HEADERS, PADDED, PRIO = 1, 1, 4, 8, 32

STATIC = [None] + [tuple(e.split('|', 1)) for e in (
    ':authority|', ':method|GET', ':method|POST', ':path|/', ':path|/index.html', ':scheme|http',
    ':scheme|https', ':status|200', ':status|204', ':status|206', ':status|304', ':status|400',
    ':status|404', ':status|500', 'accept-charset|', 'accept-encoding|gzip, deflate',
    'accept-language|', 'accept-ranges|', 'accept|', 'access-control-allow-origin|', 'age|',
    'allow|', 'authorization|', 'cache-control|', 'content-disposition|', 'content-encoding|',
    'content-language|', 'content-length|', 'content-location|', 'content-range|',
    'content-type|', 'cookie|', 'date|', 'etag|', 'expect|', 'expires|', 'from|', 'host|',
    'if-match|', 'if-modified-since|', 'if-none-match|', 'if-range|', 'if-unmodified-since|',
    'last-modified|', 'link|', 'location|', 'max-forwards|', 'proxy-authenticate|',
    'proxy-authorization|', 'range|', 'referer|', 'refresh|', 'retry-after|', 'server|',
    'set-cookie|', 'strict-transport-security|', 'transfer-encoding|', 'user-agent|', 'vary|',
    'via|', 'www-authenticate|')]

# Code lengths of the HPACK Huffman code (RFC 7541 Appendix B), symbols 0 to 256; canonical.
HUFF_LENS = ('13232828282828282824302828302828282828282828302828282828282828280610101213060811101008110806'
             '06060505050606060606060607081506121013060707070707070707070707070707070707070707070708070813'
             '19131406150506050605060606050707060606050607060505060707070707151114132820222020222222232223'
             '23232323242324242223242323232321222322232324222120222223232123222224212223232121222123222323'
             '20222222232222232626201922232225262626272726242519212627272627242121262628272727202420212221'
             '212322222525242426232627262627272727272827272727272630')


def _huffman_table():
    lens = [int(HUFF_LENS[2 * i:2 * i + 2]) for i in range(257)]
    order = sorted(range(257), key=lambda s: (lens[s], s))
    codes = {}
    code, prev = 0, lens[order[0]]
    for i, s in enumerate(order):
        if i:
            code = (code + 1) << (lens[s] - prev)
            prev = lens[s]
        codes[(lens[s], code)] = s
    return codes


HUFF = _huffman_table()
HUFF_CODES = {sym: (code, n) for (n, code), sym in HUFF.items()}


def huffman_encode(data):
    acc, bits, out = 0, 0, bytearray()
    for b in data:
        code, n = HUFF_CODES[b]
        acc = (acc << n) | code
        bits += n
        while bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 255)
    if bits:
        out.append(((acc << (8 - bits)) | ((1 << (8 - bits)) - 1)) & 255)
    return bytes(out)


def enc_huff(s):
    b = huffman_encode(s.encode('latin-1') if isinstance(s, str) else s)
    return enc_int(128, 7, len(b)) + b


def huffman_decode(data):
    out, code, bits = bytearray(), 0, 0
    for byte in data:
        for k in range(7, -1, -1):
            code = (code << 1) | ((byte >> k) & 1)
            bits += 1
            sym = HUFF.get((bits, code))
            if sym is not None:
                if sym == 256:
                    raise ValueError('EOS in a Huffman string')
                out.append(sym)
                code, bits = 0, 0
    if bits > 7 or code != (1 << bits) - 1:
        raise ValueError('bad Huffman padding')
    return bytes(out)


def enc_int(first, prefix, v):
    mask = (1 << prefix) - 1
    if v < mask:
        return bytes([first | v])
    out = bytearray([first | mask])
    v -= mask
    while v >= 128:
        out.append((v & 127) | 128)
        v >>= 7
    out.append(v)
    return bytes(out)


def enc_str(s):
    b = s.encode() if isinstance(s, str) else s
    return enc_int(0, 7, len(b)) + b


def encode(fields):
    """A header block of literals without indexing and without Huffman coding."""
    out = bytearray()
    for name, value in fields:
        out += b'\x00' + enc_str(name) + enc_str(value)
    return bytes(out)


class Encoder:
    """An encoder that keeps a dynamic table as the server's decoder must: fields already in a
    table are sent as indexes, the others as literals with incremental indexing, so entries are
    added and evicted; resize() starts the next block with a table size update."""

    def __init__(self):
        self.table = []  # newest first
        self.size = 0
        self.max = 4096
        self.updates = []

    def resize(self, n):
        self.updates.append(n)

    def _evict(self, room):
        while self.table and self.size + room > self.max:
            n, v = self.table.pop()
            self.size -= len(n) + len(v) + 32

    def encode(self, fields):
        out = bytearray()
        for n in self.updates:
            out += enc_int(0x20, 5, n)
            self.max = n
            self._evict(0)
        self.updates = []
        for name, value in fields:
            index = name_index = 0
            for i, e in enumerate(STATIC[1:] + self.table, 1):
                if e == (name, value):
                    index = i
                    break
                if e[0] == name and not name_index:
                    name_index = i
            if index:
                out += enc_int(0x80, 7, index)
                continue
            out += enc_int(0x40, 6, name_index) + (b'' if name_index else enc_str(name)) + enc_str(value)
            size = len(name) + len(value) + 32
            self._evict(size)
            if size <= self.max:
                self.table.insert(0, (name, value))
                self.size += size
        return bytes(out)


class Decoder:
    def __init__(self):
        self.table = []  # newest first
        self.size = 0
        self.max = 4096

    def _entry(self, i):
        if i <= 0:
            raise ValueError('index 0')
        if i < len(STATIC):
            return STATIC[i]
        return self.table[i - len(STATIC)]

    def _int(self, data, pos, prefix):
        mask = (1 << prefix) - 1
        v = data[pos] & mask
        pos += 1
        if v < mask:
            return v, pos
        m = 0
        while True:
            b = data[pos]
            pos += 1
            v += (b & 127) << m
            m += 7
            if b < 128:
                return v, pos

    def _str(self, data, pos):
        huff = data[pos] & 128
        n, pos = self._int(data, pos, 7)
        raw = data[pos:pos + n]
        return (huffman_decode(raw) if huff else bytes(raw)).decode('latin-1'), pos + n

    def _add(self, name, value):
        size = len(name) + len(value) + 32
        while self.table and self.size + size > self.max:
            n, v = self.table.pop()
            self.size -= len(n) + len(v) + 32
        if size <= self.max:
            self.table.insert(0, (name, value))
            self.size += size

    def decode(self, data):
        fields, pos = [], 0
        while pos < len(data):
            b = data[pos]
            if b & 128:
                i, pos = self._int(data, pos, 7)
                fields.append(self._entry(i))
            elif b & 64 or b < 32:
                prefix = 6 if b & 64 else 4
                i, pos = self._int(data, pos, prefix)
                name = self._entry(i)[0] if i else None
                if name is None:
                    name, pos = self._str(data, pos)
                value, pos = self._str(data, pos)
                fields.append((name, value))
                if b & 64:
                    self._add(name, value)
            else:
                self.max, pos = self._int(data, pos, 5)
                while self.size > self.max:
                    n, v = self.table.pop()
                    self.size -= len(n) + len(v) + 32
        return fields


def frame(typ, flags, sid, payload=b''):
    return struct.pack('>I', len(payload))[1:] + bytes([typ, flags]) + struct.pack('>I', sid) + payload


def headers_frames(sid, block, end_stream, max_frame=16384):
    """HEADERS, then CONTINUATION frames when the block is longer than one frame."""
    first, rest = block[:max_frame], block[max_frame:]
    out = frame(HEADERS, (END_STREAM if end_stream else 0) | (0 if rest else END_HEADERS), sid, first)
    while rest:
        part, rest = rest[:max_frame], rest[max_frame:]
        out += frame(CONTINUATION, 0 if rest else END_HEADERS, sid, part)
    return out


def settings(*pairs):
    return frame(SETTINGS, 0, 0, b''.join(struct.pack('>HI', k, v) for k, v in pairs))


class Conn:
    """One client connection: frames out, frames in, responses by stream."""

    def __init__(self, port, host='127.0.0.1', timeout=5, preface=True, client_settings=()):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.buf = b''
        self.dec = Decoder()
        self.port = port
        if preface:
            self.send(PREFACE + settings(*client_settings))

    def send(self, data):
        self.sock.sendall(data)

    def close(self):
        self.sock.close()

    def read_frame(self):
        """(type, flags, stream, payload), or None at the end of the connection."""
        while len(self.buf) < 9 or len(self.buf) < 9 + int.from_bytes(self.buf[:3], 'big'):
            try:
                chunk = self.sock.recv(65536)
            except ConnectionResetError:
                chunk = b''
            if not chunk:
                return None
            self.buf += chunk
        n = int.from_bytes(self.buf[:3], 'big')
        typ, flags = self.buf[3], self.buf[4]
        sid = int.from_bytes(self.buf[5:9], 'big') & 0x7fffffff
        payload = self.buf[9:9 + n]
        self.buf = self.buf[9 + n:]
        return typ, flags, sid, payload

    def request(self, sid, method, path, headers=(), body=None, end=True):
        fields = [(':method', method), (':scheme', 'http'), (':path', path),
                  (':authority', f'127.0.0.1:{self.port}')] + list(headers)
        self.send(headers_frames(sid, encode(fields), body is None and end))
        if body is not None:
            self.send(frame(DATA, END_STREAM if end else 0, sid, body))

    def responses(self, want, window_updates=True):
        """Read until the streams in want have ended: {stream: {'headers', 'body', 'trailers',
        'reset'}}, plus the connection's other frames in self.other."""
        out = {sid: {'headers': None, 'body': b'', 'trailers': None, 'reset': None, 'frames': []}
               for sid in want}
        self.other = []
        pending = set(want)
        while pending:
            f = self.read_frame()
            if f is None:
                raise EOFError('connection closed with streams pending: %s' % sorted(pending))
            typ, flags, sid, payload = f
            if typ in (HEADERS, CONTINUATION):
                block = payload
                if typ == HEADERS:
                    if flags & PADDED:
                        block = block[1:len(block) - payload[0]]
                    if flags & PRIO:
                        block = block[5:]
                while not flags & END_HEADERS:
                    f2 = self.read_frame()
                    assert f2 and f2[0] == CONTINUATION and f2[2] == sid, f2
                    block += f2[3]
                    flags |= f2[1] & END_HEADERS
                fields = self.dec.decode(block)
                if sid in out:
                    r = out[sid]
                    r['frames'].append(('HEADERS', flags))
                    if r['headers'] is None:
                        r['headers'] = fields
                    else:
                        r['trailers'] = fields
                    if flags & END_STREAM:
                        pending.discard(sid)
                continue
            if typ == DATA and sid in out:
                r = out[sid]
                r['frames'].append(('DATA', len(payload), flags))
                r['body'] += payload
                if window_updates and payload:
                    self.send(frame(WINDOW_UPDATE, 0, 0, struct.pack('>I', len(payload))) +
                              frame(WINDOW_UPDATE, 0, sid, struct.pack('>I', len(payload))))
                if flags & END_STREAM:
                    pending.discard(sid)
                continue
            if typ == RST_STREAM and sid in out:
                out[sid]['reset'] = int.from_bytes(payload, 'big')
                pending.discard(sid)
                continue
            if typ == GOAWAY:
                self.other.append(f)
                raise EOFError('GOAWAY %d (last stream %d)' % (int.from_bytes(payload[4:8], 'big'),
                                                              int.from_bytes(payload[:4], 'big')))
            self.other.append(f)
        return out


def status(r):
    return dict(r['headers'])[':status']
