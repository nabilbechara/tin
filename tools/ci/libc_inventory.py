"""Audit Linux foreign declarations and linker-added imports against the removal plan."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ('linux-arm64', 'linux-amd64')
EXTERN = re.compile(r'\bextern\s+(?:func|fn)\s+([A-Za-z_][A-Za-z_0-9]*)\s*\(')
IMPORT = re.compile(r'\bel_import\s*\(\s*(?:cstr\s*\(\s*)?"([A-Za-z_][A-Za-z_0-9]*)"\s*\)')
LEXEME = re.compile(r'"(?:\\.|[^"\\])*"|`[^`]*`|//[^\n]*|/\*.*?\*/', re.S)


def mask(text, strings=True):
    def replace(match):
        value = match.group()
        if not strings and value.startswith(('"', '`')):
            return value
        return ''.join('\n' if c == '\n' else ' ' for c in value)
    return LEXEME.sub(replace, text)


def linux_file(path, target):
    name = path.name
    return not (name.endswith(('_test.tin', '_darwin.tin', '_darwin_arm64.tin',
                              '_darwin_amd64.tin'))
                or (name.endswith('_linux_arm64.tin') and target != 'linux-arm64')
                or (name.endswith('_linux_amd64.tin') and target != 'linux-amd64'))


def discover(root=ROOT, target='linux-arm64'):
    if target not in TARGETS:
        raise ValueError('unsupported inventory target: ' + target)
    symbols = {}
    for folder in ('toolchain/runtime', 'toolchain/std', 'packages', 'toolchain/compiler'):
        if not (root / folder).is_dir():
            continue
        for path in sorted((root / folder).rglob('*.tin')):
            if not linux_file(path, target):
                continue
            text = path.read_text()
            names = set(EXTERN.findall(mask(text)))
            if path.name in ('elf.tin', 'elf_x64.tin'):
                names.update(IMPORT.findall(mask(text, strings=False)))
            for name in names:
                symbols.setdefault(name, set()).add(path.relative_to(root).as_posix())
    return symbols


def read_inventory(path):
    rows = {}
    for line in path.read_text().splitlines():
        if not line.startswith('| `'):
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if len(cells) != 6:
            raise ValueError('inventory row must have six columns: ' + line)
        name, sources, phase, status, replacement, verification = cells
        name = name.strip('`')
        if name in rows:
            raise ValueError('duplicate inventory symbol: ' + name)
        if phase not in ('0', '1', '2', '3', '4', '5'):
            raise ValueError('unassigned phase for ' + name)
        if status not in ('active', 'intrinsic', 'removed'):
            raise ValueError('invalid inventory status for ' + name)
        if not replacement or not verification:
            raise ValueError('missing replacement or verification for ' + name)
        rows[name] = {'sources': set(re.findall(r'`([^`]+)`', sources)),
                      'phase': phase, 'status': status}
    if not rows:
        raise ValueError('empty libc inventory')
    return rows


def audit(root=ROOT):
    rows = read_inventory(root / 'design/libc_inventory.md')
    found = {}
    for target in TARGETS:
        for name, sources in discover(root, target).items():
            found.setdefault(name, set()).update(sources)
    errors = []
    for name in sorted(found.keys() - rows.keys()):
        errors.append('unassigned Linux symbol: ' + name)
    for name, row in rows.items():
        if row['status'] == 'removed':
            if name in found:
                errors.append('removed Linux symbol reappeared: ' + name)
        elif name not in found:
            errors.append('mark absent symbol removed: ' + name)
        elif row['sources'] != found[name]:
            errors.append('update call-site files for ' + name + ': ' + ', '.join(sorted(found[name])))
    return errors


if __name__ == '__main__':
    errors = audit()
    for error in errors:
        print(error)
    raise SystemExit(bool(errors))
