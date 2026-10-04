#!/usr/bin/env python3
"""Docs are edition 1 (#227): no edition-0 syntax in the docs or examples, and every docs code
block compiles.

Without a compiler it checks the text only. Every fenced block in README.md and docs/*.md names
its language, Tin code is fenced ```tin (never ```go), and no Tin code (a ```tin block, an
inline `code` span, or a file under examples/) uses a form edition 1 removed: func,
var, :=, switch/case/default, the three-clause for, range, ++/--, go, chan, extern.
Given a compiler, it also compiles every ```tin block of README.md and docs/ with -edition 1.
docs/ERRORS.md is checked for syntax only: diagnostics_check.py compiles its examples.

A ```tin block is a program, or a package that a generated program imports. Missing parts are
added: `package main` when there is no package clause, an import for each standard package it
uses, and an empty `fn main()`. Attributes after
the language word change that:
  body          the block is statements: it becomes the body of `fn example() !`;
  error         the block must not compile (error=E123 also names the code it must print);
  old-syntax    the block shows edition-0 syntax on purpose (a rejected form): no syntax check;
  file=NAME     the block is another file, NAME, of the program before it (a local package).
An HTML comment `<!-- tin-prelude` ... `-->` right before a fence holds declarations the
reader does not need (a type, a stub function); they are added to that block only.
Text between `<!-- docs-check: old-syntax begin -->` and `<!-- docs-check: old-syntax end -->`
may name removed forms (a table of what edition 1 changed).
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
# Fenced languages a doc may use; Tin code is ```tin, a grammar ```ebnf, program output ```text.
LANGUAGES = {'tin', 'text', 'sh', 'ebnf', 'dockerfile', 'json', 'yaml', 'go-reference'}
# Syntax-checked languages: ```text is program output and layouts, the rest shell, data or Go.
CODE = {'tin'}
FENCE = re.compile(r'^(\s*)```(?!`)([^\s`]*)([^`]*)$')
PRELUDE_START = '<!-- tin-prelude'
REGION_BEGIN = '<!-- docs-check: old-syntax begin -->'
REGION_END = '<!-- docs-check: old-syntax end -->'
INLINE = re.compile(r'(`+)(.+?)\1')

# Forms edition 1 removed, each with the replacement the message names.
OLD_FORMS = [
    (re.compile(r'\bfunc\b'), "'func' (edition 1: fn)"),
    (re.compile(r'\bvar\b'), "'var' (edition 1: let or mut)"),
    (re.compile(r':='), "':=' (edition 1: let or mut)"),
    (re.compile(r'\bswitch\b'), "'switch' (edition 1: match)"),
    (re.compile(r'^\s*(case\b.*|default\s*):\s*($|//)'), "a case clause (edition 1: match arms)"),
    (re.compile(r'\bfor\b[^{]*;[^{]*;'), "a three-clause for (edition 1: for i in 0..n)"),
    (re.compile(r'(\bfor\b.*|:=\s*)\brange\b'), "'range' (edition 1: for x in xs)"),
    (re.compile(r'(\w|\]|\))(\+\+|--)(?![\w-])'), "'++' or '--' (edition 1: += 1)"),
    (re.compile(r'^\s*go\s+[\w.]+\('), "'go' (edition 1: scope or detach)"),
    (re.compile(r'\bchan\b'), "'chan' (edition 1 has no channels)"),
    (re.compile(r'\bextern\s+(func|fn)\b'), "'extern' (edition 1 has no extern declarations)"),
]
STRING = re.compile(r'"(\\.|[^"\\])*"|`[^`]*`|\'(\\.|[^\'\\])*\'')


def code_part(line):
    """The line without its string literals and // comment, so prose in them never matches."""
    line = STRING.sub('""', line)
    at = line.find('//')
    return line if at < 0 else line[:at]


def old_forms(line):
    """The removed forms one line of Tin uses."""
    code = code_part(line)
    return [why for pattern, why in OLD_FORMS if pattern.search(code)]


