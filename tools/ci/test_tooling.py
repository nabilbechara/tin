"""Tests for the build tooling: the Makefile and the tin command."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


def make_var(name, *overrides):
    result = subprocess.run(['make', '-s', '-C', str(ROOT), f'print-{name}', *overrides],
                            check=True, capture_output=True, text=True)
    return result.stdout.split()


class MakefileTests(unittest.TestCase):
    def test_linux_sources_have_one_linux_host_on_every_host(self):
        # Issue #11: a native Linux host listed host_linux.tin twice.
        for host in ('linux', 'darwin'):
            with self.subTest(host=host):
                sources = make_var('SELF_LINUX', f'HOST_OS={host}')
                self.assertEqual(sources.count('selfhost/host_linux.tin'), 1)
                self.assertNotIn('selfhost/host_darwin.tin', sources)
                self.assertEqual(len(sources), len(set(sources)))


if __name__ == '__main__':
    unittest.main()
