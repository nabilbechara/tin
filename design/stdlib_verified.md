# Stdlib verification against Go (bench/ref/NAME/main.go)

| package | Go reference | result |
|---|---|---|
| mint | strconv | identical on all cases |
| gauge | math, math/bits | the transcendental functions are Tin ports of Go's algorithms: see "gauge: the corpus check" below |
| tide | time | identical |
| squash (Deflate, Inflate, Gzip, Gunzip, Zlib, Unzlib) | compress/flate, compress/gzip, compress/zlib (`bench/ref/squash`) | identical on 117 lines: Go's and Tin's vectors decoded by both, round trips of 7 inputs at 4 levels in 3 formats, damaged, cut and foreign input, limits; one changed constant of the length table changes 18 lines. Snappy, LZ4 and Zstandard have no Go standard package: checked against the reference tools |
| dice | same algorithms in Go | identical |
| sift | slices/sort, Each (`bench/ref/closures/main.go`) | identical |
| sift (generic: Sort, SortFunc, SortStableFunc, Insert, Delete, Compact, BinarySearch ...) | slices, cmp (`bench/ref/sift/generic.go`) | identical on 149 lines, including the order of equal elements after SortFunc on 119 inputs of 7 shapes up to 20,000 elements; the port is Go's pdqsort, and changing one shift constant in it breaks 16 lines |
| bits | math/bits (`bench/ref/bits`, generated with `tests/v2/bits.tin` from one description) | identical on all 37 function hashes: every function at 8, 16, 32 and 64 bits, exhaustive for 8 and 16 bits, about 40,000 values at 32 bits and 20,000 at 64; changing one comparison in `Div64`'s correction loop breaks 2 of them |
| link | net/url (`bench/ref/link`, generated with `tests/v2/link.tin` from one description) | identical on all 813 lines: 159 URLs through Parse and 14 through ParseRequestURI (every field and method, fault messages included: bad escapes, IPv6 literals and zones, ports, userinfo, opaque and rootless forms, CTL bytes), 30 strings through the four escape functions, 246 references resolved (50 against the RFC 3986 section 5.4 base, 196 more across 14 bases and 14 references), 23 JoinPath cases, 27 queries and a Values sequence; five mutations (OmitHost, ForceQuery in ResolveReference, the path-segment escape set, the IPv6 group length, the postgres host list) each break 1 to 4 lines |
| glyph (Unicode: `bench/ref/unicode`, generated with `tests/v2/unicode.tin` from one description) | unicode, strconv.Quote | identical on all 258 lines: for every rune up to U+10FFFF the 13 classification functions, ToUpper, ToLower, ToTitle and SimpleFold (hash of the results), every one of the 236 category, script and property tables over U+0000 to U+323AF, the orbit cases, the out-of-range edges, and `mint.Quote` and `say.Fmt("%q")` of every valid rune against `strconv.Quote`; five mutations (the upper/lower alternation bit, the stride test, NBSP in IsSpace, the fold orbit lookup, one byte of Zs) each break 1 to 98 lines |
| twine (Unicode and the new functions: `bench/ref/twine`, generated with `tests/v2/twine_unicode.tin`) | strings | identical on all 3,544 lines: 38 texts (ASCII, Latin-1, Greek, Turkish, Cyrillic, Arabic, CJK, combining marks, emoji, every kind of space, invalid UTF-8) through ToUpper, ToLower, ToTitle, Title, Fields, FieldsFunc, Map, the Trim family, Index/LastIndexFunc, ContainsFunc, Split/SplitAfter(N), ToValidUTF8, Lines, CutPrefix/Suffix, LastIndexAny, Trim with 11 cutsets, IndexRune with 10 runes, 24 EqualFold pairs and 13 Replacer lists; mutations that remove the Replacer empty-match rule or the fold loop bound hang or break it |
| closures (capture semantics: `bench/ref/closures` and `bench/ref/closures2`, with `tests/v2/closures.tin` and `closures2.tin`) | language | identical to Go on loop variables per iteration (3-clause and range), defer with captures, nested closures sharing variables, struct fields and range-var structs, shadowing, `keep` of a closure that captures a kept slice, and `sift.SortFunc` (51 comparisons, as Go), `twine.Map` and `FieldsFunc` with capturing literals; one frame-resident closure measured at 0 pool bytes |
| shapes (`bench/ref/shapes/main.go`, with `tests/v2/shapes_dispatch.tin`) | language (interfaces) | identical on all 10 lines: structural `Reader`, `Writer` and composed `ReadWriter`, `Copy[R io.Reader, W io.Writer]` through static specialization, `Log(w dyn io.Writer, ...)` through a Go interface / Tin method table, ordered values constrained by `sift.Ordered`, and `Sized` on `Stack[i64]`. Breaking one constant in the dispatched path breaks the output comparison. `constraints.Any` and `constraints.Comparable` are imported library shapes, covered by `tests/v2/constraints.tin`; negatives verify incomparable slices are rejected, bare `any`/`comparable` are not syntax, and bool is outside `sift.Ordered`. The dynamic assembly check finds one indirect call and no allocation call on arm64 and amd64. `bench/dispatch/dyn.tin` reports zero pool bytes; four runs measured a median 4.66 ns/op dynamic and 2.95 ns/op direct on Apple M3 Pro. Missing/mis-signed shape methods include method-name diagnostics and fix-it text. Regression cases for #141 cover the missing method fix-it and request-region escape rejection. Map values and `!dyn` results remain deferred. |
| atlas | maps (`bench/ref/atlas`) | identical; Keys and Values come back in insertion order, so the test sorts them |
| cairn | hand-written Go equivalents | identical |
| trail | path/filepath | identical |
| quarry | os | identical except stderr interleaving and naming fdopendir instead of open in one error |
| lever | flag | identical except: a value that fails to parse leaves the flag unchanged (Go overwrites it with a zero value) |
| twine, glyph | strings, unicode/utf8 | checked by hand against Go semantics |