def parse_markdown(text):
    """The blocks of a page: dicts with line, lang, attrs, body and prelude; and the prose
    lines outside blocks as (line, text, exempt)."""
    blocks, prose = [], []
    fence = None
    exempt = False
    prelude, in_prelude, prelude_end = None, False, -1
    lines = text.splitlines()
    for number, line in enumerate(lines, 1):
        if fence is not None:
            if line.strip().startswith('```') and line.strip().strip('`') == '':
                blocks.append(fence)
                fence = None
            else:
                indent = fence['indent']
                fence['body'].append(line[len(indent):] if line.startswith(indent) else line.lstrip())
            continue
        if in_prelude:
            if line.strip() == '-->':
                in_prelude, prelude_end = False, number
            else:
                prelude.append(line)
            continue
        if line.strip() == PRELUDE_START:
            prelude, in_prelude = [], True
            continue
        match = FENCE.match(line)
        if match:
            words = match.group(3).split()
            attrs = {}
            for word in words:
                key, _, value = word.partition('=')
                attrs[key] = value or True
            fence = {'line': number, 'indent': match.group(1), 'lang': match.group(2), 'attrs': attrs,
                     'body': [], 'exempt': exempt or 'old-syntax' in attrs,
                     'prelude': prelude if prelude is not None and prelude_end == number - 1 else None}
            prelude = None
            continue
        if line.strip() == REGION_BEGIN:
            exempt = True
        elif line.strip() == REGION_END:
            exempt = False
        prose.append((number, line, exempt))
    if fence is not None:
        raise ValueError(f"unterminated code block at line {fence['line']}")
    if in_prelude:
        raise ValueError('unterminated tin-prelude comment')
    return blocks, prose


def doc_pages(root):
    return [root / 'README.md'] + sorted((root / 'docs').glob('*.md'))


def check_page(path, root, problems):
    """Syntax problems of one page; returns its compilable ```tin blocks."""
    where = path.relative_to(root)
    try:
        blocks, prose = parse_markdown(path.read_text())
    except ValueError as e:
        problems.append(f'{where}: {e}')
        return []
    for number, line, exempt in prose:
        if exempt:
            continue
        for _, span in INLINE.findall(line):
            # A bare word (`switch`) names a construct; code has more than one word.
            if re.fullmatch(r'[\w.$]+', span.strip()):
                continue
            for why in old_forms(span):
                problems.append(f'{where}:{number}: `{span}` uses {why}')
    programs = []
    for b in blocks:
        if b['lang'] == 'go':
            problems.append(f"{where}:{b['line']}: Tin code is fenced ```tin, not ```go "
                            '(real Go is ```go-reference)')
        elif b['lang'] not in LANGUAGES:
            problems.append(f"{where}:{b['line']}: a code block names its language "
                            f"({', '.join(sorted(LANGUAGES))}), not {b['lang'] or 'nothing'!r}")
        if b['lang'] in CODE | {'go'} and not b['exempt']:
            for offset, line in enumerate(b['body'], 1):
                for why in old_forms(line):
                    problems.append(f"{where}:{b['line'] + offset}: uses {why}")
        if b['lang'] == 'tin':
            programs.append(b)
    return programs


def check_examples(root, problems):
    count = 0
    for path in sorted((root / 'examples').rglob('*.tin')):
        count += 1
        for number, line in enumerate(path.read_text().splitlines(), 1):
            for why in old_forms(line):
                problems.append(f'{path.relative_to(root)}:{number}: uses {why}')
    return count


def check_static(root=ROOT):
    """Problems, and {page: [```tin blocks]} for the pages whose blocks this check compiles."""
    problems, programs = [], {}
    for path in doc_pages(root):
        if not path.exists():
            continue
        found = check_page(path, root, problems)
        if path.name != 'ERRORS.md':
            programs[path] = found
    examples = check_examples(root, problems)
    return problems, programs, examples


PACKAGE = re.compile(r'^package\s+(\w+)', re.M)
IMPORT = re.compile(r'^import\s+"([^"]+)"', re.M)
MAIN = re.compile(r'^fn\s+main\s*\(', re.M)
USE = re.compile(r'(?<![\w.])([a-z]\w*)\.[A-Za-z_]')


def library_packages(root):
    return {p.name for p in (root / 'lib').iterdir() if p.is_dir() and p.name not in ('runtime', 'std')}


