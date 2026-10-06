#!/usr/bin/env python3
"""Diagnostic codes (#244): the compiler, toolchain/docs/ERRORS.md and the expected diagnostics agree.

Without a compiler it checks the codes only: every code the compiler prints (a string such as
"E502 TYPE_ARG_COUNT" in toolchain/compiler/*.tin) is documented under that name, every documented code
is printed by the compiler or retired, a number and a name each belong to one code, the
compiler prints no error without a code, and every line of the tests' expected diagnostics
carries a documented code. Given a compiler, it also compiles each documented example and
requires exactly the output the page shows.
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
DOC = Path('toolchain/docs/ERRORS.md')
# Examples use the syntax toolchain/docs/LANGUAGE.md describes; a ```tin edition=1 block uses edition 1.
EDITION = '0'

SOURCE_CODE = re.compile(r'"(E\d{3}) ([A-Z][A-Z0-9_]*)"')
HEADING = re.compile(r'^### (E\d{3}) ([A-Z][A-Z0-9_]*)$')
GROUP = re.compile(r'^## E(\d)xx ')
FENCE = re.compile(r'^```(\w*)(.*)$')
FENCE_EDITION = re.compile(r'\bedition=(\d+)\b')
# A block opened with file=NAME is written next to the example as NAME (a tin.lock, a second
# package), and a ```sh block replaces the default command: one line, [VAR=value ...] tinc ARGS.
FENCE_FILE = re.compile(r'\bfile=(\S+)')
PRINTED = re.compile(r'\berror (E\d{3}) ([A-Z][A-Z0-9_]*): ')
UNCODED = re.compile(r'(^|: )error: ')
# The compiler's sources print errors only through the coded helpers (err_code and the like).
SOURCE_UNCODED = re.compile(r'"error: ')


def parse_doc(text):
    """The entries of the page in order: code, name, line, group digit, retired, fenced blocks."""
    entries, entry, group, fence, block, edition, name = [], None, None, None, [], EDITION, None
    for number, line in enumerate(text.splitlines(), 1):
        if fence is not None:
            if line.startswith('```'):
                if entry is not None:
                    entry['blocks'].append((fence, ''.join(l + '\n' for l in block), edition, name))
                fence, block = None, []
            else:
                block.append(line)
            continue
        match = FENCE.match(line)
        if match:
            fence = match.group(1)
            found = FENCE_EDITION.search(match.group(2))
            edition = found.group(1) if found else EDITION
            found = FENCE_FILE.search(match.group(2))
            name = found.group(1) if found else None
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
        if entry is not None and line.startswith('No example:'):
            entry['unexampled'] = True
    if fence is not None:
        raise ValueError(f'{DOC}: unterminated code block')
    return entries


def example(entry):
    """The program (None when a command runs without one), its edition and the expected output
    of an entry, or a problem."""
    blocks = [b for b in entry['blocks'] if b[3] is None]
    programs = [(body, edition) for kind, body, edition, _ in blocks if kind == 'tin']
    outputs = [body for kind, body, _, _ in blocks if kind == 'text']
    commands = [body for kind, body, _, _ in blocks if kind == 'sh']
    if len(programs) > 1 or len(outputs) != 1 or len(commands) > 1 or not (programs or commands):
        return None, None, None, 'needs exactly one ```tin example (or ```sh command) and one ```text output'
    if commands and (len(commands[0].splitlines()) != 1 or 'tinc' not in commands[0].split()):
        return None, None, None, 'a ```sh command is one line that runs tinc'
    if not programs:
        return None, EDITION, outputs[0], None
    return programs[0][0], programs[0][1], outputs[0], None


def command(entry, compiler, edition):
    """The environment additions and argv that compile an entry's example."""
    commands = [body for kind, body, _, name in entry['blocks'] if kind == 'sh' and name is None]
    if not commands:
        return {}, [str(compiler), '-edition', edition, '-o', 'example', 'example.tin']
    words = commands[0].split()
    at = words.index('tinc')
    env = dict(word.split('=', 1) for word in words[:at])
    return env, [str(compiler)] + words[at + 1:]


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
        if e['retired'] or e.get('unexampled'):
            continue
        program, _, output, why = example(e)
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
    for path in sorted((root / 'toolchain/compiler').glob('*.tin')):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            for code, name in SOURCE_CODE.findall(line):
                used.setdefault((code, name), []).append(f'{path.relative_to(root)}:{number}')
    return used


def expected_diagnostics(root):
    """(where, text, whole) for every expected compiler diagnostic in the tests; whole is
    False for a stderr_contains contract, which is part of a line."""
    found = []
    for pattern in ('toolchain/tests/v2/*.err', 'toolchain/tests/edition1/*.err'):
        for path in sorted(root.glob(pattern)):
            for number, line in enumerate(path.read_text().splitlines(), 1):
                found.append((f'{path.relative_to(root)}:{number}', line, True))
    cases = root / 'toolchain/tests/regressions/cases.json'
    for case in json.loads(cases.read_text()) if cases.exists() else []:
        expected = case.get('expected', {})
        if expected.get('phase') != 'compile':
            continue
        for key in ('stderr', 'stderr_contains'):
            for line in expected.get(key, '').splitlines():
                found.append((f"{cases.relative_to(root)}: {case['source']}", line, key == 'stderr'))
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
    for path in sorted((root / 'toolchain/compiler').glob('*.tin')):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if SOURCE_UNCODED.search(line):
                problems.append(f'{path.relative_to(root)}:{number}: prints an error without a code '
                                '(use err_code and a code from toolchain/docs/ERRORS.md)')
    coded = uncoded = 0
    for where, line, whole in expected_diagnostics(root):
        found = PRINTED.findall(line)
        for code, name in found:
            entry = documented.get(code)
            if entry is None or entry['name'] != name:
                problems.append(f'{where}: {code} {name} is not documented in {DOC}')
        if found:
            coded += 1
        elif whole or UNCODED.search(line):
            uncoded += 1
            problems.append(f'{where}: an expected diagnostic without a code: {line}')
    return problems, entries, coded, uncoded


def run_example(compiler, root, entry):
    """Compile one documented example; return a problem or None."""
    program, edition, output, _ = example(entry)
    with tempfile.TemporaryDirectory(prefix='diag-') as work:
        if program is not None:
            Path(work, 'example.tin').write_text(program)
        for _, body, _, name in entry['blocks']:
            if name is not None:
                Path(work, name).parent.mkdir(parents=True, exist_ok=True)
                Path(work, name).write_text(body)
        extra, argv = command(entry, compiler, edition)
        env = dict(os.environ, TIN_ROOT=str(root), LC_ALL='C')
        env.update(extra)
        try:
            result = subprocess.run(argv, cwd=work, env=env, capture_output=True, timeout=60)
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
        live = [e for e in entries if not e['retired'] and not e.get('unexampled') and not example(e)[3]]
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            problems += [p for p in pool.map(lambda e: run_example(compiler, ROOT, e), live) if p]
    for problem in problems:
        print('FAIL diagnostics:', problem)
    if problems:
        return 1
    examples = 'and their examples ' if args.compiler else ''
    print(f'PASS diagnostics: {len(entries)} codes {examples}agree; '
          f'all {coded} expected diagnostics carry a code')
    return 0


if __name__ == '__main__':
    sys.exit(main())
