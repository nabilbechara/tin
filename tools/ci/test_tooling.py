"""Tests for the build tooling: the Makefile and the tin command."""
import os
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def make_env(**extra):
    env = {k: v for k, v in os.environ.items() if k != 'PREFIX'}
    env.update(extra)
    return env


def make_var(name, *overrides, env=None):
    result = subprocess.run(['make', '-s', '-C', str(ROOT), f'print-{name}', *overrides],
                            check=True, capture_output=True, text=True, env=env or make_env())
    return result.stdout.split()


def install_into(tree, *overrides, env=None):
    # Copies the Makefile and tin script into tree and runs install without building bin/tinc.
    tree.mkdir(parents=True, exist_ok=True)
    for name in ('Makefile', 'tin'):
        shutil.copy2(ROOT / name, tree / name)
    return subprocess.run(['make', '-s', '-C', str(tree), '-o', 'bin/tinc', 'install', *overrides],
                          capture_output=True, text=True, env=env or make_env())


class MakefileTests(unittest.TestCase):
    def test_linux_sources_have_one_linux_host_on_every_host(self):
        # Issue #11: a native Linux host listed host_linux.tin twice.
        for host in ('linux', 'darwin'):
            with self.subTest(host=host):
                sources = make_var('SELF_LINUX', f'HOST_OS={host}')
                self.assertEqual(sources.count('selfhost/host_linux.tin'), 1)
                self.assertNotIn('selfhost/host_darwin.tin', sources)
                self.assertEqual(len(sources), len(set(sources)))

    def test_linux_install_prefix_defaults_to_usr_local(self):
        # Issue #10: PREFIX defaulted to the Homebrew prefix on Linux too.
        self.assertEqual(make_var('PREFIX', 'HOST_OS=linux'), ['/usr/local'])
        self.assertIn(make_var('PREFIX', 'HOST_OS=darwin'), (['/opt/homebrew'], ['/usr/local']))
        self.assertEqual(make_var('PREFIX', 'HOST_OS=linux', env=make_env(PREFIX='/opt/x')), ['/opt/x'])

    def test_install_creates_missing_bin_directory(self):
        # Issue #10: a PREFIX without a bin directory made ln fail.
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory) / 'tin tree'
            prefix = Path(directory) / 'fresh prefix'
            result = install_into(tree, f'PREFIX={prefix}')
            self.assertEqual(result.returncode, 0, result.stderr)
            link = prefix / 'bin/tin'
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), (tree / 'tin').resolve())

    def test_install_expands_tilde_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / 'home'
            result = install_into(Path(directory) / 'tree', 'PREFIX=~/.local', env=make_env(HOME=str(home)))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((home / '.local/bin/tin').is_symlink())


# A stand-in for bin/tinc: logs its arguments one per line and writes an executable that prints its own.
FAKE_TINC = r"""#!/bin/sh
: > "$FAKE_TINC_LOG"
for a do printf '%s\n' "$a" >> "$FAKE_TINC_LOG"; done
out=
while [ $# -gt 0 ]; do
  case $1 in
    -o) out=$2; shift 2 ;;
    -target) shift 2 ;;
    -audit-secrets) exit 0 ;;
    *) [ -f "$1" ] || { echo "cannot open $1" >&2; exit 1; }; shift ;;
  esac
done
printf '#!/bin/sh\nfor a do printf "%%s\\n" "$a"; done\n' > "$out"
chmod +x "$out"
"""


