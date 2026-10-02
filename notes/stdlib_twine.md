# stdlib: twine (strings) and glyph (utf8)

Built against the frozen `bin/tinc_agents`; output dir `bin/agent_twine/`.
Tests: `tests/v2/twine.tin` + `.out` (34 lines), `tests/v2/glyph.tin` + `.out` (33 lines); every
line hand-checked against Go's `strings` / `unicode/utf8` semantics. The `.out` files are the
program output piped through `sort`, as the primer specifies.

## twine (package twine, lib/twine.tin) — imports glyph

Search:
- `IndexByte(s str, c u8) i64`, `LastIndexByte(s str, c u8) i64`
- `Index(s, sub str) i64` (0 for empty sub), `LastIndex(s, sub str) i64` (len(s) for empty sub)
- `Contains(s, sub str) bool`, `ContainsByte(s str, c u8) bool`
- `HasPrefix(s, prefix str) bool`, `HasSuffix(s, suffix str) bool`
- `Count(s, sub str) i64` (non-overlapping; `RuneCount(s)+1` for empty sub)
- `Cut(s, sep str) (before str, after str, found bool)`
- `Compare(a, b str) i64` (-1/0/1 bytewise), `IndexRune(s str, r i32) i64`, `ContainsRune(s str, r i32) bool`
- `IndexAny(s, chars str) i64` (first rune of s that is in chars), `ContainsAny(s, chars str) bool`

Split/join:
- `Split(s, sep str) []str` (empty sep explodes into runes), `SplitN(s, sep str, n i64) []str`
  (n < 0 all, n == 0 empty slice), `Fields(s str) []str` (ASCII white space), `Join(elems []str, sep str) str`

Transform:
- `Repeat(s str, count i64) str` (empty for count <= 0)
- `Replace(s, old, repl str, n i64) str` (n < 0 all; empty old inserts at every rune boundary), `ReplaceAll`
- `ToLower(s str) str`, `ToUpper(s str) str` — ASCII only, return s itself when nothing changes
- `Trim/TrimLeft/TrimRight(s, cutset str) str` (cutset is a set of runes), `TrimSpace(s str) str`
  (ASCII space, \t \n \v \f \r, plus U+0085 and U+00A0), `TrimPrefix`, `TrimSuffix`
- `EqualFold(s, t str) bool` — Unicode simple folding (SimpleFold orbits)

Builder (struct holding `buf []u8`; `Builder{}` is usable, `NewBuilder(n)` preallocates):
- mut: `Str(s str)`, `Byte(c u8)`, `Rune(r i32)`, `Int(v i64)`, `Reset()`
- read: `Len() i64`, `String() str` (copies), `Bytes() []u8` (aliases)

### Design notes
- `Index`/`indexAt` use libc `memchr` (declared `extern` in the lib) to find the first byte, then
  `memcmp` for the rest; `HasPrefix`/`HasSuffix`/`LastIndex` use `memcmp` on the raw bytes
  (`cast(i64, s)+8`). All entry points guard len 0 before touching the pointer (an empty str may be nil).
- `Join`/`Repeat`/`ToLower`/`ToUpper` build the result directly with `rt_str_new` + `memcpy`/`store8`
  (one allocation, no []u8 -> str copy). `Replace` and the Builder use the `append(b, s...)` idiom.
- Only `memchr` is declared here; `memcmp`/`memcpy` come from lib/runtime.tin's externs, which are
  visible to all packages.
- `Replace` uses `repl` instead of `new` as the parameter name to avoid any keyword clash.

### Known gaps
- `ToLower`/`ToUpper` are ASCII-only (non-ASCII bytes pass through unchanged); `EqualFold` folds
  ASCII + Latin-1 only (no Kelvin sign, no full Unicode case folding).
- `Fields` is ASCII white space only (no U+0085/U+00A0 split), unlike Go's `Fields`.
- No `IndexAny`, `Map`, `Title`, `Compare`, `IndexFunc` (no closures in Tin; use loops).
- `Trim*` with an invalid UTF-8 byte in s matches it as a raw byte against the cutset.

## glyph (package glyph, lib/glyph.tin)

- consts `RuneError = 0xfffd`, `MaxRune = 0x10ffff`, `UTFMax = 4`
- `ValidRune(r i32) bool`, `RuneLen(r i32) i64` (-1 for invalid)
- `EncodeRune(b mut []u8, r i32) i64` — **appends** to b (Tin append mutates in place) and returns
  the byte count; invalid runes encode as RuneError. `RuneStr(r i32) str` for a one-rune str.
- `DecodeRune(s str, i i64) (i32, i64)` — rune and size at byte i; `(RuneError, 1)` for a bad byte,
  `(RuneError, 0)` at/after the end. Rejects overlongs, surrogates and > MaxRune like Go.
- `DecodeLastRune(s str, end i64) (i32, i64)` — last rune of `s[0:end]`.
- `RuneCount(s str) i64` (each invalid byte counts as one), `Valid(s str) bool`
- `RuneStart(b u8) bool` (not a continuation byte), `FullRune(s str, i i64) bool` (s[i:] begins with a
  complete rune; already-invalid bytes count as complete, like Go)
- The classification and case functions are Unicode's, from Go's tables: see `lib/glyph/unicode.tin`
  and the "glyph: Unicode" row of notes/stdlib_verified.md.

### Known gaps
- `EncodeRune` appends rather than writing at index 0 as Go does; there is no in-place variant.

## Compiler bug found
`len(f())` where `f` returns `[]u8` nested directly in `say.Line(...)` args jumps to address
0x100000000 (SIGILL). See notes/compiler_bugs_twine.md; the test assigns the slice to a local first.
