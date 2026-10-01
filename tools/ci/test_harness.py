"""Test failure propagation itself: a green CI must mean the programs really passed."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import regressions
import suite


class SuiteTests(unittest.TestCase):
    def scenario(self, *, negative=False, golden=True, outcomes=()):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / 'tests/v2'
            tests.mkdir(parents=True)
            source = tests / ('sample_bad.tin' if negative else 'sample.tin')
            source.write_text('package main\n')
            if golden:
                source.with_suffix('.err' if negative else '.out').write_text('expected\n')
            with patch.object(suite, 'execute', side_effect=outcomes), contextlib.redirect_stdout(io.StringIO()):
                return suite.run(Path('/compiler'), root=root)

    def test_positive_pass(self):
        self.assertTrue(self.scenario(outcomes=[(0, b'', b''), (0, b'expected\n', b'')]))

    def test_output_then_crash_is_failure(self):
        self.assertFalse(self.scenario(outcomes=[(0, b'', b''), (-11, b'expected\n', b'')]))

    def test_timeout_is_failure_even_with_expected_output(self):
        self.assertFalse(self.scenario(outcomes=[(0, b'', b''), (124, b'expected\n', b'')]))

    def test_missing_golden_is_failure(self):
        self.assertFalse(self.scenario(golden=False))

    def test_compile_failure_cannot_run_stale_binary(self):
        self.assertFalse(self.scenario(outcomes=[(1, b'', b'compile failed')]))

    def test_negative_must_reject(self):
        self.assertFalse(self.scenario(negative=True, outcomes=[(0, b'', b'expected\n')]))

    def test_negative_crash_does_not_count_as_rejection(self):
        self.assertFalse(self.scenario(negative=True, outcomes=[(-11, b'', b'expected\n')]))

    def test_negative_diagnostics_must_match(self):
        self.assertFalse(self.scenario(negative=True, outcomes=[(1, b'', b'wrong\n')]))
        self.assertTrue(self.scenario(negative=True, outcomes=[(1, b'', b'expected\n')]))

    def test_real_process_timeout(self):
        result = suite.execute([sys.executable, '-c', 'import time; time.sleep(10)'], timeout=.05)
        self.assertEqual(result[0], 124)


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.case = {'expected': {'phase': 'run', 'exit': 0, 'stdout': 'ok\n'},
                     'known_failure': {'phase': 'run', 'exit': -11, 'stdout': ''}}

    def test_known_failure_is_narrow(self):
        self.assertEqual(regressions.classify(self.case, {'phase': 'run', 'exit': -11, 'stdout': ''}), 'XFAIL')
        self.assertEqual(regressions.classify(self.case, {'phase': 'run', 'exit': 124, 'stdout': ''}), 'FAIL')
        self.assertEqual(regressions.classify(self.case, {'phase': 'compile', 'exit': -11, 'stdout': ''}), 'FAIL')

    def test_fix_requires_promotion_and_then_stays_required(self):
        actual = {'phase': 'run', 'exit': 0, 'stdout': 'ok\n'}
        self.assertEqual(regressions.classify(self.case, actual), 'XPASS')
        del self.case['known_failure']
        self.assertEqual(regressions.classify(self.case, actual), 'PASS')
        self.assertEqual(regressions.classify(self.case, {'phase': 'run', 'exit': -11}), 'FAIL')

    def test_manifest_discovers_all_tests(self):
        self.assertGreater(len(regressions.load_cases()), 0)

    def test_closed_issue_blocks_exemption(self):
        response = io.BytesIO(json.dumps({'state': 'closed'}).encode())
        with patch.object(regressions.urllib.request, 'urlopen', return_value=response):
            with self.assertRaisesRegex(ValueError, 'Closed issues'):
                regressions.audit([dict(self.case, issue=2)])


if __name__ == '__main__':
    unittest.main()
