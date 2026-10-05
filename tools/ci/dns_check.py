#!/usr/bin/env python3
"""Native Linux hosts/search/options/DNS transport and task deadline checks."""
import argparse
import concurrent.futures
import contextlib
import ipaddress
import os
from pathlib import Path
import shutil
import select
import socket
import struct
import subprocess
import tempfile
import threading
import time
from urllib.parse import quote
from suite import ROOT
from task_check import free_port
from lifetime_check import request, response


def question(data):
    if len(data) < 12:
        raise ValueError('short query')
    pos = 12
    labels = []
    while data[pos]:
        n = data[pos]
        labels.append(data[pos+1:pos+1+n].decode('ascii'))
        pos += n+1
    end = pos+5
    return '.'.join(labels).lower(), struct.unpack_from('!H', data, pos+1)[0], end


def name_bytes(name):
    return b''.join(bytes([len(p)])+p.encode() for p in name.split('.'))+b'\0'


def record(owner, kind, data, ttl=60):
    return owner+struct.pack('!HHIH',kind,1,ttl,len(data))+data


class DNS:
    def __init__(self):
        self.port = free_port()
        self.log = []
        self.stop = threading.Event()
        self.sockets = []
        self.threads = []
        self.dropped = threading.Event()
        for host in ('127.0.0.1','127.0.0.2'):
            for kind in (socket.SOCK_DGRAM,socket.SOCK_STREAM):
                s = socket.socket(socket.AF_INET,kind)
                s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                s.bind((host,self.port))
                s.settimeout(.1)
                if kind == socket.SOCK_STREAM:
                    s.listen(16)
                self.sockets.append(s)
                t = threading.Thread(target=self.serve,args=(s,host,kind),daemon=True)
                t.start()
                self.threads.append(t)

    def answer(self, data, host, tcp):
        name, typ, end = question(data)
        self.log.append((host,name,typ,'tcp' if tcp else 'udp'))
        if name.startswith('drop.') or (name == 'retry.test' and host.endswith('.1')):
            self.dropped.set()
            return None
        flags = 0x8180
        answers = []
        success = {'ok.test','canonical.test','trunc.test','short.first.test',
                   'dots.name','many.dots.name.first.test','rotate.test','retry.test','fallback.second.test','wrongid.test','ttl1.test'}
        if name == 'trunc.test' and not tcp:
            flags |= 0x200
        elif name == 'bad.test':
            # A compressed owner referring to itself must be rejected, not hang.
            offset = end
            answers = [record(struct.pack('!H',0xc000|offset),1,b'\x7f\0\0\1')]
        elif name == 'alias.test':
            answers = [record(b'\xc0\x0c',5,name_bytes('canonical.test'))]
        elif name == 'inline.test':
            answers = [record(name_bytes('canonical.test'),1,b'\x7f\0\0\1'),
                       record(b'\xc0\x0c',5,name_bytes('canonical.test'))]
        elif name == 'v6.test':
            if typ == 28:
                answers = [record(b'\xc0\x0c',28,ipaddress.IPv6Address('::1').packed)]
        elif name in success:
            if typ == 1:
                answers = [record(b'\xc0\x0c',1,b'\x7f\0\0\1',1 if name == 'ttl1.test' else 60)]
        else:
            flags = 0x8183
        return data[:2]+struct.pack('!HHHHH',flags,1,len(answers),0,0)+data[12:end]+b''.join(answers)

    def serve(self, s, host, kind):
        while not self.stop.is_set():
            try:
                if kind == socket.SOCK_DGRAM:
                    data,peer = s.recvfrom(65535)
                    answer = self.answer(data,host,False)
                    if answer is not None:
                        if question(data)[0]=='wrongid.test':
                            wrong=bytearray(answer);wrong[1]^=1;s.sendto(wrong,peer)
                        s.sendto(answer,peer)
                else:
                    conn,_ = s.accept()
                    threading.Thread(target=self.tcp,args=(conn,host),daemon=True).start()
            except socket.timeout:
                continue
            except OSError:
                if not self.stop.is_set():
                    raise

    def tcp(self, conn, host):
        def read(n):
            b = b''
            while len(b) < n:
                chunk = conn.recv(n-len(b))
                if not chunk:
                    raise EOFError
                b += chunk
            return b
        with conn:
            conn.settimeout(3)
            try:
                size = struct.unpack('!H',read(2))[0]
                answer = self.answer(read(size),host,True)
                if answer is None:
                    return
                frame = struct.pack('!H',len(answer))+answer
                # Split the length and response body so exact reads must handle fragments.
                for part in (frame[:1],frame[1:5],frame[5:]):
                    conn.sendall(part)
                    time.sleep(.005)
            except (OSError,EOFError):
                return

    def close(self):
        self.stop.set()
        for s in self.sockets:
            s.close()
        for t in self.threads:
            t.join(timeout=1)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',default='bin/tinc')
    args=parser.parse_args()
    compiler=(ROOT/args.compiler).resolve()
    out = ROOT/'bin/ci/dns'
    out.mkdir(parents=True,exist_ok=True)
    dns = DNS()
    try:
        with tempfile.TemporaryDirectory(prefix='dns-',dir=out) as tmp:
            work = Path(tmp)
            shutil.copytree(ROOT/'lib',work/'lib')
            shutil.copy(ROOT/'tools/ci/fixtures/dns_probe.tin',work/'lib/wire/probe.tin')
            hosts = work/'hosts'
            resolv = work/'resolv.conf'
            hosts.write_text('127.0.0.7 hosts.test Alias.Test\n::1 hosts6.test\n')
            def config(options='', servers=('127.0.0.1',), search='first.test second.test'):
                resolv.write_text(''.join('nameserver '+s+'\n' for s in servers)+
                                  'search '+search+'\noptions timeout:1 attempts:1 '+options+'\n')
            config()
            exe = work/'dns'
            subprocess.run([str(compiler),'-o',str(exe),'tools/ci/fixtures/dns.tin'],
                check=True,cwd=ROOT,env=dict(os.environ,TIN_ROOT=str(work)),timeout=60)
            port = free_port()
            env = dict(os.environ,PORT=str(port),TIN_CORES='1',TIN_DEADLINE_MS='1500',
                TIN_DNS_TEST='1',TIN_DNS_CACHE='0',TIN_DNS_HOSTS=str(hosts),TIN_DNS_RESOLV_CONF=str(resolv),TIN_DNS_PORT=str(dns.port))
            with (out/'server.log').open('wb') as log:
                server = subprocess.Popen([str(exe)],env=env,stdout=log,stderr=log)
                try:
                    for _ in range(100):
                        try:
                            assert response(request(port,'/health')) == (200,b'healthy')
                            break
                        except (OSError,ValueError):
                            assert server.poll() is None, 'DNS fixture crashed'
                            time.sleep(.05)
                    else:
                        raise AssertionError('DNS fixture did not start')
                    def lookup(name, timeout=0):
                        return response(request(port,'/resolve?name='+quote(name,safe='')+'&timeout='+str(timeout)))
                    v4 = (200,b'2:7f000001')
                    v6 = (200,b'10:00000000000000000000000000000001')
                    for literal,want in [('127.0.0.1',v4),('[::1]',v6),
                        ('::ffff:127.0.0.1',(200,b'10:00000000000000000000ffff7f000001'))]:
                        assert lookup(literal)==want,literal
                    before=len(dns.log)
                    assert lookup('hosts.test')==(200,b'2:7f000007')
                    assert lookup('ALIAS.TEST')==(200,b'2:7f000007')
                    assert lookup('hosts6.test')==v6
                    assert len(dns.log)==before, 'hosts lookup reached DNS'
                    # Empty the hosts overrides to exercise DNS CNAMEs with the same names.
                    hosts.write_text('')
                    for name in ('ok.test.','alias.test.','inline.test.','trunc.test.','wrongid.test.'):
                        assert lookup(name)==v4,name
                    assert lookup('v6.test.')==v6
                    oracle=subprocess.run(['go','run','./bench/ref/dns','127.0.0.1:'+str(dns.port),
                        'ok.test.','v6.test.','trunc.test.'],capture_output=True,check=True,cwd=ROOT,timeout=60)
                    assert oracle.stdout==b'2:7f000001\n10:00000000000000000000000000000001\n2:7f000001\n',oracle
                    assert any(x[1]=='trunc.test' and x[3]=='tcp' for x in dns.log)
                    assert lookup('missing.test.')[0]==502
                    assert lookup('bad.test.')[0]==502
                    config('ndots:1')
                    mark=len(dns.log)
                    assert lookup('short')==v4
                    assert dns.log[mark][1]=='short.first.test'
                    mark=len(dns.log)
                    assert lookup('fallback')==v4
                    assert [x[1] for x in dns.log[mark:]]==['fallback.first.test','fallback.second.test']
                    mark=len(dns.log)
                    assert lookup('dots.name')==v4
                    assert dns.log[mark][1]=='dots.name'
                    # A timeout ends the search like glibc: no AAAA, no other search names.
                    mark=len(dns.log)
                    assert lookup('drop')==(502,b'wire: cannot resolve "drop": no DNS server answered')
                    assert [x[1:3] for x in dns.log[mark:]]==[('drop.first.test',1)],dns.log[mark:]
                    config('ndots:3')
                    mark=len(dns.log)
                    assert lookup('many.dots.name')==v4
                    assert dns.log[mark][1]=='many.dots.name.first.test'
                    mark=len(dns.log)
                    assert lookup('ok.test.')==v4
                    assert [x[1] for x in dns.log[mark:]]==['ok.test']
                    config('rotate',('127.0.0.1','127.0.0.2'))
                    mark=len(dns.log)
                    assert lookup('rotate.test.')==v4 and lookup('rotate.test.')==v4
                    assert [x[0] for x in dns.log[mark:]]==['127.0.0.1','127.0.0.2']
                    config('',('127.0.0.1','127.0.0.2'))
                    assert lookup('retry.test.')==v4
                    config('attempts:2')
                    mark=len(dns.log)
                    # An explicit call timeout is shorter than the request's own deadline.
                    started=time.monotonic()
                    assert lookup('drop.test.',100)[0]==502
                    assert time.monotonic()-started < .7
                    dns.dropped.clear()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                        pending=[pool.submit(lookup,'drop.test.') for _ in range(6)]
                        assert dns.dropped.wait(1)
                        started=time.monotonic()
                        for _ in range(20):
                            assert response(request(port,'/health'))==(200,b'healthy')
                        assert time.monotonic()-started < .7,'DNS blocked a core'
                        for f in pending:
                            assert f.result()==(504,b'deadline exceeded')
                    assert len([x for x in dns.log[mark:] if x[1]=='drop.test']) >= 13,'attempt retry was not made'
                    # Request pools and DNS socket/scratch state must remain bounded.
                    for _ in range(100):assert lookup('ok.test.')==v4
                    def rss():
                        return int(Path('/proc/'+str(server.pid)+'/statm').read_text().split()[1])*os.sysconf('SC_PAGESIZE')
                    baseline=rss()
                    for _ in range(1000):assert lookup('ok.test.')==v4
                    assert rss()<=baseline+32*1024*1024,'repeated DNS lookups retained scratch memory'
                    assert server.poll() is None
                finally:
                    server.terminate()
                    server.wait(timeout=10)
            ipv6=work/'ipv6'
            subprocess.run([str(compiler),'-o',str(ipv6),'tools/ci/fixtures/ipv6.tin'],check=True,cwd=ROOT,env=dict(os.environ,TIN_ROOT=str(work)),timeout=60)
            listener=subprocess.Popen([str(ipv6)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,TIN_CORES='1'))
            try:
                assert select.select([listener.stderr],[],[],5)[0],'IPv6 listener did not report its port'
                line=listener.stderr.readline()
                assert line,'IPv6 listener exited before reporting its port'
                chosen=int(line)
                with socket.socket(socket.AF_INET6,socket.SOCK_STREAM) as c:
                    c.settimeout(3);c.connect(('::1',chosen));c.sendall(b'IPv6')
                    assert c.recv(4)==b'IPv6'
                assert listener.wait(timeout=5)==0,listener.stderr.read()
            finally:
                if listener.poll() is None:listener.terminate();listener.wait(timeout=5)
            client=work/'ipv6-client'
            subprocess.run([str(compiler),'-o',str(client),'tools/ci/fixtures/ipv6_client.tin'],check=True,cwd=ROOT,env=dict(os.environ,TIN_ROOT=str(work)),timeout=60)
            # Exercise connect's IPv6 family/length for both literals and AAAA answers.
            with socket.socket(socket.AF_INET6,socket.SOCK_STREAM) as echo:
                echo.bind(('::1',0));echo.listen(2);echo.settimeout(5)
                chosen=echo.getsockname()[1]
                def echo_clients():
                    for _ in range(2):
                        c,_=echo.accept()
                        with c:
                            c.settimeout(3);data=b''
                            while len(data)<4:
                                chunk=c.recv(4-len(data))
                                assert chunk,'IPv6 client closed early'
                                data+=chunk
                            assert data==b'IPv6'
                            c.sendall(data)
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pending=pool.submit(echo_clients)
                    for host in ('[::1]','v6.test.'):
                        got=subprocess.run([str(client),host+':'+str(chosen)],env=env,capture_output=True,timeout=5)
                        assert got.returncode==0 and got.stdout==b'IPv6\n',got
                    pending.result(timeout=5)
            print('PASS DNS: hosts precedence, A/AAAA, CNAMEs, compressed-name bounds, UDP/TCP fragments, IPv6 listen/dial, NXDOMAIN, search, ndots, rotate, attempts, timeout, concurrent request deadlines')
    finally:
        dns.close()


if __name__ == '__main__':
    main()
