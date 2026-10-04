"""The diagnostic-code checker (#244) finds every kind of disagreement, and the tree has none."""
from pathlib import Path
import tempfile
import unittest
import diagnostics_check as dc

ENTRY = '''## E5xx Generics

### E501 NOT_GENERIC

Rule.

```tin
package main
```

```text
example.tin:1:1: error E501 NOT_GENERIC: 'P' is not a generic type
```
'''


class DiagnosticsTests(unittest.TestCase):
    def problems(self, doc, source='err_code(pos, "E501 NOT_GENERIC");\n', err=''):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docs').mkdir()
            (root / 'docs/ERRORS.md').write_text('# Compiler diagnostics\n\n' + doc)
            (root / 'selfhost').mkdir()
            (root / 'selfhost/x.tin').write_text(source)
            (root / 'tests/v2').mkdir(parents=True)
            (root / 'tests/v2/a_bad.err').write_text(err)
            problems, _, coded, uncoded = dc.check_static(root)
            return problems, coded, uncoded

    def test_agreement(self):
        err = 'a.tin:1:1: error E501 NOT_GENERIC: x\na.tin:2:1: error: y\n'
        self.assertEqual(self.problems(ENTRY, err=err), ([], 1, 1))

    def test_undocumented_code(self):
        problems, _, _ = self.problems(ENTRY, source='err_code(pos, "E501 NOT_GENERIC");\nerr_code(pos, "E502 COUNT");\n')
        self.assertTrue(any('E502 COUNT is not documented' in p for p in problems), problems)

    def test_wrong_name(self):
        problems, _, _ = self.problems(ENTRY, source='err_code(pos, "E501 NOT_TEMPLATE");\n')
        self.assertTrue(any('E501 is NOT_GENERIC' in p for p in problems), problems)

    def test_unused_code_must_be_retired(self):
        problems, _, _ = self.problems(ENTRY, source='')
        self.assertTrue(any('not printed by the compiler' in p for p in problems), problems)
        retired = ENTRY.split('Rule.')[0] + 'Retired: replaced by E502.\n'
        self.assertEqual(self.problems(retired, source='')[0], [])

    def test_retired_code_is_never_reused(self):
        retired = ENTRY.split('Rule.')[0] + 'Retired: replaced by E502.\n'
        problems, _, _ = self.problems(retired)
        self.assertTrue(any('never reused' in p for p in problems), problems)

    def test_expected_diagnostic_must_be_documented(self):
        problems, _, _ = self.problems(ENTRY, err='a.tin:1:1: error E599 OTHER: x\n')
        self.assertTrue(any('E599 OTHER is not documented' in p for p in problems), problems)

    def test_entry_needs_example_and_order(self):
        second = ENTRY.replace('## E5xx Generics\n\n', '').replace('```tin\npackage main\n```\n\n', '')
        problems, _, _ = self.problems(ENTRY + '\n' + second)
        self.assertTrue(any('code documented twice' in p for p in problems), problems)
        self.assertTrue(any('code order' in p for p in problems), problems)
        self.assertTrue(any('one ```tin example' in p for p in problems), problems)

    def test_entry_in_wrong_group(self):
        problems, _, _ = self.problems(ENTRY.replace('## E5xx', '## E4xx'))
        self.assertTrue(any('## E5xx' in p for p in problems), problems)

    def test_tree_agrees(self):
        problems, entries, _, _ = dc.check_static()
        self.assertEqual(problems, [])
        self.assertTrue(entries)


if __name__ == '__main__':
    unittest.main()
