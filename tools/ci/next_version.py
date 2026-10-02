#!/usr/bin/env python3
"""Release versions for merges into main.

VERSION holds the base version. Every merge whose CI passes is released: the first one at
VERSION itself, later ones as the next patch of VERSION's major.minor (0.5.0, 0.5.1, ...).
Bumping VERSION's major or minor starts a new series. A prerelease VERSION (0.6.0-rc.1) is
released once; bump it for the next one.

  next_version.py next VERSION_FILE  [TAG...]   the tag to release, or nothing
  next_version.py check VERSION_FILE TAG       whether TAG is a valid release of VERSION
"""
import re
import sys

PATTERN = re.compile(r'v?(\d+)\.(\d+)\.(\d+)(-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?')


def parse(text):
    m = PATTERN.fullmatch(text.strip())
    if not m:
        raise ValueError('not a release version: %r' % text)
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) or ''


def next_tag(base, tags):
    """The tag the next merge is released as, or None when there is nothing to release."""
    major, minor, patch, pre = parse(base)
    released = []
    for t in tags:
        try:
            released.append(parse(t))
        except ValueError:
            continue
    stable = [r for r in released if not r[3]]
    newest = max(stable, default=None)
    if newest and (newest[0], newest[1]) > (major, minor):
        raise ValueError('VERSION %s is behind the latest release v%d.%d.%d' % ((base.strip(),) + newest[:3]))
    if pre:
        exact = (major, minor, patch, pre)
        return None if exact in released else 'v%d.%d.%d%s' % exact
    series = [r[2] for r in stable if (r[0], r[1]) == (major, minor)]
    if not series or max(series) < patch:
        return 'v%d.%d.%d' % (major, minor, patch)
    return 'v%d.%d.%d' % (major, minor, max(series) + 1)


def valid_release(base, tag):
    """Whether tag may be released from a tree whose VERSION is base."""
    major, minor, patch, pre = parse(base)
    t = parse(tag)
    if not tag.startswith('v'):
        return False
    if pre or t[3]:
        return t == (major, minor, patch, pre)
    return (t[0], t[1]) == (major, minor) and t[2] >= patch


def main(argv):
    if len(argv) < 3 or argv[1] not in ('next', 'check'):
        sys.exit(__doc__)
    base = open(argv[2]).read()
    if argv[1] == 'next':
        tag = next_tag(base, argv[3:])
        if tag:
            print(tag)
        return
    if len(argv) != 4 or not valid_release(base, argv[3]):
        sys.exit('%s is not a release of VERSION %s' % (argv[3] if len(argv) > 3 else '?', base.strip()))


if __name__ == '__main__':
    main(sys.argv)
