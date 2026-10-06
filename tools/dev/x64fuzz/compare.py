#!/usr/bin/env python3
"""Compare the x64fuzz listing with objdump's disassembly of the same bytes.

Usage: compare.py OURS.txt OBJDUMP.txt [MAX_REPORTED]

Both listings are normalized to one instruction per line with single spaces and lower-case
text (objdump's addresses, byte columns, continuation lines and `# target` comments are
dropped), then compared instruction by instruction.
"""
import re
import sys

LINE = re.compile(r"^\s*([0-9a-f]+):\t([0-9a-f ]+)\t(.*)$")


def norm(text):
    return " ".join(text.split("#")[0].lower().split())


def read_ours(path):
    with open(path) as f:
        return [norm(line) for line in f if line.strip()]


def read_objdump(path):
    out = []
    with open(path) as f:
        for line in f:
            m = LINE.match(line.rstrip("\n"))
            if not m:
                continue  # headers and the byte-only continuation lines of long instructions
            out.append((int(m.group(1), 16), m.group(2).strip(), norm(m.group(3))))
    return out


def main():
    ours = read_ours(sys.argv[1])
    theirs = read_objdump(sys.argv[2])
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    mismatches = 0
    for i in range(max(len(ours), len(theirs))):
        a = ours[i] if i < len(ours) else "<missing>"
        b = theirs[i] if i < len(theirs) else (0, "", "<missing>")
        if a != b[2]:
            mismatches += 1
            if mismatches <= limit:
                print(f"#{i} @{b[0]:#x} [{b[1]}]\n  ours:    {a}\n  objdump: {b[2]}")
    print(f"x64fuzz: {len(ours)} instructions printed, {len(theirs)} disassembled, {mismatches} mismatches")
    sys.exit(1 if mismatches else 0)


if __name__ == "__main__":
    main()
