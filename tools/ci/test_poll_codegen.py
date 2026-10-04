"""Both native backends retain safepoints, including continue edges and @nopoll."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from suite import ROOT


class PollCodegenTests(unittest.TestCase):
    def test_polls_and_optout(self):
        compiler = ROOT / 'bin/tinc'
        if not compiler.exists():
            self.skipTest('compiler not built')
        source = '''package main
@nopoll fn kernel(n i64) i64 {
    mut total i64 = 0
    for i in 0..n {
        total += i
    }
    return total
}
fn spin(n i64) i64 {
    mut total i64 = 0
    for i in 0..n {
        if i == 3 {
            continue
        }
        total += kernel(i)
    }
    return total
}
fn main() {
    spin(10)
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'poll.tin'
            path.write_text(source)
            for arch in ('arm64', 'amd64'):
                with self.subTest(arch=arch):
                    text = subprocess.check_output([str(compiler), '-polls', '-edition', '1', '-target',
                        'linux-' + arch, '-S', '-o', str(Path(tmp) / arch), str(path)],
                        text=True, cwd=ROOT, env=dict(os.environ, TINC_POLLS='0'))
                    default = subprocess.check_output([str(compiler), '-edition', '1', '-target',
                        'linux-' + arch, '-S', '-o', str(Path(tmp) / arch), str(path)],
                        text=True, cwd=ROOT, env=dict(os.environ, TINC_POLLS='0'))
                    enabled_env = subprocess.check_output([str(compiler), '-edition', '1', '-target',
                        'linux-' + arch, '-S', '-o', str(Path(tmp) / arch), str(path)],
                        text=True, cwd=ROOT, env=dict(os.environ, TINC_POLLS='1'))
                    self.assertEqual(text, enabled_env)
                    self.assertNotIn(' # rt_bnd_poll', default)
                    self.assertNotIn('bl _rt_bnd_poll', default)
                    if arch == 'arm64':
                        def body(name):
                            return text.split('_' + name + ':', 1)[1].split('\n\t.p2align', 1)[0]
                        self.assertNotIn('[x28, #96]', body('kernel'))
                        self.assertGreaterEqual(body('spin').count('[x28, #96]'), 2)
                        self.assertIn('bl _rt_bnd_poll', body('spin'))
                    else:
                        # Resolve the function labels from the listing header.
                        def body(name):
                            match = re.search(r'^# (L\d+): ' + name + r'\n', text, re.M)
                            self.assertIsNotNone(match, text[:2000])
                            label = match.group(1)
                            section = text.split('\n' + label + ':\n', 1)[1]
                            labels = re.findall(r'^# (L\d+): ', text, re.M)
                            ends = [section.find('\n' + label + ':\n') for label in labels]
                            ends = [end for end in ends if end >= 0]
                            return section[:min(ends)] if ends else section
                        self.assertNotIn('[r15+0x60]', body('kernel'))
                        self.assertGreaterEqual(body('spin').count('[r15+0x60]'), 2)
