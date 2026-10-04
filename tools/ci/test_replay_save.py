"""Tests for tin replay --save-test (tools/replay_save.py, #242) and replay cases in regressions.py."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import replay_save  # noqa: E402
import regressions  # noqa: E402

KEY = bytes(range(32))


class ReplaySaveTest(unittest.TestCase):
    def test_envelope_round_trip(self):
        body = b'x' * 100
        sealed = replay_save.seal(body, KEY)
        self.assertEqual(sealed[:8], b'TINCAP\x01\x00')
        self.assertEqual(len(sealed), 8 + 16 + 100 + 32)
        self.assertEqual(replay_save.unseal(sealed, KEY), body)
        with self.assertRaisesRegex(ValueError, 'wrong key or damaged'):
            replay_save.unseal(sealed, bytes(32))
        damaged = bytearray(sealed)
        damaged[30] ^= 1
        with self.assertRaisesRegex(ValueError, 'wrong key or damaged'):
            replay_save.unseal(bytes(damaged), KEY)
        with self.assertRaisesRegex(ValueError, 'not a capsule'):
            replay_save.unseal(b'GET / HTTP/1.1\r\n\r\n', KEY)

    def save(self, root, name, issue='242'):
        work = root / 'work'
        work.mkdir(exist_ok=True)
        (work / 'cap.tcap').write_bytes(replay_save.seal(b'body', KEY))
        (work / 'main.tin').write_text('package main\n')
        (work / 'out').write_text('replay: status 200 (recorded 500)\nok\n')
        with patch.dict(os.environ, {'TIN_REPLAY_KEY': KEY.hex()}):
            replay_save.main(['replay_save.py', str(root), name, issue, str(work / 'cap.tcap'),
                              str(work / 'main.tin'), str(work / 'out')])

    def test_saves_the_program_the_rekeyed_capsule_and_the_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'tests/regressions').mkdir(parents=True)
            (root / 'tests/regressions/cases.json').write_text('[]\n')
            self.save(root, 'replay-x')
            dest = root / 'tests/regressions'
            self.assertEqual((dest / 'replay-x.tin').read_text(), 'package main\n')
            case = json.loads((dest / 'cases.json').read_text())[0]
            self.assertEqual(case['replay']['key'], replay_save.TEST_KEY)
            self.assertEqual(case['expected'], {'phase': 'run', 'exit': 0,
                                                'stdout': 'replay: status 200 (recorded 500)\nok\n'})
            capsule = (dest / 'replay-x.tcap').read_bytes()
            self.assertEqual(replay_save.unseal(capsule, bytes.fromhex(replay_save.TEST_KEY)), b'body')
            with self.assertRaisesRegex(SystemExit, 'exists already'):
                self.save(root, 'replay-x')
            with self.assertRaisesRegex(SystemExit, 'lower-case'):
                self.save(root, 'Replay X')
            with self.assertRaisesRegex(SystemExit, 'issue number'):
                self.save(root, 'replay-y', 'abc')

    def test_regressions_requires_the_capsule_of_a_replay_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / 'a.tin').write_text('package main\n')
            case = {'source': 'a.tin', 'issue': 242, 'replay': {'capsule': 'a.tcap', 'key': 'k'},
                    'expected': {'phase': 'run', 'exit': 0}}
            (dest / 'cases.json').write_text(json.dumps([case]))
            with patch.object(regressions, 'MANIFEST', dest / 'cases.json'):
                with self.assertRaisesRegex(ValueError, 'capsule file and key'):
                    regressions.load_cases()
                (dest / 'a.tcap').write_bytes(b'')
                self.assertEqual(len(regressions.load_cases()), 1)


if __name__ == '__main__':
    unittest.main()
