"""Keep new and reintroduced Linux imports visible, including legacy compiler syntax."""
from pathlib import Path
import tempfile
import unittest

from libc_inventory import audit, discover


class LibcInventoryTests(unittest.TestCase):
    def test_repository_inventory_is_complete(self):
        self.assertEqual(audit(), [])

    def test_platforms_comments_strings_and_legacy_declarations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'packages').mkdir()
            (root / 'toolchain/compiler').mkdir(parents=True)
            (root / 'packages/common.tin').write_text('''
// extern func commented() i64
/* extern fn block_comment(); */
var text = `extern func string_literal() i64`
extern func current() i64
extern fn legacy();
''')
            (root / 'packages/x_darwin.tin').write_text('extern func mac_only() i64')
            (root / 'packages/x_linux_arm64.tin').write_text('extern fn arm_only();')
            (root / 'packages/x_linux_amd64.tin').write_text('extern fn x64_only();')
            (root / 'packages/x_test.tin').write_text('extern fn test_only();')
            (root / 'toolchain/compiler/elf.tin').write_text('''
// el_import("commented_start")
el_import("startup")
''')
            self.assertEqual(set(discover(root)), {'current', 'legacy', 'arm_only', 'startup'})
            self.assertEqual(set(discover(root, 'linux-amd64')),
                             {'current', 'legacy', 'x64_only', 'startup'})

    def test_unassigned_and_removed_symbols_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'design').mkdir()
            (root / 'packages').mkdir()
            (root / 'toolchain/compiler').mkdir(parents=True)
            (root / 'design/libc_inventory.md').write_text(
                '| `old` | `packages/x.tin` | 2 | removed | Tin allocator | OOM check |\n')
            (root / 'packages/x.tin').write_text('extern fn old();\nextern func surprise() i64\n')
            self.assertEqual(audit(root), ['unassigned Linux symbol: surprise',
                                          'removed Linux symbol reappeared: old'])

    def test_stale_sources_and_missing_plan_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'design').mkdir()
            (root / 'packages').mkdir()
            (root / 'packages/x.tin').write_text('extern fn old();\n')
            inventory = root / 'design/libc_inventory.md'
            inventory.write_text('| `old` | `packages/stale.tin` | 2 | active | allocator | OOM |\n')
            self.assertEqual(audit(root), ['update call-site files for old: packages/x.tin'])
            inventory.write_text('| `old` | `packages/x.tin` | ? | active | allocator | OOM |\n')
            with self.assertRaisesRegex(ValueError, 'unassigned phase'):
                audit(root)


if __name__ == '__main__':
    unittest.main()
