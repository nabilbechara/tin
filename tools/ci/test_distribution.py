"""Archive reproducibility and installer integrity, upgrades, and paths with spaces."""
import importlib.util
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('tin_dist', ROOT / 'tools/dev/dist.py')
dist = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dist)

FAKE_COMPILER = '''#!/bin/sh
while [ "$#" -gt 0 ]; do
  case "$1" in -o) out=$2; shift 2 ;; *) shift ;; esac
done
printf '#!/bin/sh\\necho "Tin installation verified"\\n' > "$out"
chmod +x "$out"
'''


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='tin distribution ')
        self.base = Path(self.directory.name)
        self.root = self.base / 'source'
        self.root.mkdir()
        for name in ('tin', 'Makefile', 'README.md', 'go.mod', 'install.sh'):
            shutil.copy2(ROOT / name, self.root / name)
        (self.root / 'lib').mkdir()
        (self.root / 'lib/runtime.tin').write_text('// library\n')
        self.compiler = self.base / 'compiler'
        self.compiler.write_text(FAKE_COMPILER)
        self.compiler.chmod(0o755)
        arch = {'aarch64': 'arm64', 'x86_64': 'amd64'}.get(platform.machine(), platform.machine())
        self.target = ('darwin' if platform.system() == 'Darwin' else 'linux') + '-' + arch
        self.releases = self.base / 'releases'
        self.install = self.base / 'installed tin'

    def tearDown(self):
        self.directory.cleanup()

    def release(self, version='0.4.0'):
        output = self.releases / ('v' + version)
        archive = dist.package(version, self.target, self.compiler, output, self.root)
        (output / 'SHA256SUMS').write_bytes(archive.with_suffix('.gz.sha256').read_bytes())
        return archive

    def run_install(self, version):
        return subprocess.run(['sh', str(ROOT / 'install.sh'), version], capture_output=True, text=True,
                              env=dict(os.environ, TIN_INSTALL_DIR=str(self.install),
                                       TIN_RELEASE_BASE_URL=self.releases.as_uri()))

    def test_archive_is_reproducible_and_self_contained(self):
        first = self.release()
        second = dist.package('v0.4.0', self.target, self.compiler, self.base / 'second', self.root)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with tarfile.open(first) as archive:
            root = f'tin-0.4.0-{self.target}/'
            self.assertEqual(archive.extractfile(root + 'VERSION').read(), b'0.4.0\n')
            self.assertEqual(archive.extractfile(root + 'TARGET').read().decode().strip(), self.target)
            self.assertEqual(archive.getmember(root + 'bin/tinc').mode, 0o755)
            self.assertEqual(archive.extractfile(root + 'seed/tinc-' + self.target).read(), self.compiler.read_bytes())
            self.assertIn(root + 'lib/runtime.tin', archive.getnames())

    def test_install_upgrade_preserves_old_version(self):
        self.release()
        result = self.run_install('v0.4.0')
        self.assertEqual(result.returncode, 0, result.stderr)
        first = (self.install / 'bin/tin').resolve()
        self.release('0.4.1')
        result = self.run_install('0.4.1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(first.exists())
        self.assertNotEqual((self.install / 'bin/tin').resolve(), first)
        self.assertTrue((self.install / 'bin/tinc').is_symlink())

    def test_bad_checksum_does_not_change_existing_install(self):
        self.release()
        self.assertEqual(self.run_install('0.4.0').returncode, 0)
        current = (self.install / 'bin/tin').resolve()
        archive = self.release('0.4.1')
        archive.write_bytes(archive.read_bytes() + b'tampered')
        result = self.run_install('0.4.1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('checksum mismatch', result.stderr)
        self.assertEqual((self.install / 'bin/tin').resolve(), current)

    def test_invalid_version_cannot_escape_install_directory(self):
        for value in ('../../bad', '0.4.0/other', '0.4.0;touch bad'):
            with self.subTest(value=value):
                self.assertNotEqual(self.run_install(value).returncode, 0)
        self.assertFalse(self.install.exists())


if __name__ == '__main__':
    unittest.main()
