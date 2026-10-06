"""The docs checker (#227) finds edition-0 syntax and unlabeled blocks, and builds blocks as programs."""
from pathlib import Path
import tempfile
import unittest
import docs_check as dc

PACKAGES = {'say', 'tide', 'argo'}


def page(text, examples=None):
    """The problems of a tree with one docs page (and example files)."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'toolchain/docs').mkdir(parents=True)
        (root / 'examples').mkdir()
        (root / 'README.md').write_text('# Tin\n')
        (root / 'toolchain/docs/PAGE.md').write_text(text)
        for name, body in (examples or {}).items():
            (root / 'examples' / name).write_text(body)
        problems, programs, _ = dc.check_static(root)
        return problems, programs


def block(body, attrs=None, prelude=None):
    return {'line': 1, 'lang': 'tin', 'attrs': attrs or {}, 'body': body.splitlines(),
            'prelude': prelude.splitlines() if prelude else None}


class SyntaxTests(unittest.TestCase):
    def test_each_removed_form(self):
        for line in ['func f() {}', 'x := 1', 'var n i64', 'switch x {', '\tcase 1, 2:', '\tdefault:',
                     'for i := 0; i < n; i++ {', 'for _, x := range xs {', 'n++', 'xs[i]--',
                     'go serve()', 'let c chan i64', 'extern func write(fd i64) i64']:
            self.assertTrue(dc.old_forms(line), line)

    def test_edition1_is_clean(self):
        for line in ['fn f() {}', 'let x = 1', 'mut n i64 = 0', 'match x {', '\t1, 2 => "a"',
                     'for i in 0..n {', 'for i, x in xs {', 'n += 1', 'let s = "a--b"',
                     'say.Line("x := 1") // var y', 'let r = `raw ++ {}`', 'shell --flag']:
            self.assertEqual(dc.old_forms(line), [], line)

    def test_blocks_and_inline_code(self):
        problems, _ = page('Use `x := 1` here, but `switch` is a word.\n\n```tin\nfn main() {\n\tx := 1\n}\n```\n')
        self.assertTrue(any('PAGE.md:1:' in p and ':=' in p for p in problems), problems)
        self.assertTrue(any('PAGE.md:5:' in p for p in problems), problems)
        self.assertEqual(len(problems), 2, problems)

    def test_go_and_unlabeled_fences(self):
        problems, _ = page('```go\nfn main() {}\n```\n\n```\nplain\n```\n\n```go-reference\nfunc main() {}\n```\n')
        self.assertTrue(any('not ```go' in p for p in problems), problems)
        self.assertTrue(any("not 'nothing'" in p for p in problems), problems)
        self.assertEqual(len(problems), 2, problems)

    def test_old_syntax_on_purpose(self):
        text = ('<!-- docs-check: old-syntax begin -->\n| `x := 1` | `let x = 1` |\n'
                '<!-- docs-check: old-syntax end -->\n\n```tin old-syntax error\nx := 1\n```\n')
        self.assertEqual(page(text)[0], [])

    def test_examples(self):
        problems, _ = page('# p\n', {'a.tin': 'package main\n\nfunc main() {}\n'})
        self.assertTrue(any('examples/a.tin:3' in p for p in problems), problems)

    def test_errors_page_is_not_compiled_here(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'toolchain/docs').mkdir(parents=True)
            (root / 'examples').mkdir()
            (root / 'toolchain/docs/ERRORS.md').write_text('```tin\nfn main() {}\n```\n')
            problems, programs, _ = dc.check_static(root)
            self.assertEqual(problems, [])
            self.assertEqual(programs, {})


class ProgramTests(unittest.TestCase):
    def test_adds_package_imports_and_main(self):
        text = dc.program(block('fn f() {\n\tsay.Line(tide.Now())\n}'), PACKAGES)
        self.assertTrue(text.startswith('package main\n\nimport "say"\nimport "tide"\n'), text)
        self.assertIn('fn main() {}', text)

    def test_keeps_own_imports_and_main(self):
        text = dc.program(block('package main\n\nimport "say"\n\nfn main() {\n\tsay.Line(1)\n}'), PACKAGES)
        self.assertEqual(text.count('import "say"'), 1, text)
        self.assertEqual(text.count('fn main'), 1, text)

    def test_local_with_a_package_name_is_not_an_import(self):
        text = dc.program(block('fn f(argo str) {\n\t_ = argo.x\n}'), PACKAGES)
        self.assertNotIn('import "argo"', text)

    def test_body_and_prelude(self):
        text = dc.program(block('let n = work()\nsay.Line(n)', {'body': True},
                                'import "tide"\n\nfn work() i64 {\n\treturn 1\n}'), PACKAGES)
        self.assertTrue(text.startswith('package main\n\nimport "tide"\nimport "say"\n'), text)
        self.assertIn('fn work() i64', text)
        self.assertIn('fn example() ! {\n\tlet n = work()\n\tsay.Line(n)\n}', text)

    def test_library_package_has_no_main(self):
        text = dc.program(block('package geo\n\nfn Area() i64 {\n\treturn 1\n}'), PACKAGES)
        self.assertNotIn('fn main', text)

    def test_parse_prelude_and_attributes(self):
        blocks, _ = dc.parse_markdown('<!-- tin-prelude\nfn f() {}\n-->\n```tin body error=E020\nf()\n```\n'
                                      '\n```tin\nfn g() {}\n```\n')
        self.assertEqual(blocks[0]['prelude'], ['fn f() {}'])
        self.assertEqual(blocks[0]['attrs'], {'body': True, 'error': 'E020'})
        self.assertIsNone(blocks[1]['prelude'])

    def test_file_blocks_join_the_program_before(self):
        blocks, _ = dc.parse_markdown('```tin\nfn main() {}\n```\n\n```tin file=geo.tin\npackage geo\n```\n')
        programs = dc.attach_files(blocks)
        self.assertEqual(len(programs), 1)
        self.assertEqual(programs[0]['files'], [('geo.tin', 'package geo\n')])


class TreeTests(unittest.TestCase):
    def test_parse_every_page(self):
        for path in dc.doc_pages(dc.ROOT):
            dc.parse_markdown(path.read_text())


if __name__ == '__main__':
    unittest.main()
