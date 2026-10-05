#!/usr/bin/env python3
"""The Linux resolver's caches (#348): answers for their TTL, names that do not exist for a few
seconds, and /etc/hosts re-read when it changes. Uses dns_check's fake DNS server and fixture."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from urllib.parse import quote

from suite import ROOT
from task_check import free_port
from lifetime_check import request, response
from dns_check import DNS


def main():
    out = ROOT / 'bin/ci/dns_cache'
    out.mkdir(parents=True, exist_ok=True)
    dns = DNS()
    try:
        with tempfile.TemporaryDirectory(prefix='dnscache-', dir=out) as tmp:
            work = Path(tmp)
            shutil.copytree(ROOT / 'lib', work / 'lib')
            shutil.copy(ROOT / 'tools/ci/fixtures/dns_probe.tin', work / 'lib/wire/probe.tin')
            hosts, resolv = work / 'hosts', work / 'resolv.conf'
            hosts.write_text('127.0.0.7 hosts.test\n')
            resolv.write_text('nameserver 127.0.0.1\nsearch first.test\noptions timeout:1 attempts:1\n')
            exe = work / 'dns'
            subprocess.run([str(ROOT / os.environ.get('TIN_COMPILER', 'bin/tinc')), '-o', str(exe), 'tools/ci/fixtures/dns.tin'],
                           check=True, cwd=ROOT, env=dict(os.environ, TIN_ROOT=str(work)), timeout=300)
            port = free_port()
            env = dict(os.environ, PORT=str(port), TIN_CORES='1', TIN_DEADLINE_MS='4000', TIN_DNS_TEST='1',
                       TIN_DNS_HOSTS=str(hosts), TIN_DNS_RESOLV_CONF=str(resolv), TIN_DNS_PORT=str(dns.port))
            with (out / 'server.log').open('wb') as log:
                server = subprocess.Popen([str(exe)], env=env, stdout=log, stderr=log)
                try:
                    for _ in range(100):
                        try:
                            assert response(request(port, '/health')) == (200, b'healthy')
                            break
                        except (OSError, ValueError):
                            assert server.poll() is None, 'DNS fixture crashed'
                            time.sleep(.05)

                    def lookup(name):
                        return response(request(port, '/resolve?name=' + quote(name, safe='') + '&timeout=0'))

                    def queries(name):
                        return len([x for x in dns.log if x[1] == name])
                    v4 = (200, b'2:7f000001')
                    # An answer is kept for its TTL: ten lookups, one question.
                    for _ in range(10):
                        assert lookup('ok.test.') == v4
                    assert queries('ok.test') == 1, ('ten lookups of ok.test asked', queries('ok.test'))
                    # A one-second TTL runs out.
                    for _ in range(5):
                        assert lookup('ttl1.test.') == v4
                    assert queries('ttl1.test') == 1
                    time.sleep(1.3)
                    assert lookup('ttl1.test.') == v4
                    assert queries('ttl1.test') == 2, 'the entry stayed past its TTL'
                    # A name that does not exist is remembered for a few seconds, search list included.
                    assert lookup('gone.test.')[0] == 502
                    asked = len(dns.log)
                    for _ in range(5):
                        assert lookup('gone.test.')[0] == 502
                    assert len(dns.log) == asked, 'a missing name was asked for again at once'
                    time.sleep(5.3)
                    assert lookup('gone.test.')[0] == 502
                    assert len(dns.log) > asked, 'a missing name was never asked for again'
                    # /etc/hosts is read again when it changes, also by a rewrite of the same size.
                    assert lookup('hosts.test') == (200, b'2:7f000007')
                    hosts.write_text('127.0.0.8 hosts.test\n')
                    assert lookup('hosts.test') == (200, b'2:7f000008'), 'hosts change not seen (same size)'
                    hosts.write_text('127.0.0.9 hosts.test\n127.0.0.10 other.test\n')
                    assert lookup('hosts.test') == (200, b'2:7f000009'), 'hosts change not seen'
                    assert lookup('other.test') == (200, b'2:7f00000a')
                    assert server.poll() is None
                finally:
                    server.terminate()
                    server.wait(timeout=10)
        print('PASS DNS cache: answers kept for their TTL and dropped after it, missing names for 5 s, /etc/hosts re-read on change')
    finally:
        dns.close()


if __name__ == '__main__':
    main()
