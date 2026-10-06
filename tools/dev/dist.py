#!/usr/bin/env python3
"""Package a native Tin compiler and its source/library tree as a reproducible archive."""
import argparse
import gzip
import hashlib
import io
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ('darwin-arm64', 'linux-arm64', 'linux-amd64')
TREES = ('toolchain', 'packages', 'tools', 'examples', 'bench')


def version_name(value):
    value = value.removeprefix('v')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?', value):
        raise ValueError('Version must be MAJOR.MINOR.PATCH, optionally with a prerelease suffix')
    return value


def package(version, target, compiler, output, root=ROOT):
    version = version_name(version)
    if target not in TARGETS:
        raise ValueError('Unsupported target: ' + target)
    compiler = Path(compiler)
    if not compiler.is_file():
        raise ValueError('Compiler does not exist: ' + str(compiler))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    name = f'tin-{version}-{target}'
    archive = output / (name + '.tar.gz')
    files = {}
    for tree in TREES:
        for path in sorted((root / tree).rglob('*')):
            if path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts:
                files[path.relative_to(root).as_posix()] = path
    for filename in ('tin', 'Makefile', 'README.md', 'go.mod', 'install.sh'):
        files[filename] = root / filename
    files['bin/tinc'] = compiler
    files['toolchain/seed/tinc-' + target] = compiler
    # Normalize metadata and gzip timestamps so identical inputs produce identical archives.
    with archive.open('wb') as stream, gzip.GzipFile(fileobj=stream, mode='wb', filename='', mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode='w', format=tarfile.PAX_FORMAT) as tar:
            for filename, path in sorted(files.items()):
                data = path.read_bytes()
                info = tarfile.TarInfo(name + '/' + filename)
                info.size = len(data)
                info.mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
                tar.addfile(info, io.BytesIO(data))
            for filename, value in (('VERSION', version), ('TARGET', target)):
                data = (value + '\n').encode()
                info = tarfile.TarInfo(name + '/' + filename)
                info.size = len(data)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(archive.suffix + '.sha256').write_text(f'{digest}  {archive.name}\n')
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default=(ROOT / 'VERSION').read_text().strip())
    parser.add_argument('--target', required=True, choices=TARGETS)
    parser.add_argument('--compiler', type=Path, default=ROOT / 'bin/tinc')
    parser.add_argument('--outdir', type=Path, default=ROOT / 'bin/dist')
    args = parser.parse_args()
    print(package(args.version, args.target, args.compiler, args.outdir))


if __name__ == '__main__':
    main()
