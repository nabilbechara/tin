"""Benchmark correctness, revision isolation and noisy/failing process handling."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench'))
import measure

spec = importlib.util.spec_from_file_location('http_benchmark', ROOT / 'bench/http/run_wrk.py')
http = importlib.util.module_from_spec(spec)
spec.loader.exec_module(http)
spec = importlib.util.spec_from_file_location('h2_benchmark', ROOT / 'bench/http/run_h2load.py')
h2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h2)


class BenchmarkTests(unittest.TestCase):
    def test_alternates_and_reports_median_not_minimum(self):
        order = []
        times = {'base': iter((10, 1, 3)), 'head': iter((2, 20, 4))}

        def run(command):
            name = command[0]
            order.append(name)
            return next(times[name]), (b'same\n', b'')

        with patch.object(measure, 'run_checked', side_effect=run):
            medians, samples = measure.interleaved(
                {'base': {'command': ['base']}, 'head': {'command': ['head']}}, 3)
        self.assertEqual(order, ['base', 'head', 'head', 'base', 'base', 'head'])
        self.assertEqual(medians, {'base': 3, 'head': 4})
        self.assertEqual(samples['base'], [10, 1, 3])

    def test_checks_output_on_every_repetition(self):
        results = [(1, (b'ok', b'')), (1, (b'ok', b'')), (1, (b'wrong', b''))]
        with patch.object(measure, 'run_checked', side_effect=results):
            with self.assertRaisesRegex(ValueError, 'OUTPUT MISMATCH'):
                measure.interleaved({'base': {'command': ['b']}, 'head': {'command': ['h']}}, 3)

    def test_crash_and_timeout_are_never_samples(self):
        with self.assertRaises(subprocess.CalledProcessError):
            measure.run_checked([sys.executable, '-c', 'raise SystemExit(2)'])
        with self.assertRaises(subprocess.TimeoutExpired):
            measure.run_checked([sys.executable, '-c', 'import time; time.sleep(10)'], timeout=.05)

    def test_comparison_uses_matching_library_tree_and_identical_input(self):
        with tempfile.TemporaryDirectory(prefix='tin benchmark ') as tmp:
            tmp = Path(tmp).resolve()
            for side in ('base', 'head'):
                root = tmp / side
                (root / 'bin').mkdir(parents=True)
                (root / 'toolchain/runtime').mkdir(parents=True)
                (root / 'toolchain/runtime/version').write_text(side)
                compiler = root / 'bin/tinc'
                compiler.write_text(f'''#!{sys.executable}
import os
from pathlib import Path
import sys
root = Path(os.environ['TIN_ROOT'])
assert root == Path.cwd()
assert root == Path(__file__).resolve().parents[1]
assert (root/'toolchain/runtime/version').read_text() == {side!r}
source = Path(sys.argv[-1])
(root/'compiled-source').write_text(str(source))
out = Path(sys.argv[sys.argv.index('-o')+1])
out.write_text('#!{sys.executable}\\nprint("same output")\\n')
out.chmod(0o755)
''')
                compiler.chmod(0o755)
            suite = tmp / 'input'
            suite.mkdir()
            (suite / 'one.tin').write_text('same benchmark input')
            report = tmp / 'results.json'
            result = subprocess.run([sys.executable, str(ROOT / 'bench/compare.py'),
                '--base-root', str(tmp / 'base'), '--head-root', str(tmp / 'head'),
                '--bench-dir', str(suite), '--json', str(report)],
                capture_output=True, text=True, env=dict(os.environ, TIN_ROOT='/wrong/inherited/root'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((tmp / 'base/compiled-source').read_text(), str(suite / 'one.tin'))
            self.assertEqual((tmp / 'head/compiled-source').read_text(), str(suite / 'one.tin'))
            records = json.loads(report.read_text())['results']
            self.assertEqual(len(records[0]['seconds']['base']), 7)
            self.assertEqual(len(records[0]['seconds']['head']), 7)

    def test_unknown_and_empty_suites_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'no benchmarks'):
                measure.benchmark_names(Path(tmp), [])
            with self.assertRaisesRegex(ValueError, 'unknown benchmarks'):
                measure.benchmark_names(Path(tmp), ['typo'])

    def test_wrk_parser_rejects_errors_and_missing_measurements(self):
        valid = '  99%    1.50ms\n  100 requests in 1.00s, 20KB read\nRequests/sec: 100.00\n'
        self.assertEqual(http.parse_wrk(valid)['p99_us'], 1500)
        for text in ('', 'unable to connect', valid + 'Socket errors: connect 1\n',
                     valid + 'Non-2xx or 3xx responses: 100\n', valid.replace('100.00', '0.00')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                http.parse_wrk(text)

    def test_h2load_parser_reads_both_formats_and_rejects_failures(self):
        head = ('finished in 10.00s, 1000.50 req/s, 1.00MB/s\n'
                'requests: 10005 total, 10005 started, 10005 done, 10005 succeeded, 0 failed, 0 errored, 0 timeout\n'
                'status codes: 10007 2xx, 0 3xx, 0 4xx, 0 5xx\n')
        old = head + 'time for request:       30us      2.39ms       157us        63us    87.68%\n'
        new = head + 'request     :       30us      2.39ms       150us       234us       306us       1.58ms        63us    87.68%\n'
        self.assertEqual(h2.parse_h2load(old), {'rps': 1000.5, 'requests': 10005, 'mean_us': 157})
        self.assertEqual(h2.parse_h2load(new)['mean_us'], 1580)
        for text in ('', head, old.replace(' 0 failed', ' 3 failed'), old.replace(' 0 errored', ' 1 errored'),
                     old.replace(' 0 5xx', ' 2 5xx'), old.replace('10005 succeeded', '10004 succeeded')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                h2.parse_h2load(text)

    def test_workflow_pipelines_propagate_harness_failures(self):
        workflow = (ROOT / '.github/workflows/bench-linux.yml').read_text()
        self.assertIn('defaults:\n  run:\n    shell: bash', workflow)
        result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c',
                                 'python3 -c "raise SystemExit(2)" | cat'], capture_output=True)
        self.assertEqual(result.returncode, 2)

    def test_http_body_is_checked_before_timing(self):
        http.verify_body('/json', b'{"message":"Hello, World!"}\n')
        http.verify_body('/plaintext', b'Hello, World!')
        with self.assertRaises(ValueError):
            http.verify_body('/json', b'{"message":"wrong"}')
        with self.assertRaises(ValueError):
            http.verify_body('/plaintext', b'error page')


if __name__ == '__main__':
    unittest.main()
