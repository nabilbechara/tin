import unittest

from next_version import next_tag, valid_release


class NextVersion(unittest.TestCase):
    def test_first_release_of_a_series_is_version_itself(self):
        self.assertEqual(next_tag('0.5.0\n', ['v0.4.0', 'v0.4.3']), 'v0.5.0')

    def test_later_merges_take_the_next_patch(self):
        self.assertEqual(next_tag('0.4.0', ['v0.4.0']), 'v0.4.1')
        self.assertEqual(next_tag('0.4.0', ['v0.4.0', 'v0.4.1', 'v0.4.7', 'v0.3.9']), 'v0.4.8')

    def test_a_higher_patch_in_version_is_respected(self):
        self.assertEqual(next_tag('0.4.5', ['v0.4.0', 'v0.4.1']), 'v0.4.5')

    def test_prerelease_once(self):
        self.assertEqual(next_tag('0.6.0-rc.1', ['v0.5.2']), 'v0.6.0-rc.1')
        self.assertIsNone(next_tag('0.6.0-rc.1', ['v0.5.2', 'v0.6.0-rc.1']))

    def test_prerelease_tags_do_not_count_as_patches(self):
        self.assertEqual(next_tag('0.6.0', ['v0.6.0-rc.1']), 'v0.6.0')

    def test_other_tags_are_ignored(self):
        self.assertEqual(next_tag('0.4.0', ['v0.4.0', 'nightly', 'v1.x']), 'v0.4.1')

    def test_version_behind_latest_release_is_an_error(self):
        with self.assertRaises(ValueError):
            next_tag('0.4.0', ['v0.5.0'])

    def test_valid_release(self):
        self.assertTrue(valid_release('0.4.0', 'v0.4.0'))
        self.assertTrue(valid_release('0.4.0', 'v0.4.9'))
        self.assertFalse(valid_release('0.4.2', 'v0.4.1'))
        self.assertFalse(valid_release('0.4.0', 'v0.5.0'))
        self.assertFalse(valid_release('0.4.0', '0.4.1'))
        self.assertTrue(valid_release('0.6.0-rc.1', 'v0.6.0-rc.1'))
        self.assertFalse(valid_release('0.6.0-rc.1', 'v0.6.0-rc.2'))
        self.assertFalse(valid_release('0.4.0', 'v0.4.1-rc.1'))


if __name__ == '__main__':
    unittest.main()
