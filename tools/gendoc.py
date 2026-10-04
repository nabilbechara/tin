#!/usr/bin/env python3
"""Generate docs/STDLIB.md from the comments in lib/*/ (run from the repo root)."""
import os, re

SKIP = {"runtime", "std", "fmt", "say"}
ORDER = ["say", "fault", "argo", "io", "anvil", "hearth", "relay", "wire", "twine", "glyph", "mint", "gauge", "bits",
         "link", "ore", "flume", "quarry", "trail", "lever", "tide", "dice", "sift", "atlas", "cairn", "stamp",
         "seal", "herald", "crucible", "constraints", "redis", "mysql", "postgres", "websocket"]
ROLE = {"say": "formatting and printing (fmt)", "fault": "fault chains and standard sentinels (errors)", "argo": "JSON (encoding/json)", "anvil": "HTTP/1.1 server (net/http)",
        "hearth": "cores and threads (runtime)", "relay": "messages between cores (channels)", "wire": "TCP and HTTP client (net)",
        "twine": "strings (strings)", "glyph": "UTF-8 and Unicode (unicode/utf8, unicode)", "mint": "number and string conversion (strconv)",
        "gauge": "math (math)", "bits": "bit counting and manipulation (math/bits)", "link": "URLs and their escaping (net/url)", "io": "streaming shapes (io)", "ore": "byte slices (bytes)", "flume": "buffered I/O (bufio)",
        "quarry": "files, environment, process (os)", "trail": "paths (path/filepath)", "lever": "command-line flags (flag)",
        "tide": "time (time)", "dice": "random numbers (math/rand)", "sift": "sorting, searching and the generic slice functions (sort, slices, cmp)", "atlas": "functions on maps (maps)",
        "cairn": "containers (container/heap, sets, LRU)", "stamp": "hashes and checksums (hash/*)",
        "seal": "crypto and encodings (crypto/sha256, hmac, encoding/hex, base64)", "herald": "logging (log/slog)",
        "crucible": "testing helpers (testing)", "constraints": "named generic constraint shapes",
        "redis": "Redis client (go-redis)",
        "mysql": "MySQL client (database/sql with go-sql-driver/mysql)",
        "postgres": "PostgreSQL client (database/sql with pgx)",
        "websocket": "WebSocket server and client (gorilla/websocket)"}

def package_files(name):
    """The files of lib/<name>/ that document the package: every .tin file except tests and the
    per-OS and per-CPU parts, in name order."""
    directory = f"lib/{name}"
    if not os.path.isdir(directory):
        return []
    return [f"{directory}/{f}" for f in sorted(os.listdir(directory))
            if f.endswith(".tin") and not f.endswith("_test.tin")
            and not re.search(r"_(darwin|linux)(_(arm64|amd64))?\.tin$", f)]

def parse(path):
    lines = open(path).read().split("\n")
    pkgdoc, items, comment = [], [], []
    seen_pkg = False
    for line in lines:
        if line.startswith("//"):
            comment.append(line[2:])
            continue
        if line.startswith("package "):
            pkgdoc = comment[:]
            seen_pkg = True
            comment = []
            continue
        m = re.match(r"^func (\([a-z]+ (mut )?[A-Za-z0-9_\[\], ]+\) )?([A-Z][A-Za-z0-9_]*)(\[[^\]]*\])?\((.*)$", line)
        t = re.match(r"^type ([A-Z][A-Za-z0-9_]*)", line)
        sh = re.match(r"^shape ([A-Z][A-Za-z0-9_]*)", line)
        c = re.match(r"^const ([A-Z][A-Za-z0-9_]*)", line)
        if m and seen_pkg:
            sig = line[len("func "):].rstrip(" {")
            items.append(("func", sig, " ".join(c.strip() for c in comment)))
        elif t and seen_pkg:
            items.append(("type", line.rstrip(" {"), " ".join(c.strip() for c in comment)))
        elif sh and seen_pkg:
            items.append(("shape", line.rstrip(" {"), " ".join(c.strip() for c in comment)))
        elif c and seen_pkg:
            items.append(("const", line, " ".join(c.strip() for c in comment)))
        if not line.startswith("//"):
            comment = []
    return pkgdoc, items

out = ["# Tin standard library", "", "Generated from the comments in `lib/*/` by `tools/gendoc.py`.", ""]
out.append("| package | role (Go equivalent) |")
out.append("|---|---|")
for p in ORDER:
    out.append(f"| [{p}](#{p}) | {ROLE[p]} |")
out.append("")
out.append("## say")
out.append("")
out.append("Built into the compiler (formatting by static type, no reflection): `say.Line(a, b...)`, `say.Text(...)`, "
           "`say.Out(format, ...)`, `say.Fmt(format, ...) str`, `say.Str(x) str`, `say.Fault(format, ...) fault`, "
           "`say.To(fd, ...)`, `say.LineTo(fd, ...)`. See docs/LANGUAGE.md.")
out.append("")
for p in ORDER:
    if p == "say":
        continue
    files = package_files(p)
    if not files:
        continue
    doc, items = [], []
    for path in files:
        file_doc, file_items = parse(path)
        doc = doc or file_doc
        items += file_items
    out.append(f"## {p}")
    out.append("")
    if doc:
        text, code = [], []
        def flush_text():
            if text:
                out.append(" ".join(text))
                out.append("")
                text.clear()
        for c in doc:
            if c.startswith("\t"):
                flush_text()
                code.append(c[1:])
            else:
                if code:
                    out.append("```go")
                    out.extend(code)
                    out.append("```")
                    out.append("")
                    code = []
                if c.strip():
                    text.append(c.strip())
                else:
                    flush_text()
        flush_text()
        if code:
            out.append("```go")
            out.extend(code)
            out.append("```")
            out.append("")
    for kind, sig, cm in items:
        out.append(f"- `{sig}`" + (f": {cm}" if cm else ""))
    out.append("")
open("docs/STDLIB.md", "w").write("\n".join(out))
print(sum(1 for l in out if l.startswith("- ")), "entries")
