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
            tests = root / 'toolchain/tests/v2'
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


class AssemblyCheckTests(unittest.TestCase):
    def checks(self, text, arch='arm64'):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'x_asm.check'
            path.write_text(text)
            return suite.parse_checks(path, arch)

    def test_sections_select_one_arch(self):
        directives = self.checks('# comment\n[arm64]\nCHECK: bl A\n[amd64]\nCHECK: call B\n')
        self.assertEqual(directives, [('CHECK', 'bl A')])

    def test_lines_before_a_section_apply_everywhere(self):
        directives = self.checks('CHECK: prologue\n[amd64]\nCHECK: call B\n')
        self.assertEqual(directives, [('CHECK', 'prologue')])

    def test_ordered_check_and_scoped_check_not(self):
        self.assertTrue(suite.check_asm('a\nbl X\nc\nd', [('CHECK', 'bl X'), ('CHECK-NOT', 'blr')])[0])
        # CHECK-NOT only looks after the previous CHECK.
        self.assertTrue(suite.check_asm('blr\na\nbl X\nc', [('CHECK', 'bl X'), ('CHECK-NOT', 'blr')])[0])
        ok, why = suite.check_asm('bl X\nblr x16\n', [('CHECK', 'bl X'), ('CHECK-NOT', 'blr')])
        self.assertFalse(ok)
        self.assertIn('blr', why)

    def test_check_not_is_bounded_by_the_next_check(self):
        # Lit's scope: a pattern after the next CHECK is not this CHECK-NOT's business.
        self.assertTrue(suite.check_asm('A\nB\nX\n', [('CHECK', 'A'), ('CHECK-NOT', 'X'), ('CHECK', 'B')])[0])
        self.assertFalse(suite.check_asm('A\nX\nB\n', [('CHECK', 'A'), ('CHECK-NOT', 'X'), ('CHECK', 'B')])[0])

    def test_check_order_is_required(self):
        self.assertFalse(suite.check_asm('second first', [('CHECK', 'first'), ('CHECK', 'second')])[0])

    def test_arch_comes_from_the_target_or_the_host(self):
        self.assertEqual(suite.asm_arch('linux-amd64'), 'amd64')
        self.assertEqual(suite.asm_arch('linux-arm64'), 'arm64')
        for machine, expected in (('aarch64', 'arm64'), ('arm64', 'arm64'), ('x86_64', 'amd64'), ('AMD64', 'amd64')):
            with patch.object(suite.platform, 'machine', return_value=machine):
                self.assertEqual(suite.asm_arch(), expected)

    def test_a_bad_line_or_empty_pattern_is_an_error(self):
        with self.assertRaisesRegex(ValueError, 'not a CHECK'):
            self.checks('CHEC: oops\n')
        with self.assertRaisesRegex(ValueError, 'empty pattern'):
            self.checks('CHECK:\n')


class AsmSuiteTests(unittest.TestCase):
    """run()'s assembly branches, not just the pure checker functions."""

    def scenario(self, *, check='[arm64]\nCHECK: bl X\n[amd64]\nCHECK: bl X\n', tin=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / 'toolchain/tests/v2'
            tests.mkdir(parents=True)
            # run() insists on finding the ordinary suite too; one tiny passing case.
            (tests / 'sample.tin').write_text('package main\n')
            (tests / 'sample.out').write_text('bl X\n')
            if tin:
                (tests / 'sample_asm.tin').write_text('package main\n')
            if check is not None:
                (tests / 'sample_asm.check').write_text(check)
            with patch.object(suite, 'execute', return_value=(0, b'bl X\n', b'')), contextlib.redirect_stdout(io.StringIO()):
                return suite.run(Path('/compiler'), root=root)

    def test_matching_check_passes(self):
        self.assertTrue(self.scenario())

    def test_missing_check_fails(self):
        self.assertFalse(self.scenario(check=None))

    def test_no_directive_for_this_arch_fails(self):
        self.assertFalse(self.scenario(check='[otherarch]\nCHECK: bl X\n'))

    def test_invalid_regex_fails_without_crashing_the_suite(self):
        self.assertFalse(self.scenario(check='[arm64]\nCHECK: (unclosed\n[amd64]\nCHECK: x\n'))

    def test_check_without_a_test_fails(self):
        self.assertFalse(self.scenario(tin=False))


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