class TinCommandTests(unittest.TestCase):
    # Issue #9: run and build split file names on spaces and expanded wildcards.
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.base = Path(self.directory.name)
        self.root = self.base / 'root'
        (self.root / 'bin').mkdir(parents=True)
        shutil.copy2(ROOT / 'tin', self.root / 'tin')
        tinc = self.root / 'bin/tinc'
        tinc.write_text(FAKE_TINC)
        tinc.chmod(0o755)
        self.work = self.base / 'work'
        self.work.mkdir()
        for name in ('hello world.tin', 'b*.tin', 'bx.tin', 'c.tin'):
            (self.work / name).write_text('package main\n')
        self.log = self.base / 'argv.log'

    def tearDown(self):
        self.directory.cleanup()

    def tin(self, *args):
        env = make_env(FAKE_TINC_LOG=str(self.log), TMPDIR=str(self.base))
        result = subprocess.run(['sh', str(self.root / 'tin'), *args], cwd=self.work,
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def tinc_args(self):
        return self.log.read_text().splitlines()

    def test_run_keeps_files_and_program_arguments(self):
        output = self.tin('run', 'hello world.tin', 'b*.tin', '--', 'a', 'b c', '*', '--', '')
        self.assertEqual(output, ['a', 'b c', '*', '--', ''])
        argv = self.tinc_args()
        self.assertEqual(argv[0], '-o')
        self.assertEqual(argv[2:], ['hello world.tin', 'b*.tin'])

    def test_run_without_program_arguments(self):
        self.assertEqual(self.tin('run', 'hello world.tin', 'c.tin'), [])
        self.assertEqual(self.tinc_args()[2:], ['hello world.tin', 'c.tin'])

    def test_build_keeps_files_options_and_output(self):
        (self.work / 'out dir').mkdir()
        self.tin('build', 'hello world.tin', '-o', 'out dir/prog', 'b*.tin', '--target', 'linux-arm64')
        self.assertEqual(self.tinc_args(), ['-target', 'linux-arm64', '-o', 'out dir/prog', 'hello world.tin', 'b*.tin'])

    def test_build_default_output_is_first_file(self):
        (self.work / 'sub dir').mkdir()
        (self.work / 'sub dir/my prog.tin').write_text('package main\n')
        self.tin('build', 'sub dir/my prog.tin', 'c.tin')
        self.assertEqual(self.tinc_args(), ['-o', 'my prog', 'sub dir/my prog.tin', 'c.tin'])
        self.assertTrue((self.work / 'my prog').exists())

    def test_single_file_form(self):
        self.assertEqual(self.tin('hello world.tin', 'x y', '*'), ['x y', '*'])
        self.assertEqual(self.tinc_args()[2:], ['hello world.tin'])

    def test_audit_secrets_passes_options_and_files(self):
        # tin audit secrets (#239) hands its options and files to tinc -audit-secrets unchanged.
        self.assertEqual(self.tin('audit', 'secrets', '-edition', '1', 'hello world.tin', 'b*.tin'), [])
        self.assertEqual(self.tinc_args(), ['-audit-secrets', '-edition', '1', 'hello world.tin', 'b*.tin'])


class PackageResolutionTests(unittest.TestCase):
    def test_vendor_precedes_library_and_lock_hashes_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / 'vendor/dep').mkdir(parents=True)
            main = project / 'main.tin'
            dep = project / 'vendor/dep/dep.tin'
            main.write_text('package main\nimport "dep"\nimport "say"\nfunc main() { say.Line(dep.Value()) }\n')
            dep.write_text('package dep\nfunc Value() i64 { return 7 }\n')
            output = project / 'program'
            env = make_env(TIN_ROOT=str(ROOT))
            command = [str(ROOT / 'bin/tinc'), '-o', str(output), str(main)]
            result = subprocess.run(command, capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            ran = subprocess.run([str(output)], capture_output=True, text=True)
            self.assertEqual(ran.stdout, '7\n')

            entries = []
            for source in (main, dep):
                relative = source.relative_to(project).as_posix()
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                entries.append(f'{digest} {relative}\n')
            (project / 'tin.lock').write_text(''.join(entries))
            result = subprocess.run(command, capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)

            dep.write_text('package dep\nfunc Value() i64 { return 8 }\n')
            result = subprocess.run(command, capture_output=True, text=True, env=env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('tin.lock hash mismatch', result.stderr)


if __name__ == '__main__':
    unittest.main()
