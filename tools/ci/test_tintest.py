"""tin test: builds a package with its *_test.tin files and reports each TestXxx."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

LIB = '''package geo

// Area is the area of a w by h rectangle.
func Area(w i64, h i64) i64 {
	return w * h
}

func clampPos(x i64) i64 {
	if x < 0 {
		return 0
	}
	return x
}
'''

TESTS = '''package geo

import "crucible"

func TestArea(t mut crucible.T) {
	crucible.Equal(mut t, "2x3", Area(2, 3), 6)
}

func TestPrivate(t mut crucible.T) {
	t.True("clamp", clampPos(-1) == 0)
}
'''

FAILING = '''package geo

import "crucible"

func TestWrong(t mut crucible.T) {
	crucible.Equal(mut t, "area", Area(2, 2), 5)
}
'''

APP = '''package main

import "say"

func double(x i64) i64 {
	return 2 * x
}

func main() {
	say.Line(double(2))
}
'''

APP_TEST = '''package main

import "crucible"

func TestDouble(t mut crucible.T) {
	crucible.Equal(mut t, "double", double(21), 42)
}
'''


def tin_test(files, *args):
    with tempfile.TemporaryDirectory() as d:
        for name, text in files.items():
            (Path(d) / name).write_text(text)
        r = subprocess.run([str(ROOT / 'tin'), 'test', *args, d], capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout + r.stderr


class TinTestCommand(unittest.TestCase):
    def test_library_package_passes(self):
        code, out = tin_test({'geo.tin': LIB, 'geo_test.tin': TESTS})
        self.assertEqual(code, 0, out)
        self.assertIn('--- PASS: TestArea', out)
        self.assertIn('--- PASS: TestPrivate', out)
        self.assertIn('PASS: 2 tests', out)

    def test_failure_sets_exit_status(self):
        code, out = tin_test({'geo.tin': LIB, 'geo_test.tin': TESTS, 'wrong_test.tin': FAILING})
        self.assertEqual(code, 1, out)
        self.assertIn('--- FAIL: TestWrong', out)
        self.assertIn('area: got 4, want 5', out)

    def test_main_package(self):
        code, out = tin_test({'main.tin': APP, 'main_test.tin': APP_TEST})
        self.assertEqual(code, 0, out)
        self.assertIn('--- PASS: TestDouble', out)

    def test_no_test_files(self):
        code, out = tin_test({'geo.tin': LIB})
        self.assertEqual(code, 0, out)
        self.assertIn('no *_test.tin files', out)


if __name__ == '__main__':
    unittest.main()
