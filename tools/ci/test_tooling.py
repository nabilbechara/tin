"""Tests for the build tooling: the Makefile and the tin command."""
import os
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


if __name__ == '__main__':
    unittest.main()
