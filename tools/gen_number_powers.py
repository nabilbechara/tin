#!/usr/bin/env python3
"""Regenerate the packed, rounded-down 128-bit Eisel-Lemire powers using integers."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def table():
    packed = bytearray()
    for exponent in range(-348, 348):
        if exponent < 0:
            denominator = 10 ** -exponent
            value = (1 << (127 + denominator.bit_length())) // denominator
        else:
            value = 10 ** exponent
            shift = value.bit_length() - 128
            value = value >> shift if shift >= 0 else value << -shift
        packed.extend(value.to_bytes(16, 'little'))
    return ''.join('\\x%02x' % byte for byte in packed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    source = ROOT / 'lib/runtime/number.tin'
    text = source.read_text()
    pattern = r'(fn num_power\(exp i64\) i64 \{\n\tlet p = \(cast\(i64, ")[^"\n]*("\) \+ 8\))'
    match = re.search(pattern, text)
    if not match:
        raise ValueError('packed power table not found')
    replacement = table()
    if args.check:
        if text[match.start(1) + len(match.group(1)):match.start(2)] != replacement:
            raise SystemExit('number power table differs from exact integer regeneration')
    else:
        source.write_text(text[:match.end(1)] + replacement + text[match.start(2):])


if __name__ == '__main__':
    main()
