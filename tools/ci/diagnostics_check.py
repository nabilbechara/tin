#!/usr/bin/env python3
"""Diagnostic codes (#244): the compiler, docs/ERRORS.md and the expected diagnostics agree.

Without a compiler it checks the codes only: every code the compiler prints (a string such as
"E502 TYPE_ARG_COUNT" in selfhost/*.tin) is documented under that name, every documented code
is printed by the compiler or retired, a number and a name each belong to one code, and every
coded line in the tests' expected diagnostics is documented. Given a compiler, it also compiles
each documented example and requires exactly the output the page shows.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DOC = Path('docs/ERRORS.md')
# The examples use the syntax docs/LANGUAGE.md describes.
EDITION = '0'

SOURCE_CODE = re.compile(r'"(E\d{3}) ([A-Z][A-Z0-9_]*)"')
HEADING = re.compile(r'^### (E\d{3}) ([A-Z][A-Z0-9_]*)$')
GROUP = re.compile(r'^## E(\d)xx ')
FENCE = re.compile(r'^```(\w*)\s*$')
PRINTED = re.compile(r'\berror (E\d{3}) ([A-Z][A-Z0-9_]*): ')
UNCODED = re.compile(r'(^|: )error: ')


def parse_doc(text):
    """The entries of the page in order: code, name, line, group digit, retired, fenced blocks."""
    entries, entry, group, fence, block = [], None, None, None, []
    for number, line in enumerate(text.splitlines(), 1):
        if fence is not None:
            if line.startswith('```'):
                if entry is not None:
                    entry['blocks'].append((fence, ''.join(l + '\n' for l in block)))
                fence, block = None, []
            else:
                block.append(line)
            continue
        match = FENCE.match(line)
        if match:
            fence = match.group(1)
            continue
        match = HEADING.match(line)
        if match:
            entry = {'code': match.group(1), 'name': match.group(2), 'line': number,
                     'group': group, 'retired': False, 'blocks': []}
            entries.append(entry)
            continue
        if line.startswith('## ') or line.startswith('# '):
            match = GROUP.match(line)
            group = match.group(1) if match else None
            entry = None
            continue
        if entry is not None and line.startswith('Retired'):
            entry['retired'] = True
    if fence is not None:
        raise ValueError(f'{DOC}: unterminated code block')
    return entries


def example(entry):
    """The program and expected output of an entry, or a problem."""
    programs = [body for kind, body in entry['blocks'] if kind == 'tin']
    outputs = [body for kind, body in entry['blocks'] if kind == 'text']
    if len(programs) != 1 or len(outputs) != 1:
        return None, None, 'needs exactly one ```tin example and one ```text output'
    return programs[0], outputs[0], None


def check_doc(entries, problems):
    documented = {}
    names = {}
    last = -1
    for e in entries:
        where = f"{DOC}:{e['line']}: {e['code']} {e['name']}"
        number = int(e['code'][1:])
        if e['code'] in documented:
            problems.append(f'{where}: code documented twice')
        if e['name'] in names:
            problems.append(f"{where}: name already used by {names[e['name']]}")
        if number <= last:
            problems.append(f'{where}: entries must be in code order')
        if e['group'] != e['code'][1]:
            problems.append(f"{where}: belongs under the heading ## E{e['code'][1]}xx")
        last = number
        documented[e['code']] = e
        names[e['name']] = e['code']
        if e['retired']:
            continue
        program, output, why = example(e)
        if why:
            problems.append(f'{where}: {why}')
            continue
        codes = PRINTED.findall(output)
        if (e['code'], e['name']) not in codes:
            problems.append(f'{where}: the example output does not show this code')
    return documented


def source_codes(root):
    """{(code, name): [file:line, ...]} for every code string in the compiler's sources."""
    used = {}
    for path in sorted((root / 'selfhost').glob('*.tin')):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            for code, name in SOURCE_CODE.findall(line):
                used.setdefault((code, name), []).append(f'{path.relative_to(root)}:{number}')
    return used


