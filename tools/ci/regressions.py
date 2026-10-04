#!/usr/bin/env python3
"""Strict issue-linked regression contracts: PASS, known XFAIL, or blocking failure."""
import argparse
import json
import os
from pathlib import Path
import resource
import shutil
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
        replay = case.get('replay')
        if replay is not None and (not isinstance(replay, dict) or set(replay) != {'capsule', 'key'}
                                   or not (MANIFEST.parent / str(replay['capsule'])).is_file()):
            raise ValueError(f'{case["source"]}: a replay case needs its capsule file and key (tin replay --save-test, #242)')
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


def run_case(case, compiler, work, cross=None, docker=None):
    target = case.get('target') or cross
    exe = work / Path(case['source']).stem
    command = [str(compiler)] + (['-target', target] if target else [])
    command += ['-o', str(exe), 'tests/regressions/' + case['source']]
    code, stdout, stderr = execute(command, env=dict(os.environ, TIN_ROOT=str(ROOT)))
    actual = {'phase': 'compile', 'exit': code, 'stdout': stdout.decode(errors='replace'), 'stderr': stderr.decode(errors='replace')}
    if code != 0 or case['expected']['phase'] == 'compile':
        return actual
    env, docker_env = None, []
    if 'replay' in case:
        # A saved replay (#242): the program runs the capsule's request instead of serving.
        shutil.copy(MANIFEST.parent / case['replay']['capsule'], work / case['replay']['capsule'])
        env = {k: v for k, v in os.environ.items() if not k.startswith('TIN_REPLAY_')}
        env.update(TIN_REPLAY_CAPSULE=str(work / case['replay']['capsule']), TIN_REPLAY_KEY=case['replay']['key'])
        docker_env = ['-e', 'TIN_REPLAY_CAPSULE=/work/' + case['replay']['capsule'], '-e', 'TIN_REPLAY_KEY=' + case['replay']['key']]
    if docker:
        # Cross-built cases run in a container of the target with the same limits.
        command = ['docker', 'run', '--rm', '--platform', target.replace('-', '/'), '-v', str(work) + ':/work',
                   '-w', '/work'] + docker_env + [docker, 'sh', '-c', 'ulimit -c 0; ulimit -v 524288; exec timeout 20 /work/' + exe.name]
        code, stdout, stderr = execute(command, timeout=60)
        return {'phase': 'run', 'exit': code, 'stdout': stdout.decode(errors='replace'), 'stderr': stderr.decode(errors='replace')}
    try:
        result = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, timeout=20, preexec_fn=limits, env=env)
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
    parser.add_argument('--target', help='Cross-build cases without their own target for this target')
    parser.add_argument('--docker', help='Execute cross-built cases in this Linux image')
    args = parser.parse_args()
    if args.docker and not args.target:
        parser.error('--docker requires --target')
    platform = 'linux' if args.docker else sys.platform
    cases = load_cases()
    if args.audit:
        audit(cases)
        return 0
    out = ROOT / 'bin/ci'
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix='regressions-', dir=out) as work:
        for case in cases:
            if case.get("platform", platform) != platform:
                print(f'SKIP {case["source"]}: runs on {case["platform"]}')
                continue
            own = 'target' in case
            actual = run_case(case, Path(args.compiler).resolve(), Path(work),
                              None if own else args.target, None if own else args.docker)
            status = classify(case, actual)
            print(f'{status} {case["source"]} (#{case["issue"]})')
            if status in ('FAIL', 'XPASS'):
                print(json.dumps(actual, indent=2))
                if status == 'XPASS':
                    print('Fix detected: keep this test and remove known_failure from its manifest entry.')
            results.append({'source': case['source'], 'issue': case['issue'], 'status': status, 'actual': actual})
    (out / ('regressions-' + args.target + '.json' if args.target else 'regressions.json')).write_text(json.dumps(results, indent=2) + '\n')
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
