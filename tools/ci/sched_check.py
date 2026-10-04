#!/usr/bin/env python3
"""Scheduling replay (#243, notes/interface_replay.md section 7): a recording select appends
its winning arm as sched.select@1 keyed by its site; a replaying select checks, watches and
waits for the recorded arm only, so a select that raced a timer takes the recorded branch
under any live timing. A request's tasks resume in the recorded order (sched.resume@1), and
a task whose effect is not the next record waits for its turn; when no task can go on, the
replay diverges instead of hanging. Cancels go on the tape (sched.cancel@1); replaying, a
deadline comes from the tape, not the clock. The fixture counts branches, it never times them."""
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from suite import ROOT
from replay_check import CAPSULE_KEY, decode_body, free_port, open_capsule

EXPECTED = '''\
no tape: lane
lane recorded: lane [sched.resume@1  1 sched.resume@1  1 sched.resume@1  0 sched.select@1 sched.tin:17 0]
lane live now: timer replayed: 20 of 20 took lane clean: 20
timer recorded: timer [sched.resume@1  1 sched.resume@1  0 sched.select@1 sched.tin:17 1 sched.cancel@1 task 1 fault canceled sched.resume@1  1 sched.resume@1  0]
timer live now: lane replayed: 20 of 20 took timer clean: 20
race: 30 of 30 recordings replayed their branch under both timings
deadline recorded: fault deadline exceeded [sched.resume@1  1 sched.cancel@1 within 0 fault deadline exceeded sched.resume@1  0 sched.select@1 sched.tin:17 2 sched.resume@1  1 sched.resume@1  0]
deadline replayed: fault deadline exceeded diverged: false
recorded deadline under 10 s: fault deadline exceeded diverged: false left: 0
no deadline recorded: lane live under 1 ms: fault deadline exceeded replayed under 1 ms: 10 of 10
order recorded: ab ba live swapped: ba
order replayed: 20 of 20 gave ab and 20 of 20 gave ba
effects recorded: v:b v:a  [sched.resume@1  1 sched.resume@1  2 test@1 b test@1 a sched.resume@1  0]
effects replayed: 20 of 20 gave v:b v:a 
effects diverged: fault replay: divergence at effect 2: got test@1 "a", recorded test@1 "b" | replay: divergence at effect 2: got test@1 "a", recorded test@1 "b"
old tape: v:a lane diverged: false left: 0
other site: other replay: divergence at effect 0: select at sched.tin:30 has no record
'''


def get(port, path):
    """The body of GET path, or None when the server does not answer."""
    with socket.create_connection(('127.0.0.1', port), timeout=10) as c:
        c.sendall(f'GET {path} HTTP/1.1\r\nHost: race\r\nConnection: close\r\n\r\n'.encode())
        data = b''
        while True:
            chunk = c.recv(65536)
            if not chunk:
                break
            data += chunk
    return data.split(b'\r\n\r\n', 1)[1].decode()


