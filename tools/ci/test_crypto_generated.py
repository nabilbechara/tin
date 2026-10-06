"""Generated crypto code matches its generators: the AES S-box circuit, the AES/GHASH leaves and the 2^255-19 field."""
import platform
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class GeneratedCrypto(unittest.TestCase):
    def test_aes_sbox(self):
        got = subprocess.run([sys.executable, str(ROOT/'tools/gen_aes_sbox.py')], capture_output=True, check=True).stdout
        self.assertEqual(got, (ROOT/'lib/seal/aes_sbox.tin').read_bytes(), 'run tools/gen_aes_sbox.py > lib/seal/aes_sbox.tin')

    def test_fe25519(self):
        got = subprocess.run([sys.executable, str(ROOT/'tools/gen_fe25519.py')], capture_output=True, check=True).stdout
        self.assertEqual(got, (ROOT/'lib/seal/fe25519.tin').read_bytes(), 'run tools/gen_fe25519.py > lib/seal/fe25519.tin')

    def test_sha256_amd64(self):
        # Runs the instruction list on a model of the SHA extensions against hashlib, then compares the text.
        subprocess.run([sys.executable, 'gen_sha256_amd64.py', '--check'], cwd=ROOT/'tools', check=True)

    @unittest.skipUnless(shutil.which('clang') and platform.system() == 'Linux', 'needs clang on Linux')
    def test_aes_hw(self):
        subprocess.run([sys.executable, 'gen_aes_hw.py', '--check'], cwd=ROOT/'tools', check=True)


if __name__ == '__main__':
    unittest.main()
