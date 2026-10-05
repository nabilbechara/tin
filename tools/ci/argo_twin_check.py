#!/usr/bin/env python3
"""argo.Get and argo.GetStrict against encoding/json, case by case (#354). Where Go decides, Tin
agrees (type errors, ranges, trailing garbage, unknown members under DisallowUnknownFields); Tin is
stricter on purpose for duplicate members (GetStrict), invalid UTF-8 and lone surrogates (both)."""
import os
import shutil
import subprocess
import sys

from suite import ROOT

# Where Tin differs from Go by design: case -> (Tin's default, Tin's strict).
STRICTER = {
    'duplicate': ('ok', 'fault'),
    'bad_utf8': ('fault', 'fault'),
    'lone_surrogate': ('fault', 'fault'),
}


def lines(out):
    result = {}
    for line in out.strip().splitlines():
        name, default, strict = line.split()
        result[name] = (default.split('=')[1], strict.split('=')[1])
    return result


def main():
    compiler = os.environ.get('TIN_COMPILER', str(ROOT / 'bin/tinc'))
    exe = ROOT / 'bin/ci/argo_twin'
    exe.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([compiler, '-o', str(exe), 'tools/ci/fixtures/argo_twin.tin'], cwd=ROOT,
                   env=dict(os.environ, TIN_ROOT=str(ROOT)), check=True)
    tin = lines(subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout)
    if not shutil.which('go'):
        print('go is not installed: Tin results only')
        go = None
    else:
        go = lines(subprocess.run(['go', 'run', 'tools/ci/fixtures/argo_twin.go'], cwd=ROOT,
                                  capture_output=True, text=True, check=True).stdout)
    bad = []
    for name, got in tin.items():
        want = STRICTER.get(name) or (go or {}).get(name)
        if want is None:
            continue
        if got != want:
            bad.append('%s: tin %s, want %s' % (name, got, want))
        elif go is not None and name in STRICTER:
            assert go[name][0] == 'ok', 'the twin says Go rejects %s' % name
    assert not bad, bad
    for name, (default, strict) in tin.items():
        print('%-17s Get %-5s GetStrict %-5s%s' % (name, default, strict, '' if go is None else '  (Go: %s / %s)' % go[name]))


if __name__ == '__main__':
    sys.exit(main())