def serve(exe, port, **extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith('TIN_REPLAY_') and k != 'RACE_MODE'}
    env.update(PORT=str(port), TIN_CORES='1', **extra)
    server = subprocess.Popen([str(exe)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(200):
        try:
            socket.create_connection(('127.0.0.1', port), timeout=0.1).close()
            return server
        except OSError:
            time.sleep(0.05)
    server.kill()
    raise SystemExit('FAIL scheduling replay end to end: the server did not start')


def stop(server):
    server.send_signal(signal.SIGTERM)
    try:
        server.wait(timeout=30)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()


def end_to_end(work):
    """A request whose select raced a timer, recorded by anvil (TIN_REPLAY_SAMPLE=1 keeps every
    capsule) and replayed by tin replay under live timings that make each side win: it takes the
    recorded branch every time and serves its whole tape."""
    exe = work / 'sched_serve'
    subprocess.run([str(ROOT / 'bin/tinc'), '-edition', '1', '-o', str(exe), 'tools/ci/fixtures/sched_serve.tin'],
                   check=True, env=dict(os.environ, TIN_ROOT=str(ROOT)), cwd=ROOT, timeout=60)
    # Live, RACE_MODE decides the race: the timing really flips the branch.
    port = free_port()
    server = serve(exe, port, RACE_MODE='timer')
    try:
        flipped = (get(port, '/lane'), get(port, '/timer'))
    finally:
        stop(server)
    port = free_port()
    server = serve(exe, port, RACE_MODE='lane')
    try:
        flipped += (get(port, '/timer'),)
    finally:
        stop(server)
    assert flipped == ('timer', 'timer', 'lane'), flipped
    spool = work / 'spool'
    paths = ['/lane', '/timer'] + ['/race/' + 'x' * (1 + i % 3) for i in range(30)]
    port = free_port()
    server = serve(exe, port, TIN_REPLAY_DIR=str(spool), TIN_REPLAY_KEY=CAPSULE_KEY.hex(), TIN_REPLAY_SAMPLE='1')
    try:
        answers = [get(port, p) for p in paths]
    finally:
        stop(server)
    assert answers[:2] == ['lane', 'timer'], answers[:2]
    caps = sorted(spool.glob('*.tcap'))
    assert len(caps) == len(paths), (len(caps), len(paths))
    failures = []
    selects = 0
    replays = 0
    env = {k: v for k, v in os.environ.items() if not k.startswith('TIN_REPLAY_')}
    env['TIN_REPLAY_KEY'] = CAPSULE_KEY.hex()
    for path, want, cap in zip(paths, answers, caps):
        c = decode_body(open_capsule(cap.read_bytes()))
        if not c['request'].startswith(f'GET {path} '.encode()):
            failures.append(f'{cap.name}: holds {c["request"][:40]!r}, not {path}')
            continue
        kinds = [e[1] for e in c['effects']]
        if 'sched.select@1' in kinds:
            selects += 1
        for mode in ('', 'lane', 'timer'):
            r = subprocess.run([str(ROOT / 'tin'), 'replay', str(cap), '--against', str(exe)], capture_output=True,
                               text=True, timeout=60, env=dict(env, RACE_MODE=mode))
            replays += 1
            if r.returncode != 0 or r.stdout != 'replay: status 200 (recorded 200)\n' + want:
                failures.append(f'{path} recorded {want!r}, RACE_MODE={mode!r}: exit {r.returncode}\n{r.stdout}{r.stderr}')
    (ROOT / 'bin/ci/sched/end_to_end.log').write_text('\n'.join(failures))
    if failures:
        raise SystemExit('FAIL scheduling replay end to end:\n' + '\n'.join(failures[:10]))
    assert selects == len(paths), selects
    lanes = answers.count('lane')
    print(f'PASS scheduling replay end to end: {len(paths)} requests whose select raced a timer, recorded by anvil '
          f'({lanes} took the lane), {replays} tin replay runs under both deciding timings all took the recorded '
          'branch and served the whole capsule')


def main():
    out = ROOT / 'bin/ci/sched'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sched-', dir=out) as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / 'lib', work / 'lib')
        probe = work / 'lib/schedprobe'
        probe.mkdir()
        shutil.copy(ROOT / 'tools/ci/fixtures/sched_probe.tin', probe / 'probe.tin')
        exe = work / 'sched'
        env = dict(os.environ, TIN_ROOT=str(work))
        subprocess.run([str(ROOT / 'bin/tinc'), '-edition', '1', '-o', str(exe), 'tools/ci/fixtures/sched.tin'],
                       check=True, env=env, cwd=ROOT, timeout=60)
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60, cwd=ROOT)
        (out / 'sched.log').write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result
        if result.stdout != EXPECTED:
            raise SystemExit('FAIL scheduling replay: output differs\n--- want\n' + EXPECTED +
                             '--- got\n' + result.stdout)
        end_to_end(work)
    print('PASS scheduling replay: select winners and resume order replayed under the opposite timing, effects in their recorded order, deadlines from the tape, divergence')


if __name__ == '__main__':
    main()