def expected_diagnostics(root):
    """(where, text) for every expected compiler diagnostic in the tests."""
    found = []
    for pattern in ('tests/v2/*.err', 'tests/edition1/*.err'):
        for path in sorted(root.glob(pattern)):
            for number, line in enumerate(path.read_text().splitlines(), 1):
                found.append((f'{path.relative_to(root)}:{number}', line))
    cases = root / 'tests/regressions/cases.json'
    for case in json.loads(cases.read_text()) if cases.exists() else []:
        expected = case.get('expected', {})
        if expected.get('phase') != 'compile':
            continue
        for key in ('stderr', 'stderr_contains'):
            for line in expected.get(key, '').splitlines():
                found.append((f"{cases.relative_to(root)}: {case['source']}", line))
    return found


def check_static(root=ROOT):
    """Problems with the codes, and (coded, uncoded) counts of expected diagnostic lines."""
    problems = []
    entries = parse_doc((root / DOC).read_text())
    documented = check_doc(entries, problems)
    used = source_codes(root)
    by_code, by_name = {}, {}
    for (code, name), sites in used.items():
        by_code.setdefault(code, set()).add(name)
        by_name.setdefault(name, set()).add(code)
        entry = documented.get(code)
        if entry is None:
            problems.append(f'{sites[0]}: {code} {name} is not documented in {DOC}')
        elif entry['name'] != name:
            problems.append(f"{sites[0]}: {code} is {entry['name']} in {DOC}, not {name}")
        elif entry['retired']:
            problems.append(f'{sites[0]}: {code} {name} is retired; a code is never reused')
    for code, names in sorted(by_code.items()):
        if len(names) > 1:
            problems.append(f"the compiler prints {code} with several names: {', '.join(sorted(names))}")
    for name, codes in sorted(by_name.items()):
        if len(codes) > 1:
            problems.append(f"the compiler prints {name} with several codes: {', '.join(sorted(codes))}")
    printed = {code for code, _ in used}
    for e in entries:
        if not e['retired'] and e['code'] not in printed:
            problems.append(f"{DOC}:{e['line']}: {e['code']} {e['name']} is not printed by the compiler "
                            '(mark it retired; never delete or reuse a code)')
    coded = uncoded = 0
    for where, line in expected_diagnostics(root):
        found = PRINTED.findall(line)
        for code, name in found:
            entry = documented.get(code)
            if entry is None or entry['name'] != name:
                problems.append(f'{where}: {code} {name} is not documented in {DOC}')
        if found:
            coded += 1
        elif UNCODED.search(line):
            uncoded += 1
    return problems, entries, coded, uncoded


def run_example(compiler, root, entry):
    """Compile one documented example; return a problem or None."""
    program, output, _ = example(entry)
    with tempfile.TemporaryDirectory(prefix='diag-') as work:
        Path(work, 'example.tin').write_text(program)
        env = dict(os.environ, TIN_ROOT=str(root), LC_ALL='C')
        try:
            result = subprocess.run([str(compiler), '-edition', EDITION, '-o', 'example', 'example.tin'],
                                    cwd=work, env=env, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            return f"{entry['code']} {entry['name']}: the example timed out"
    got = result.stderr.decode(errors='replace')
    if result.returncode != 1 or got != output:
        return (f"{DOC}:{entry['line']}: {entry['code']} {entry['name']}: the example printed "
                f'(exit {result.returncode}):\n{got}instead of:\n{output}')
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('compiler', nargs='?', help='also compile every documented example with this tinc')
    args = parser.parse_args()
    problems, entries, coded, uncoded = check_static()
    if args.compiler:
        compiler = Path(args.compiler).resolve()
        live = [e for e in entries if not e['retired'] and not example(e)[2]]
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            problems += [p for p in pool.map(lambda e: run_example(compiler, ROOT, e), live) if p]
    for problem in problems:
        print('FAIL diagnostics:', problem)
    if problems:
        return 1
    examples = 'and their examples ' if args.compiler else ''
    print(f'PASS diagnostics: {len(entries)} codes {examples}agree; '
          f'{coded} of {coded + uncoded} expected diagnostics carry a code')
    return 0


if __name__ == '__main__':
    sys.exit(main())