def program(block, packages):
    """The source a ```tin block compiles as."""
    body = '\n'.join(block['body']) + '\n'
    prelude = '\n'.join(block['prelude'] or []) + ('\n' if block['prelude'] else '')
    # The prelude's and the block's imports go first, after the package clause.
    head_lines, rest = [], []
    for line in (prelude + body).splitlines():
        (head_lines if PACKAGE.match(line) or IMPORT.match(line) else rest).append(line)
    text = '\n'.join(rest) + '\n'
    if 'body' in block['attrs']:
        body_lines = [l for l in body.splitlines() if not IMPORT.match(l)]
        prelude_lines = [l for l in prelude.splitlines() if not IMPORT.match(l)]
        indented = ''.join('\t' + l + '\n' if l.strip() else '\n' for l in body_lines)
        text = '\n'.join(prelude_lines) + '\nfn example() ! {\n' + indented + '}\n'
    package = [l for l in head_lines if PACKAGE.match(l)] or ['package main']
    imports = [l for l in head_lines if IMPORT.match(l)]
    imported = {IMPORT.match(l).group(1).rsplit('/', 1)[-1] for l in imports}
    # A package the block uses and does not import, unless a local or parameter has its name.
    wanted = sorted({name for name in USE.findall(text) if name in packages and name not in imported
                     and not re.search(r'\b(let|mut)\s+' + name + r'\b(?!\.)|[(,]\s*' + name + r'\s+(mut\s+)?[\w\[?]', text)})
    imports += [f'import "{name}"' for name in wanted]
    text = package[0] + '\n\n' + ''.join(l + '\n' for l in imports) + '\n' + text
    if not MAIN.search(text) and PACKAGE.search(text).group(1) == 'main':
        text += '\nfn main() {}\n'
    return text


def compile_block(compiler, root, page, block, packages):
    """Compile one block; return a problem or None."""
    where = f"{page.relative_to(root)}:{block['line']}"
    source = program(block, packages)
    with tempfile.TemporaryDirectory(prefix='docs-') as work:
        package = PACKAGE.search(source).group(1)
        if package == 'main':
            Path(work, 'example.tin').write_text(source)
        else:
            # A library package is compiled through a program that imports it.
            Path(work, package + '.tin').write_text(source)
            Path(work, 'example.tin').write_text(f'package main\n\nimport "./{package}"\n\nfn main() {{}}\n')
        for name, body in block.get('files', []):
            Path(work, name).parent.mkdir(parents=True, exist_ok=True)
            Path(work, name).write_text(body)
        env = dict(os.environ, TIN_ROOT=str(root), LC_ALL='C')
        argv = [str(compiler), '-edition', '1', '-S', '-o', 'example.s', 'example.tin']
        try:
            result = subprocess.run(argv, cwd=work, env=env, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            return f'{where}: compiling the block timed out'
    out = result.stderr.decode(errors='replace') + result.stdout.decode(errors='replace')
    expect = block['attrs'].get('error')
    if expect:
        if result.returncode == 0:
            return f'{where}: the block is marked error but compiles'
        if expect is not True and f'error {expect} ' not in out:
            return f'{where}: the block must fail with {expect}, but printed:\n{out}'
        return None
    if result.returncode != 0:
        numbered = ''.join(f'{i:4} {l}\n' for i, l in enumerate(source.splitlines(), 1))
        return f'{where}: the block does not compile:\n{out}as compiled:\n{numbered}'
    return None


def attach_files(blocks):
    """A block marked file=NAME is another file of the program before it; returns the blocks
    to compile."""
    out = []
    for b in blocks:
        name = b['attrs'].get('file')
        if name and name is not True and out:
            out[-1]['files'].append((name, '\n'.join(b['body']) + '\n'))
            continue
        b['files'] = []
        out.append(b)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('compiler', nargs='?', help='also compile every ```tin block with this tinc')
    args = parser.parse_args()
    problems, programs, examples = check_static()
    compiled = 0
    if args.compiler:
        compiler = Path(args.compiler).resolve()
        packages = library_packages(ROOT)
        jobs = [(page, b) for page, blocks in programs.items() for b in attach_files(blocks)]
        compiled = len(jobs)
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            problems += [p for p in pool.map(lambda j: compile_block(compiler, ROOT, j[0], j[1], packages), jobs) if p]
    for problem in problems:
        print('FAIL docs:', problem)
    if problems:
        return 1
    built = f', {compiled} code blocks compile' if args.compiler else ''
    print(f'PASS docs: no edition-0 syntax in {len(programs) + 1} pages and {examples} examples{built}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
