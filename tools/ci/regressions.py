#!/usr/bin/env python3
"""Strict issue-linked regression contracts: PASS, known XFAIL, or blocking failure."""
import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import urllib.request
from suite import ROOT, execute

MANIFEST = ROOT / 'tests/regressions/cases.json'


def load_cases():
    cases = json.loads(MANIFEST.read_text())
    sources = [c['source'] for c in cases]
    discovered = {p.name for p in MANIFEST.parent.glob('*.tin')}
    if len(sources) != len(set(sources)) or set(sources) != discovered:
        raise ValueError('Every regression source must occur exactly once in cases.json')
    for case in cases:
        if 'expected' not in case or not isinstance(case.get('issue'), int):
            raise ValueError('Each case needs an expected contract and issue number')
        for contract in [case['expected'], case.get('known_failure')]:
            if contract is not None and (contract.get('phase') not in ('compile', 'run') or 'exit' not in contract):
                raise ValueError('Contracts require phase and exit')
    return cases


def matches(contract, actual):
    for key, value in contract.items():
        if key == 'stderr_contains':
            if value not in actual.get('stderr', ''):
                return False
        elif actual.get(key) != value:
            return False
    return True


def classify(case, actual):
    if matches(case['expected'], actual):
        return 'XPASS' if 'known_failure' in case else 'PASS'
    if 'known_failure' in case and matches(case['known_failure'], actual):
        return 'XFAIL'
    return 'FAIL'


def limits():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # Bound negative allocator probes. Darwin does not implement RLIMIT_AS usefully.
    if sys.platform == 'linux':
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)


def run_case(case, compiler, work):
    target = case.get('target')
    exe = work / Path(case['source']).stem
    command = [str(compiler)] + (['-target', target] if target else [])
    command += ['-o', str(exe), 'tests/regressions/' + case['source']]
    code, stdout, stderr = execute(command, env=dict(os.environ, TIN_ROOT=str(ROOT)))
    actual = {'phase': 'compile', 'exit': code, 'stdout': stdout.decode(errors='replace'), 'stderr': stderr.decode(errors='replace')}
    if code != 0 or case['expected']['phase'] == 'compile':
        return actual
    try:
        result = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, timeout=20, preexec_fn=limits)
        return {'phase': 'run', 'exit': result.returncode, 'stdout': result.stdout.decode(errors='replace'), 'stderr': result.stderr.decode(errors='replace')}
    except subprocess.TimeoutExpired:
        return {'phase': 'run', 'exit': 124, 'stdout': '', 'stderr': 'CI timeout'}


def audit(cases):
    """An issue cannot remain closed while its exemption is still in the tree."""
    failures = []
    for number in sorted({c['issue'] for c in cases if 'known_failure' in c}):
        request = urllib.request.Request(f'https://api.github.com/repos/yasserreslan/tin/issues/{number}',
                                         headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'tin-ci'})
        if os.environ.get('GH_TOKEN'):
            request.add_header('Authorization', 'Bearer ' + os.environ['GH_TOKEN'])
        with urllib.request.urlopen(request, timeout=30) as response:
            state = json.load(response)['state']
        print(f'Issue #{number}: {state}')
        if state != 'open':
            failures.append(number)
    if failures:
        raise ValueError(f'Closed issues still have known-failure exemptions: {failures}. Keep the test, remove known_failure, and require PASS.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default='bin/tinc')
    parser.add_argument('--audit', action='store_true')
    args = parser.parse_args()
    cases = load_cases()
    if args.audit:
        audit(cases)
        return 0
    out = ROOT / 'bin/ci'
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix='regressions-', dir=out) as work:
        for case in cases:
            if case.get("platform", sys.platform) != sys.platform:
                print(f'SKIP {case["source"]}: runs on {case["platform"]}')
                continue
            actual = run_case(case, Path(args.compiler).resolve(), Path(work))
            status = classify(case, actual)
            print(f'{status} {case["source"]} (#{case["issue"]})')
            if status in ('FAIL', 'XPASS'):
                print(json.dumps(actual, indent=2))
                if status == 'XPASS':
                    print('Fix detected: keep this test and remove known_failure from its manifest entry.')
            results.append({'source': case['source'], 'issue': case['issue'], 'status': status, 'actual': actual})
    (out / 'regressions.json').write_text(json.dumps(results, indent=2) + '\n')
    summary = '\n'.join(f'- {r["status"]}: `{r["source"]}` ([#{r["issue"]}](https://github.com/yasserreslan/tin/issues/{r["issue"]}))' for r in results)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write('### Issue-linked regressions\n\n' + summary + '\n')
    return int(any(r['status'] not in ('PASS', 'XFAIL') for r in results))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))