## Deliberate difference since v0.5 (!T results)

A failing call returns zero values with its fault. Go's strconv returns the clamped value
(MaxInt64, ±Inf, MaxUint64) together with ErrRange; mint.Atoi, ParseInt, ParseUint and
ParseFloat now return 0 with the range fault. tests/v2/mint.out records this.


## gauge: the corpus check

`bench/ref/gauge/corpus.go` and `corpus.tin` run every transcendental function over the same
deterministic inputs (about 20,000 per function: 70 edge cases plus uniform, log-uniform, raw-bit
and quarter-integer values, so NaN, infinities, subnormals and arguments up to 1.8e308 are all in) and
print a hash of the result bits, or every result with `dump`. The Go side uses Go's pure algorithms for
Exp, Exp2, Sinh, Cosh, Tanh and Pow, because `math.Exp` is assembly on arm64 and amd64 and returns 0 for
Exp(-745) where the true value rounds to the smallest subnormal.

    go build -o /tmp/ref ./bench/ref/gauge && tin build bench/ref/gauge/corpus.tin -o /tmp/corpus
    /tmp/ref corpus > go.txt; /tmp/corpus corpus > tin.txt; diff go.txt tin.txt

Result (macOS arm64): bit-identical to Go for 15 of 21 hashes, over 586,156 results in all: sin, cos,
tan (with Payne-Hanek reduction up to 1.8e308), asin, acos, atan, atan2, sinh, cosh, tanh, exp, exp2,
cbrt, hypot, mod. The six that differ are log, log2, log10, log1p, pow and the pow subset: for about one
input in a thousand the result differs by exactly one ulp. The cause is the fused multiply-add. Both
compilers fuse on arm64, but not the same products. In the disassembly of Go's `math.log` the last
line `k*Ln2Hi - (...)` is one fused instruction and `hfsq = 0.5*f*f` is folded into the fused operations
that use it rather than rounded once; Tin's compiler has no `x*y - a` form, fuses the right-hand product
of an add, and rounds a product that has two uses once.
Neither is wrong, and Go's own results differ between its arm64 and amd64 builds for the same reason.

Error against exact arithmetic (Python `decimal`, 800 digits for log1p), in ulps, on the inputs where the
result is a normal number:

| function | inputs | Tin = Go | max Tin | max Go | mean Tin | mean Go |
|---|---|---|---|---|---|---|
| log | 10,110 | 99.80% | 0.718 | 0.725 | 0.2509 | 0.2510 |
| log2 | 10,110 | 95.75% | 35.1 | 34.1 | 0.2776 | 0.2767 |
| log10 | 10,110 | 99.81% | 1.76 | 1.61 | 0.3780 | 0.3780 |
| log1p | 12,875 | 99.93% | 0.707 | 0.707 | 0.2034 | 0.2034 |
| pow (4,000 sampled) | 3,476 | 99.94% | 141 | 141 | 4.209 | 4.209 |

The two large maxima are Go's algorithms, not the port: Log2 loses precision for x near 1 (it adds
Log(frac)/ln2 to an exponent of 1), and Pow's error grows with the size of the result. They are
reproduced faithfully. A more accurate Log2 and Pow would be a Tin improvement on Go, and the corpus
would then show them as deliberate differences.
